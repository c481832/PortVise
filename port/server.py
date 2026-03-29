"""FastAPI server with SSE streaming for the portfolio review GUI."""
from __future__ import annotations

import asyncio
import json
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
from port.portfolio import Portfolio

app = FastAPI(title="Portfolio Advisor")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# In-memory store: review_id → ReviewSession
_reviews: dict[str, "ReviewSession"] = {}


class ReviewSession:
    def __init__(self, review_id: str, portfolio: Portfolio):
        self.review_id = review_id
        self.portfolio = portfolio
        self.config = {"configurable": {"thread_id": review_id}}
        self.graph = build_graph()  # each session gets its own graph+checkpointer
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self.status: str = "starting"  # starting | waiting_confirmation | running | done | error
        self.interrupt_payload: dict | None = None
        self.final_state: dict | None = None
        self._task: asyncio.Task | None = None

    def start(self):
        self._task = asyncio.create_task(self._run())

    async def _run(self):
        initial_state = make_initial_state(self.portfolio)
        try:
            async for event in self.graph.astream_events(
                initial_state, self.config, version="v2"
            ):
                await self._handle_event(event)
        except Exception as exc:
            self.status = "error"
            await self.event_queue.put({"type": "error", "message": str(exc)})
        finally:
            await self.event_queue.put(None)  # sentinel

    async def resume(self, user_response: str):
        self.status = "running"
        self.interrupt_payload = None
        try:
            async for event in self.graph.astream_events(
                Command(resume=user_response), self.config, version="v2"
            ):
                await self._handle_event(event)
        except Exception as exc:
            self.status = "error"
            await self.event_queue.put({"type": "error", "message": str(exc)})
        finally:
            await self.event_queue.put(None)

    async def _handle_event(self, event: dict):
        kind = event.get("event", "")
        name = event.get("name", "")

        if kind == "on_chain_start" and name in _AGENT_NAMES:
            self.status = "running"
            await self.event_queue.put({"type": "agent_start", "agent": name})

        elif kind == "on_chain_end" and name in _AGENT_NAMES:
            output = event.get("data", {}).get("output", {})
            serialised = _serialise(output)
            if name == "planner":
                self.status = "done"
                self.final_state = serialised
            await self.event_queue.put({
                "type": "agent_done",
                "agent": name,
                "output": serialised,
            })

        elif kind == "on_interrupt":
            payload = event.get("data", {}).get("value", {})
            self.status = "waiting_confirmation"
            self.interrupt_payload = payload
            await self.event_queue.put({"type": "interrupt", "payload": payload})


_AGENT_NAMES = {"plan", "news", "risk", "regime", "theme", "validation", "planner"}


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


# ── HTTP Endpoints ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text()


class StartRequest(BaseModel):
    portfolio: dict


@app.post("/api/review/start")
async def start_review(req: StartRequest):
    try:
        portfolio = Portfolio(**req.portfolio)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

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
    asyncio.create_task(session.resume(req.response))
    return {"status": "resumed"}


@app.get("/api/review/{review_id}/stream")
async def stream_events(review_id: str):
    session = _reviews.get(review_id)
    if not session:
        raise HTTPException(status_code=404, detail="Review not found")

    async def generator():
        while True:
            item = await session.event_queue.get()
            if item is None:
                break
            yield {"data": json.dumps(item)}

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
