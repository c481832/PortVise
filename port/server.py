"""FastAPI server with SSE streaming for the portfolio review GUI."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import threading
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from port.agent_summary import summarize_agent_output
from port.config import (
    LLMOverrides,
    default_agent_models,
    freeze_agent_models,
    llm_runtime_overrides,
    locale_runtime_state,
    resolved_model_options,
    review_stop_event,
    settings,
)
from port.config import (
    step_callback as _step_cb_var,
)
from port.graph import build_graph, make_initial_state
from port.i18n import DEFAULT_LOCALE, LocaleRuntimeState, normalize_locale
from port.market_data import fetch_corporate_actions, fetch_position_snapshot
from port.portfolio import Portfolio

app = FastAPI(title="Portfolio Advisor")
event_log = logging.getLogger("port.events")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_reviews: dict[str, ReviewSession] = {}

# LangGraph node names that produce top-level chain events.
_GRAPH_NODE_NAMES = frozenset(
    {
        "planner",
        "data",
        "news_research",
        "news_synthesis",
        "risk",
        "regime",
        "theme",
        "validation",
        "manager",
    }
)

# SSE / UI agent id aliases for split news nodes.
_SSE_AGENT_FOR_NODE: dict[str, str] = {
    "news_research": "news",
    "news_synthesis": "news",
}

_SUMMARY_SUPPRESSED_NODES = frozenset({"news_research"})


def _merge_agent_output(existing: Any, new: Any) -> Any:
    """Merge repeated agent outputs while preserving latest values."""
    if isinstance(existing, dict) and isinstance(new, dict):
        merged = dict(existing)
        merged.update(new)
        return merged
    return new


def _graph_agent_for_chain_event(event: dict) -> str | None:
    """Map an ``on_chain_*`` event to a pipeline agent slot, or None to ignore.

    LangGraph tags top-level node runs with ``metadata.langgraph_node``. Nested LLM
    runnables can reuse the same ``name`` string as a graph node; requiring
    ``langgraph_node == name`` when the key is present avoids false ``agent_start``
    / ``agent_done`` SSE (e.g. parallel agents appearing to run before news finishes).
    """
    name = event.get("name", "")
    if not isinstance(name, str) or name not in _GRAPH_NODE_NAMES:
        return None
    md = event.get("metadata")
    if isinstance(md, dict) and "langgraph_node" in md:
        gn = md.get("langgraph_node")
        if gn is not None and gn != name:
            return None
    return _SSE_AGENT_FOR_NODE.get(name, name)


class ReviewSession:
    """
    Broadcast event log — any number of SSE clients can subscribe and read
    from their own position independently.
    """

    def __init__(
        self,
        review_id: str,
        portfolio: Portfolio,
        llm_overrides: LLMOverrides | None = None,
        locale: str | None = None,
    ):
        self.review_id = review_id
        self.portfolio = portfolio
        self._llm_overrides = llm_overrides
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
        self._run_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._summary_tasks: set[asyncio.Task] = set()
        self._summary_emit_lock = asyncio.Lock()
        self._summary_sequence = 0
        self._next_summary_sequence = 0
        self._pending_summary_events: dict[int, dict[str, Any]] = {}
        self._stream_closed = False
        self._stop_event = threading.Event()

        # Broadcast log: append events here; None = end-of-stream sentinel
        self._events: list[Any] = []
        self._event_added = asyncio.Event()

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
                )
            )
        )
        self._heartbeat_task = asyncio.create_task(self._heartbeat())

    async def stop(self, reason: str = "Review stopped by user.") -> bool:
        """Cancel an in-flight review and close all subscribers."""
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
        return True

    async def _heartbeat(self):
        """Send a keepalive ping every 5 s so browsers don't time out during long agents."""
        try:
            while True:
                await asyncio.sleep(5)
                if self._events and self._events[-1] is None:
                    return
                await self._emit({"type": "heartbeat", "ts": datetime.now(UTC).isoformat()})
        except asyncio.CancelledError:
            return

    async def _emit(self, event: Any):
        """Append an event and wake all waiting SSE generators."""
        if self._stream_closed:
            return
        self._events.append(event)
        if event is None:
            self._stream_closed = True
            event_log.info(
                "review_stream_closed review_id=%s status=%s",
                self.review_id,
                self.status,
            )
        elif isinstance(event, dict) and event.get("type") != "heartbeat":
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

    async def _close_stream(self):
        if self._stream_closed:
            return
        await self._emit(None)

    def _queue_agent_summary(self, agent: str, output: Any, ts: str) -> asyncio.Task:
        sequence = self._summary_sequence
        self._summary_sequence += 1
        task = asyncio.create_task(self._emit_agent_summary(sequence, agent, output, ts))
        self._summary_tasks.add(task)
        task.add_done_callback(self._summary_tasks.discard)
        return task

    async def _wait_for_agent_summaries(self):
        if not self._summary_tasks:
            return
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
            self._pending_summary_events[sequence] = event
            while self._next_summary_sequence in self._pending_summary_events:
                next_event = self._pending_summary_events.pop(self._next_summary_sequence)
                self._next_summary_sequence += 1
                await self._emit(next_event)

    async def subscribe(self):
        """Async generator — yields events to one SSE client from the beginning."""
        pos = 0
        while True:
            while pos < len(self._events):
                item = self._events[pos]
                pos += 1
                if item is None:
                    return
                yield item
            await self._event_added.wait()
            self._event_added.clear()

    async def _run(self, input_):
        loop = asyncio.get_running_loop()

        def _step_sync(agent: str, step_index: int, label: str):
            with contextlib.suppress(Exception):
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
                async for event in self.graph.astream_events(input_, self.config, version="v2"):  # type: ignore[arg-type]
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
                return
            except Exception as exc:
                self.status = "error"
                await self._emit({"type": "error", "message": str(exc)})
                await self._close_stream()
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
            _graph_agent_for_chain_event(event)
            if kind
            in (
                "on_chain_start",
                "on_chain_end",
            )
            else None
        )

        if kind == "on_chain_start" and agent is not None:
            self.status = "running"
            logging.getLogger(f"port.agentflow.{agent}").info("chain_start")
            await self._emit(
                {"type": "agent_start", "agent": agent, "ts": datetime.now(UTC).isoformat()}
            )

        elif kind == "on_chain_end" and agent is not None:
            node_name = event.get("name", "")
            output = event.get("data", {}).get("output", {})
            serialised = _serialise(output)
            logging.getLogger(f"port.agentflow.{agent}").info(
                "chain_end output=%s",
                _serialise(output),
            )
            now_ts = datetime.now(UTC).isoformat()
            self.agent_outputs[agent] = _merge_agent_output(
                self.agent_outputs.get(agent),
                serialised,
            )
            self.agent_output_updated_at[agent] = now_ts
            summary_output = self.agent_outputs[agent]
            if agent == "manager":
                # Persist the full graph state so /result includes validation + manager outputs.
                state = await self.graph.aget_state(self.config)  # type: ignore[arg-type]
                self.final_state = _serialise(getattr(state, "values", {}))
                self.status = "done"
                await self._emit(
                    {
                        "type": "agent_done",
                        "agent": agent,
                        "output": serialised,
                        "ts": now_ts,
                    }
                )
                if node_name not in _SUMMARY_SUPPRESSED_NODES:
                    self._queue_agent_summary(agent, summary_output, now_ts)
                await self._wait_for_agent_summaries()
                await self._close_stream()  # close all SSE streams
            else:
                await self._emit(
                    {
                        "type": "agent_done",
                        "agent": agent,
                        "output": serialised,
                        "ts": now_ts,
                    }
                )
                if node_name not in _SUMMARY_SUPPRESSED_NODES:
                    self._queue_agent_summary(agent, summary_output, now_ts)


