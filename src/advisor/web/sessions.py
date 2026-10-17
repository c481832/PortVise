from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from advisor.config import config
from advisor.graph import build_graph, make_initial_state
from advisor.llm.client import llm_runtime_overrides
from advisor.llm.context import review_stop_event, step_callback
from advisor.llm.structured import StructuredLLMOutputError, invoke_structured
from advisor.logging import flow_log
from advisor.prompts import summary_system_prompt
from advisor.schemas.portfolio import Portfolio
from advisor.schemas.summary import AgentTaskSummary
from advisor.util import safe_json, serialise
from advisor.web.events import (
    DONE_SUPPRESSED_NODES,
    START_SUPPRESSED_NODES,
    graph_agent_for_chain_event,
)

event_log = logging.getLogger("advisor.events")
TERMINAL_STATUSES = frozenset({"done", "error", "stopped"})


def summarize_agent_output(agent: str, output: Any, portfolio: Portfolio) -> AgentTaskSummary:
    max_chars = config.agent_summary.max_input_chars
    result: AgentTaskSummary = invoke_structured(  # type: ignore[assignment]
        AgentTaskSummary,
        [
            SystemMessage(content=summary_system_prompt()),
            HumanMessage(
                content="\n\n".join(
                    [
                        f"AGENT: {agent}",
                        f"PORTFOLIO: {portfolio.name or 'Portfolio'}",
                        f"OUTPUT JSON:\n{safe_json(output, max_chars=max_chars)}",
                    ]
                )
            ),
        ],
        agent="agent_summary",
        max_tokens=config.llm.summary_max_tokens,
        temperature=config.llm.summary_temperature,
        use_agent_model=True,
    )
    if not result.summary.strip():
        raise RuntimeError(f"agent summary for {agent} returned an empty summary string")
    return result


def review_error_event(exc: Exception) -> dict[str, Any]:
    event = {"type": "error", "message": str(exc), "ts": datetime.now(UTC).isoformat()}
    if isinstance(exc, StructuredLLMOutputError):
        event["agent"] = exc.agent
        event["technical_message"] = type(exc.__cause__ or exc).__name__
    return event


def stopped_event(message: str) -> dict[str, Any]:
    return {"type": "stopped", "message": message, "ts": datetime.now(UTC).isoformat()}


