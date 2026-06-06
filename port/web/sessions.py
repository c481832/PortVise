"""Review session orchestration and SSE event buffering."""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from port.agent_summary import summarize_agent_output
from port.config import (
    LLMOverrides,
    StructuredLLMOutputError,
    config,
    llm_runtime_overrides,
    locale_runtime_state,
    review_stop_event,
)
from port.config import step_callback as _step_cb_var
from port.graph import build_graph, make_initial_state
from port.i18n import LocaleRuntimeState, normalize_locale
from port.portfolio import Portfolio
from port.web.events import (
    DONE_SUPPRESSED_NODES,
    MERGED_OUTPUT_NODES,
    START_SUPPRESSED_NODES,
    SUMMARY_SUPPRESSED_NODES,
    graph_agent_for_chain_event,
    merge_agent_output,
    serialise,
)

event_log = logging.getLogger("port.events")


def _review_error_event(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, StructuredLLMOutputError):
        return {
            "type": "error",
            "agent": exc.agent,
            "message": str(exc),
            "technical_message": exc.__cause__.__class__.__name__
            if exc.__cause__ is not None
            else exc.__class__.__name__,
            "ts": datetime.now(UTC).isoformat(),
        }
    return {
        "type": "error",
        "message": str(exc),
        "ts": datetime.now(UTC).isoformat(),
    }