# ── Serialisation helper ───────────────────────────────────────────────────


def _serialise(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return {k: _serialise(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialise(i) for i in obj]
    if isinstance(obj, date):
        return obj.isoformat()
    return obj


# ── HTTP Endpoints ─────────────────────────────────────────────────────────


_TICKER_RE = re.compile(r"^[A-Z0-9^.\-]{1,16}$")


def _position_actions_supplied(raw_position: Any) -> bool:
    if not isinstance(raw_position, dict):
        return False
    if "dividend" not in raw_position or "split" not in raw_position:
        return False
    try:
        dividend = float(raw_position.get("dividend", 0.0))
        split = float(raw_position.get("split", 1.0))
    except (TypeError, ValueError):
        return True
    return dividend != 0.0 or split != 1.0


async def _enrich_portfolio_actions(portfolio: Portfolio, raw_portfolio: Any) -> Portfolio:
    raw_positions = raw_portfolio.get("positions", []) if isinstance(raw_portfolio, dict) else []
    enriched = []
    for index, position in enumerate(portfolio.positions):
        raw_position = raw_positions[index] if index < len(raw_positions) else None
        if _position_actions_supplied(raw_position):
            enriched.append(position)
            continue

        try:
            dividend, split = await asyncio.to_thread(
                fetch_corporate_actions,
                position.ticker,
                position.entry_date,
            )
        except Exception as exc:
            detail = f"Corporate action fetch failed for {position.ticker}: {exc}"
            raise HTTPException(status_code=502, detail=detail) from exc

        enriched.append(position.model_copy(update={"dividend": dividend, "split": split}))

    return portfolio.model_copy(update={"positions": enriched})


@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text()


class LLMConfigBody(BaseModel):
    """Optional per-review overrides; omitted fields fall back to server `settings`."""

    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    fast_llm_base_url: str | None = None
    fast_llm_model: str | None = None
    agent_models: dict[str, str] | None = None


@app.get("/api/config")
async def get_config():
    """Effective LLM settings from the server (env / `.env`). Used by the UI; excludes API keys."""
    return {
        "llm_base_url": settings.llm_base_url,
        "llm_model": settings.llm_model,
        "fast_llm_base_url": settings.fast_llm_base_url,
        "fast_llm_model": settings.fast_llm_model,
        "model_options": resolved_model_options(),
        "default_agent_models": default_agent_models(),
        "llm_connect_timeout": settings.llm_connect_timeout,
        "llm_read_timeout": settings.llm_read_timeout,
    }


def _llm_chat_completions_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/chat/completions"


@app.post("/api/config/test")
async def test_llm_config(body: LLMConfigBody):
    """Test an OpenAI-compatible model endpoint with a tiny chat completion."""
    base_url = (body.llm_base_url or settings.llm_base_url).strip()
    model = (body.llm_model or settings.llm_model).strip()
    api_key = body.llm_api_key if body.llm_api_key is not None else settings.llm_api_key
    if not base_url:
        raise HTTPException(status_code=400, detail="API URL is required")
    if not model:
        raise HTTPException(status_code=400, detail="Model name is required")

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    headers["Content-Type"] = "application/json"
    try:
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            response = await client.post(
                _llm_chat_completions_url(base_url),
                headers=headers,
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": "Reply with exactly: ok",
                        }
                    ],
                    "temperature": 0,
                    "max_tokens": 8,
                },
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Connection failed: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text.strip()[:300] or response.reason_phrase
        raise HTTPException(
            status_code=502,
            detail=f"Test message returned HTTP {response.status_code}: {detail}",
        )

    try:
        response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Test message did not return JSON") from exc

    return {
        "ok": True,
        "message": "Connected. Test message succeeded.",
        "model": model,
    }