class ReviewSession:
    def __init__(
        self,
        review_id: str,
        portfolio: Portfolio,
        llm_overrides: dict | None,
        inherited_feedback: list[dict[str, Any]],
        on_terminal: Callable[[ReviewSession], Awaitable[None]],
    ):
        self.review_id = review_id
        self.portfolio = portfolio
        self._llm_overrides = llm_overrides
        self._on_terminal = on_terminal
        self.inherited_feedback = inherited_feedback
        self.config: RunnableConfig = {"configurable": {"thread_id": review_id}}
        self.graph = build_graph()
        self.status: str = "starting"
        self.final_state: dict | None = None
        self.agent_outputs: dict[str, Any] = {}
        self.agent_output_updated_at: dict[str, str] = {}
        self.last_error_event: dict[str, Any] | None = None
        self._run_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._last_summary_task: asyncio.Task | None = None
        self._stream_closed = False
        self._stop_event = threading.Event()
        # Persisted events, replayed to late subscribers; ``None`` marks the end of the stream.
        self._events: list[dict[str, Any] | None] = []
        self._subscribers: set[asyncio.Queue[tuple[dict[str, Any] | None, int | None]]] = set()

    def start(self):
        event_log.info("review_start review_id=%s", self.review_id)
        self._run_task = asyncio.create_task(self.run())
        self._heartbeat_task = asyncio.create_task(self.heartbeat())

    async def stop(self, reason: str) -> bool:
        if self.status in TERMINAL_STATUSES:
            return False
        self.status = "stopped"
        self._stop_event.set()
        await self.finish(stopped_event(reason))
        if self._run_task is not None:
            self._run_task.cancel()
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
        return True

    async def finish(self, event: dict[str, Any] | None) -> None:
        if event is not None:
            await self.emit(event, persist=True)
        if not self._stream_closed:
            await self.emit(None, persist=True)
        try:
            await self._on_terminal(self)
        except Exception:
            event_log.exception("review_terminal_callback_failed review_id=%s", self.review_id)
            return
        # The durable result is written, so late subscribers only need the end marker.
        self._events = [None]

    async def heartbeat(self):
        while not self._stream_closed:
            await asyncio.sleep(config.server.heartbeat_seconds)
            await self.emit(
                {"type": "heartbeat", "ts": datetime.now(UTC).isoformat()}, persist=False
            )

    async def emit(self, event: dict[str, Any] | None, *, persist: bool):
        if self._stream_closed and event is not None:
            return
        event_index = None
        if persist:
            self._events.append(event)
            event_index = len(self._events) - 1
        if event is None:
            self._stream_closed = True
            event_log.info(
                "review_stream_closed review_id=%s status=%s", self.review_id, self.status
            )
        elif event["type"] != "heartbeat":
            if event["type"] == "error":
                self.last_error_event = event
            agent = event.get("agent")
            event_log.info(
                "review_event review_id=%s type=%s agent=%s status=%s",
                self.review_id,
                event["type"],
                agent,
                self.status,
            )
            if agent:
                flow_log(agent).info(
                    "event type=%s step_index=%s label=%r",
                    event["type"],
                    event.get("step_index"),
                    event.get("label"),
                )
        for queue in self._subscribers:
            queue.put_nowait((event, event_index))

    async def subscribe(self):
        pos = 0
        queue: asyncio.Queue[tuple[dict[str, Any] | None, int | None]] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            while True:
                # Replay persisted events first, then consume live events from the queue.
                while pos < len(self._events):
                    item = self._events[pos]
                    pos += 1
                    if item is None:
                        return
                    yield item
                item, event_index = await queue.get()
                if event_index is not None:
                    if event_index < pos:
                        continue
                    pos = event_index + 1
                if item is None:
                    return
                yield item
        finally:
            self._subscribers.discard(queue)

    def queue_agent_summary(self, agent: str, output: Any, ts: str) -> None:
        self._last_summary_task = asyncio.create_task(
            self.emit_agent_summary(self._last_summary_task, agent, output, ts)
        )

    async def emit_agent_summary(
        self, previous: asyncio.Task | None, agent: str, output: Any, ts: str
    ):
        summary = await asyncio.to_thread(summarize_agent_output, agent, output, self.portfolio)
        # Summary calls run concurrently, but the UI sees agent completion order.
        if previous is not None:
            await previous
        await self.emit(
            {
                "type": "agent_summary",
                "agent": agent,
                "title": summary.title,
                "summary": summary.summary,
                "bullets": summary.bullets,
                "ts": ts,
            },
            persist=True,
        )

    async def wait_for_agent_summaries(self):
        # Each summary waits for the one before it, so the last task covers them all.
        if self._last_summary_task is not None:
            await asyncio.gather(self._last_summary_task, return_exceptions=True)

    async def run(self):
        loop = asyncio.get_running_loop()

        def report_step(agent: str, step_index: int, label: str):
            # Agents run in worker threads, so hand the event back to the loop.
            flow_log(agent).info("step step_index=%d label=%r", step_index, label)
            asyncio.run_coroutine_threadsafe(
                self.emit(
                    {
                        "type": "agent_step",
                        "agent": agent,
                        "step_index": step_index,
                        "label": label,
                        "ts": datetime.now(UTC).isoformat(),
                    },
                    persist=True,
                ),
                loop,
            )

        # This task owns its context, so these settings end with it.
        step_callback.set(report_step)
        review_stop_event.set(self._stop_event)
        llm_runtime_overrides.set(self._llm_overrides)
        initial_state = make_initial_state(
            self.portfolio, inherited_feedback=self.inherited_feedback
        )
        try:
            async for event in self.graph.astream_events(  # type: ignore[arg-type]
                initial_state, self.config, version=config.server.sse_stream_version
            ):
                await self.handle_event(event)  # type: ignore[arg-type]
            if self.status == "stopped":
                return
            state = await self.graph.aget_state(self.config)
            self.final_state = serialise(state.values)
            self.status = "done"
            await self.wait_for_agent_summaries()
            await self.finish(None)
        except asyncio.CancelledError:
            if self.status != "stopped":
                self.status = "stopped"
                await self.finish(stopped_event("Review stopped."))
        except Exception as exc:
            self.status = "error"
            event_log.exception("review_failed review_id=%s", self.review_id)
            await self.finish(review_error_event(exc))

    async def handle_event(self, event: dict):
        if self.status == "stopped":
            return
        kind = event["event"]
        if kind not in ("on_chain_start", "on_chain_end"):
            return
        agent = graph_agent_for_chain_event(event)
        if agent is None:
            return
        node_name = event["name"]

        if kind == "on_chain_start":
            if node_name in START_SUPPRESSED_NODES:
                flow_log(agent).info("chain_start suppressed node=%s", node_name)
                return
            self.status = "running"
            flow_log(agent).info("chain_start")
            await self.emit(
                {"type": "agent_start", "agent": agent, "ts": datetime.now(UTC).isoformat()},
                persist=True,
            )
            return

        output = serialise(event["data"]["output"])
        flow_log(agent).info("chain_end output=%s", output)
        ts = datetime.now(UTC).isoformat()
        # An agent made of several nodes accumulates one output across them.
        merged = {**self.agent_outputs.get(agent, {}), **output}
        self.agent_outputs[agent] = merged
        self.agent_output_updated_at[agent] = ts
        if node_name in DONE_SUPPRESSED_NODES:
            return
        await self.emit(
            {"type": "agent_done", "agent": agent, "output": merged, "ts": ts},
            persist=True,
        )
        self.queue_agent_summary(agent, merged, ts)
