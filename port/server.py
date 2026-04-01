"""FastAPI server with SSE streaming for the portfolio review GUI."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from port.graph import build_graph, make_initial_state
from port.market_data import fetch_position_snapshot
from port.portfolio import Portfolio

app = FastAPI(title="Portfolio Advisor")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_reviews: dict[str, ReviewSession] = {}

_AGENT_NAMES = {"planner", "data", "news", "risk", "regime", "theme", "validation", "manager"}


class ReviewSession:
    """
    Broadcast event log — any number of SSE clients can subscribe and read
    from their own position independently.
    """

    def __init__(self, review_id: str, portfolio: Portfolio):
        self.review_id = review_id
        self.portfolio = portfolio
        self.config = {"configurable": {"thread_id": review_id}}
        self.graph = build_graph()
        self.status: str = "starting"
        self.interrupt_payload: dict | None = None
        self.final_state: dict | None = None

        # Broadcast log: append events here; None = end-of-stream sentinel
        self._events: list[Any] = []
        self._event_added = asyncio.Event()

    def start(self):
        asyncio.create_task(self._run(make_initial_state(self.portfolio)))

    async def _emit(self, event: Any):
        """Append an event and wake all waiting SSE generators."""
        self._events.append(event)
        self._event_added.set()

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
        try:
            async for event in self.graph.astream_events(input_, self.config, version="v2"):  # type: ignore[arg-type]
                await self._handle_event(event)  # type: ignore[arg-type]
        except Exception as exc:
            if not self._is_interrupt_exc(exc):
                self.status = "error"
                await self._emit({"type": "error", "message": str(exc)})
                await self._emit(None)
                return

        await self._check_for_interrupt()

    async def resume(self, user_response: str):
        self.status = "running"
        self.interrupt_payload = None
        await self._run(Command(resume=user_response))

    async def _check_for_interrupt(self):
        try:
            state = await self.graph.aget_state(self.config)  # type: ignore[arg-type]
        except Exception:
            await self._emit(None)
            return

        for task in state.tasks:
            if getattr(task, "interrupts", None):
                payload = task.interrupts[0].value
                self.status = "waiting_confirmation"
                self.interrupt_payload = payload
                await self._emit({"type": "interrupt", "payload": payload})
                return  # keep stream open — more events will come after resume

        if self.status not in ("done", "error"):
            await self._emit(None)

    async def _handle_event(self, event: dict):
        kind = event.get("event", "")
        name = event.get("name", "")

        if kind == "on_chain_start" and name in _AGENT_NAMES:
            self.status = "running"
            await self._emit({"type": "agent_start", "agent": name})

        elif kind == "on_chain_end" and name in _AGENT_NAMES:
            output = event.get("data", {}).get("output", {})
            serialised = _serialise(output)
            if name == "manager":
                self.status = "done"
                self.final_state = serialised
                await self._emit({"type": "agent_done", "agent": name, "output": serialised})
                await self._emit(None)  # close all SSE streams
            else:
                await self._emit({"type": "agent_done", "agent": name, "output": serialised})

    @staticmethod
    def _is_interrupt_exc(exc: Exception) -> bool:
        return "GraphInterrupt" in type(exc).__name__ or "Interrupt" in type(exc).__name__


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


@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text()


@app.get("/api/market/quote/{ticker}")
async def market_quote(ticker: str):
    """Live quote for one symbol (Yahoo Finance). Used by the portfolio UI for 1m/1y %."""
    clean = ticker.strip().upper()
    if not clean or not _TICKER_RE.match(clean):
        raise HTTPException(status_code=400, detail="Invalid ticker")
    snap = await asyncio.to_thread(fetch_position_snapshot, clean)
    if snap is None:
        raise HTTPException(status_code=404, detail="Quote unavailable")
    return snap.model_dump()


class StartRequest(BaseModel):
    portfolio: dict


@app.post("/api/review/start")
async def start_review(req: StartRequest):
    try:
        portfolio = Portfolio(**req.portfolio)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    review_id = str(uuid.uuid4())
    session = ReviewSession(review_id, portfolio)
    _reviews[review_id] = session
    session.start()
    return {"review_id": review_id}


class ConfirmRequest(BaseModel):
    response: str


@app.post("/api/review/{review_id}/confirm")
async def confirm_review(review_id: str, req: ConfirmRequest):
    session = _reviews.get(review_id)
    if not session:
        raise HTTPException(status_code=404, detail="Review not found")
    if session.status != "waiting_confirmation":
        raise HTTPException(status_code=409, detail=f"Session status is '{session.status}'")
    # Resume runs in a task — it pushes events to the SAME queue the SSE is reading
    asyncio.create_task(session.resume(req.response))
    return {"status": "resumed"}


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
        "interrupt_payload": session.interrupt_payload,
    }


@app.get("/api/review/{review_id}/status")
async def get_status(review_id: str):
    session = _reviews.get(review_id)
    if not session:
        raise HTTPException(status_code=404, detail="Review not found")
    return {"status": session.status, "interrupt_payload": session.interrupt_payload}
