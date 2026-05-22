from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import date
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse

from port.config import (
    config,
    default_agent_models,
    resolved_model_options,
)
from port.i18n import DEFAULT_LOCALE
from port.market_data import fetch_corporate_actions, fetch_position_snapshot
from port.portfolio import Portfolio
from port.web.api_models import LLMConfigBody, StartRequest, llm_overrides_from_body
from port.web.sessions import ReviewSession

router = APIRouter()
event_log = logging.getLogger("port.events")
STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
_reviews: dict[str, ReviewSession] = {}
_TICKER_RE = re.compile(config.server.ticker_regex_pattern)


def _position_actions_supplied(raw_position) -> bool:
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


async def _enrich_portfolio_actions(portfolio: Portfolio, raw_portfolio) -> Portfolio:
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
                timeout=config.market.yfinance_timeout_seconds,
            )
        except Exception as exc:
            detail = f"Corporate action fetch failed for {position.ticker}: {exc}"
            raise HTTPException(status_code=502, detail=detail) from exc
        enriched.append(position.model_copy(update={"dividend": dividend, "split": split}))
    return portfolio.model_copy(update={"positions": enriched})


@router.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text()


@router.get("/api/config")
async def get_config():
    return {
        "llm_base_url": config.llm.base_url,
        "llm_model": config.llm.model,
        "fast_llm_base_url": config.llm.fast_base_url,
        "fast_llm_model": config.llm.fast_model,
        "model_options": resolved_model_options(),
        "default_agent_models": default_agent_models(),
        "llm_connect_timeout": config.llm.connect_timeout,
        "llm_read_timeout": config.llm.read_timeout,
    }


def _llm_chat_completions_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/chat/completions"


@router.post("/api/config/test")
async def test_llm_config(body: LLMConfigBody):
    base_url = (body.llm_base_url or config.llm.base_url).strip()
    model = (body.llm_model or config.llm.model).strip()
    api_key = body.llm_api_key if body.llm_api_key is not None else config.llm.api_key
    if not base_url:
        raise HTTPException(status_code=400, detail="API URL is required")
    if not model:
        raise HTTPException(status_code=400, detail="Model name is required")

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    headers["Content-Type"] = "application/json"
    try:
        async with httpx.AsyncClient(
            timeout=config.server.llm_test_timeout_seconds, trust_env=False
        ) as client:
            response = await client.post(
                _llm_chat_completions_url(base_url),
                headers=headers,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
                    "temperature": config.server.llm_test_temperature,
                    "max_tokens": config.server.llm_test_max_tokens,
                },
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Connection failed: {exc}") from exc

    if response.status_code >= 400:
        detail = (
            response.text.strip()[: config.truncation.error_detail_chars] or response.reason_phrase
        )
        raise HTTPException(
            status_code=502,
            detail=f"Test message returned HTTP {response.status_code}: {detail}",
        )
    try:
        response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Test message did not return JSON") from exc
    return {"ok": True, "message": "Connected. Test message succeeded.", "model": model}


@router.get("/api/market/quote/{ticker}")
async def market_quote(ticker: str, actions_start: date | None = None):
    clean = ticker.strip().upper()
    if not clean or not _TICKER_RE.match(clean):
        raise HTTPException(status_code=400, detail="Invalid ticker")
    if actions_start is None:
        raise HTTPException(status_code=400, detail="actions_start is required")
    snap = await asyncio.to_thread(fetch_position_snapshot, clean, actions_start)
    if snap is None:
        raise HTTPException(status_code=404, detail="Quote unavailable")
    return snap.model_dump()


@router.post("/api/review/start")
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
        llm_overrides=llm_overrides_from_body(req.llm),
        locale=req.locale or DEFAULT_LOCALE,
    )
    _reviews[review_id] = session
    session.start()
    event_log.info("review_created review_id=%s", review_id)
    return {"review_id": review_id}


@router.get("/api/review/{review_id}/stream")
async def stream_events(review_id: str):
    session = _reviews.get(review_id)
    if not session:
        raise HTTPException(status_code=404, detail="Review not found")

    async def generator():
        async for item in session.subscribe():
            yield {"data": json.dumps(item, default=str)}

    return EventSourceResponse(generator())


@router.get("/api/review/{review_id}/result")
async def get_result(review_id: str):
    session = _reviews.get(review_id)
    if not session:
        raise HTTPException(status_code=404, detail="Review not found")
    return _session_snapshot(session) | {"final_state": session.final_state}


@router.post("/api/review/{review_id}/stop")
async def stop_review(review_id: str):
    session = _reviews.get(review_id)
    if not session:
        raise HTTPException(status_code=404, detail="Review not found")
    stopped = await session.stop()
    return {"review_id": review_id, "status": session.status, "stopped": stopped}


@router.get("/api/review/{review_id}/snapshot")
async def get_snapshot(review_id: str):
    session = _reviews.get(review_id)
    if not session:
        raise HTTPException(status_code=404, detail="Review not found")
    return _session_snapshot(session)


def _session_snapshot(session: ReviewSession) -> dict:
    return {
        "status": session.status,
        "agent_outputs": session.agent_outputs,
        "agent_output_updated_at": session.agent_output_updated_at,
        "requested_locale": session.locale_state.requested_locale,
        "content_locale": session.locale_state.content_locale,
        "translation_fallback_used": session.locale_state.translation_fallback_used,
    }