@app.get("/api/market/quote/{ticker}")
async def market_quote(ticker: str, actions_start: date | None = None):
    """Live quote for one symbol (Yahoo Finance). Used by the portfolio UI for 1m/1y %."""
    clean = ticker.strip().upper()
    if not clean or not _TICKER_RE.match(clean):
        raise HTTPException(status_code=400, detail="Invalid ticker")
    snap = await asyncio.to_thread(fetch_position_snapshot, clean, actions_start)
    if snap is None:
        raise HTTPException(status_code=404, detail="Quote unavailable")
    return snap.model_dump()


class StartRequest(BaseModel):
    portfolio: dict
    llm: LLMConfigBody | None = None
    locale: str | None = None


def _llm_overrides_from_body(body: LLMConfigBody | None) -> LLMOverrides | None:
    if body is None:
        return None
    am = freeze_agent_models(body.agent_models)
    has_overrides = any(
        x is not None
        for x in (
            body.llm_base_url,
            body.llm_model,
            body.llm_api_key,
            body.fast_llm_base_url,
            body.fast_llm_model,
        )
    )
    if not has_overrides and not am:
        return None
    return LLMOverrides(
        llm_base_url=body.llm_base_url,
        llm_model=body.llm_model,
        llm_api_key=body.llm_api_key,
        fast_llm_base_url=body.fast_llm_base_url,
        fast_llm_model=body.fast_llm_model,
        agent_models=am,
    )


@app.post("/api/review/start")
async def start_review(req: StartRequest):
    try:
        portfolio = Portfolio(**req.portfolio)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    portfolio = await _enrich_portfolio_actions(portfolio, req.portfolio)

    review_id = str(uuid.uuid4())
    session = ReviewSession(
        review_id,
        portfolio,
        llm_overrides=_llm_overrides_from_body(req.llm),
        locale=req.locale or DEFAULT_LOCALE,
    )
    _reviews[review_id] = session
    session.start()
    event_log.info("review_created review_id=%s", review_id)
    return {"review_id": review_id}


@app.get("/api/review/{review_id}/stream")
async def stream_events(review_id: str):
    session = _reviews.get(review_id)
    if not session:
        raise HTTPException(status_code=404, detail="Review not found")

    async def generator():
        async for item in session.subscribe():
            yield {"data": json.dumps(item, default=str)}

    return EventSourceResponse(generator())


@app.get("/api/review/{review_id}/result")
async def get_result(review_id: str):
    session = _reviews.get(review_id)
    if not session:
        raise HTTPException(status_code=404, detail="Review not found")
    return {
        "status": session.status,
        "final_state": session.final_state,
        "agent_outputs": session.agent_outputs,
        "agent_output_updated_at": session.agent_output_updated_at,
        "requested_locale": session.locale_state.requested_locale,
        "content_locale": session.locale_state.content_locale,
        "translation_fallback_used": session.locale_state.translation_fallback_used,
    }


@app.post("/api/review/{review_id}/stop")
async def stop_review(review_id: str):
    session = _reviews.get(review_id)
    if not session:
        raise HTTPException(status_code=404, detail="Review not found")
    stopped = await session.stop()
    return {"review_id": review_id, "status": session.status, "stopped": stopped}


@app.get("/api/review/{review_id}/snapshot")
async def get_snapshot(review_id: str):
    session = _reviews.get(review_id)
    if not session:
        raise HTTPException(status_code=404, detail="Review not found")
    return {
        "status": session.status,
        "agent_outputs": session.agent_outputs,
        "agent_output_updated_at": session.agent_output_updated_at,
        "requested_locale": session.locale_state.requested_locale,
        "content_locale": session.locale_state.content_locale,
        "translation_fallback_used": session.locale_state.translation_fallback_used,
    }