class ReviewSession:
    """Broadcast event log; each SSE client subscribes from its own cursor."""

    def __init__(
        self,
        review_id: str,
        portfolio: Portfolio,
        llm_overrides: LLMOverrides | None = None,
        locale: str | None = None,
        inherited_feedback: list[dict[str, Any]] | None = None,
        on_terminal: Callable[[ReviewSession], Any] | None = None,
    ):
        self.review_id = review_id
        self.portfolio = portfolio
        self._llm_overrides = llm_overrides
        self._on_terminal = on_terminal
        self.inherited_feedback = list(inherited_feedback or [])
        resolved_locale = normalize_locale(locale)
        self.locale_state = LocaleRuntimeState(
            requested_locale=resolved_locale,
            content_locale=resolved_locale,
        )
        self.config = {"configurable": {"thread_id": review_id}}
        self.graph = build_graph()
        self.status: str = "starting"
        self.final_state: dict | None = None
        self.agent_outputs: dict[str, Any] = {}
        self.agent_output_updated_at: dict[str, str] = {}
        self.last_error_event: dict[str, Any] | None = None
        self._run_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._summary_tasks: set[asyncio.Task] = set()
        self._summary_emit_lock = asyncio.Lock()
        self._summary_sequence = 0
        self._next_summary_sequence = 0
        self._pending_summary_events: dict[int, dict[str, Any]] = {}
        self._stream_closed = False
        self._stop_event = threading.Event()
        self._events: list[Any] = []
        self._event_added = asyncio.Event()
        self._subscribers: set[asyncio.Queue[tuple[Any, bool, int | None]]] = set()

    async def _notify_terminal(self) -> None:
        if self._on_terminal is None:
            return
        try:
            result = self._on_terminal(self)
            if inspect.isawaitable(result):
                await result
            self._compact_event_log()
        except Exception:
            event_log.exception("review_terminal_callback_failed review_id=%s", self.review_id)

    def _compact_event_log(self) -> None:
        """Drop replay history after the durable result has been written."""
        if self._stream_closed:
            self._events = [None]

    def start(self):
        event_log.info(
            "review_start review_id=%s locale=%s",
            self.review_id,
            self.locale_state.requested_locale,
        )
        self._run_task = asyncio.create_task(
            self._run(
                make_initial_state(
                    self.portfolio,
                    requested_locale=self.locale_state.requested_locale,
                    inherited_feedback=self.inherited_feedback,
                )
            )
        )
        self._heartbeat_task = asyncio.create_task(self._heartbeat())

    async def stop(self, reason: str = "Review stopped by user.") -> bool:
        if self.status in {"done", "error", "stopped"}:
            return False
        self.status = "stopped"
        self._stop_event.set()
        await self._emit(
            {
                "type": "stopped",
                "message": reason,
                "ts": datetime.now(UTC).isoformat(),
            }
        )
        await self._close_stream()
        if self._run_task is not None and not self._run_task.done():
            self._run_task.cancel()
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        await self._notify_terminal()
        return True

    async def _heartbeat(self):
        try:
            while True:
                await asyncio.sleep(config.server.heartbeat_seconds)
                if self._stream_closed:
                    return
                await self._emit(
                    {"type": "heartbeat", "ts": datetime.now(UTC).isoformat()},
                    persist=False,
                )
        except asyncio.CancelledError:
            return

    async def _emit(self, event: Any, *, persist: bool = True):
        if self._stream_closed and event is not None:
            return
        event_index = None
        if persist:
            self._events.append(event)
            event_index = len(self._events) - 1
        if event is None:
            self._stream_closed = True
            event_log.info(
                "review_stream_closed review_id=%s status=%s",
                self.review_id,
                self.status,
            )
        elif isinstance(event, dict) and event.get("type") != "heartbeat":
            if event.get("type") == "error":
                self.last_error_event = event
            event_log.info(
                "review_event review_id=%s type=%s agent=%s status=%s",
                self.review_id,
                event.get("type"),
                event.get("agent"),
                self.status,
            )
            agent = event.get("agent")
            if isinstance(agent, str):
                logging.getLogger(f"port.agentflow.{agent}").info(
                    "event type=%s step_index=%s label=%r",
                    event.get("type"),
                    event.get("step_index"),
                    event.get("label"),
                )
        self._event_added.set()
        for queue in list(self._subscribers):
            queue.put_nowait((event, persist, event_index))

    async def _close_stream(self):
        if not self._stream_closed:
            await self._emit(None)

    def _queue_agent_summary(self, agent: str, output: Any, ts: str) -> asyncio.Task:
        sequence = self._summary_sequence
        self._summary_sequence += 1
        task = asyncio.create_task(self._emit_agent_summary(sequence, agent, output, ts))
        self._summary_tasks.add(task)
        task.add_done_callback(self._summary_tasks.discard)
        return task

    async def _wait_for_agent_summaries(self):
        if self._summary_tasks:
            await asyncio.gather(*list(self._summary_tasks), return_exceptions=True)

    async def _emit_agent_summary(self, sequence: int, agent: str, output: Any, ts: str):
        summary = await asyncio.to_thread(summarize_agent_output, agent, output, self.portfolio)
        await self._emit_ordered_agent_summary(
            sequence,
            {
                "type": "agent_summary",
                "agent": agent,
                "title": summary.title,
                "summary": summary.summary,
                "bullets": summary.bullets,
                "ts": ts,
            },
        )

    async def _emit_ordered_agent_summary(self, sequence: int, event: dict[str, Any]):
        async with self._summary_emit_lock:
            # Summary calls run concurrently, but the UI sees agent completion order.
            self._pending_summary_events[sequence] = event
            while self._next_summary_sequence in self._pending_summary_events:
                next_event = self._pending_summary_events.pop(self._next_summary_sequence)
                self._next_summary_sequence += 1
                await self._emit(next_event)

    async def subscribe(self):
        pos = 0
        queue: asyncio.Queue[tuple[Any, bool, int | None]] = asyncio.Queue()
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
                item, persisted, event_index = await queue.get()
                if persisted and event_index is not None:
                    if event_index < pos:
                        continue
                    pos = event_index + 1
                if item is None:
                    return
                yield item
        finally:
            self._subscribers.discard(queue)

    async def _run(self, input_):
        loop = asyncio.get_running_loop()

        def _step_sync(agent: str, step_index: int, label: str):
            logging.getLogger(f"port.agentflow.{agent}").info(
                "step step_index=%d label=%r",
                step_index,
                label,
            )
            asyncio.run_coroutine_threadsafe(
                self._emit(
                    {
                        "type": "agent_step",
                        "agent": agent,
                        "step_index": step_index,
                        "label": label,
                        "ts": datetime.now(UTC).isoformat(),
                    }
                ),
                loop,
            )

        token = _step_cb_var.set(_step_sync)
        o_token = None
        l_token = locale_runtime_state.set(self.locale_state)
        s_token = review_stop_event.set(self._stop_event)
        if self._llm_overrides is not None:
            o_token = llm_runtime_overrides.set(self._llm_overrides)
        try:
            try:
                async for event in self.graph.astream_events(  # type: ignore[arg-type]
                    input_, self.config, version=config.server.sse_stream_version
                ):
                    await self._handle_event(event)  # type: ignore[arg-type]
            except asyncio.CancelledError:
                if self.status != "stopped":
                    self.status = "stopped"
                    await self._emit(
                        {
                            "type": "stopped",
                            "message": "Review stopped.",
                            "ts": datetime.now(UTC).isoformat(),
                        }
                    )
                await self._close_stream()
                await self._notify_terminal()
                return
            except Exception as exc:
                self.status = "error"
                event_log.exception("review_failed review_id=%s", self.review_id)
                await self._emit(_review_error_event(exc))
                await self._close_stream()
                await self._notify_terminal()
                return
        finally:
            if o_token is not None:
                llm_runtime_overrides.reset(o_token)
            review_stop_event.reset(s_token)
            locale_runtime_state.reset(l_token)
            _step_cb_var.reset(token)

        if self.status not in ("done", "error"):
            await self._wait_for_agent_summaries()
            await self._close_stream()

    async def _handle_event(self, event: dict):
        if self.status == "stopped":
            return
        kind = event.get("event", "")
        agent = (
            graph_agent_for_chain_event(event)
            if kind
            in (
                "on_chain_start",
                "on_chain_end",
            )
            else None
        )

        if kind == "on_chain_start" and agent is not None:
            node_name = event.get("name", "")
            if node_name in START_SUPPRESSED_NODES:
                logging.getLogger(f"port.agentflow.{agent}").info(
                    "chain_start suppressed node=%s",
                    node_name,
                )
                return
            self.status = "running"
            logging.getLogger(f"port.agentflow.{agent}").info("chain_start")
            await self._emit(
                {"type": "agent_start", "agent": agent, "ts": datetime.now(UTC).isoformat()}
            )
            return

        if kind == "on_chain_end" and agent is not None:
            node_name = event.get("name", "")
            output = event.get("data", {}).get("output", {})
            serialised = serialise(output)
            logging.getLogger(f"port.agentflow.{agent}").info(
                "chain_end output=%s",
                serialise(output),
            )
            now_ts = datetime.now(UTC).isoformat()
            self.agent_outputs[agent] = merge_agent_output(
                self.agent_outputs.get(agent),
                serialised,
            )
            self.agent_output_updated_at[agent] = now_ts
            summary_output = self.agent_outputs[agent]
            if node_name in DONE_SUPPRESSED_NODES:
                return
            event_output = summary_output if node_name in MERGED_OUTPUT_NODES else serialised
            await self._emit(
                {
                    "type": "agent_done",
                    "agent": agent,
                    "output": event_output,
                    "ts": now_ts,
                }
            )
            if node_name not in SUMMARY_SUPPRESSED_NODES:
                self._queue_agent_summary(agent, summary_output, now_ts)
            if agent == "manager":
                state = await self.graph.aget_state(self.config)  # type: ignore[arg-type]
                self.final_state = serialise(getattr(state, "values", {}))
                self.status = "done"
                await self._wait_for_agent_summaries()
                await self._close_stream()
                await self._notify_terminal()
