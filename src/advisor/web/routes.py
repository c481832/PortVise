from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse

from advisor.agents.manager import build_manager_feedback_prompt, run_manager_review
from advisor.config import config
from advisor.llm.client import (
    configured_agent_models,
    llm_overrides_from_config,
    parse_model_base_urls,
    parse_model_extra_args,
    resolved_model_base_urls,
    resolved_model_options,
)
from advisor.logging import clear_advisor_log_files
from advisor.market_data import fetch_position_snapshot, fetch_ticker_profile
from advisor.run_new_review import enrich_portfolio
from advisor.schemas.allocation import AllocationReview
from advisor.schemas.news import NewsReview
from advisor.schemas.portfolio import Portfolio
from advisor.schemas.regime import RegimeReview
from advisor.schemas.risk import RiskReview
from advisor.schemas.runner import ReviewLLMConfig
from advisor.schemas.state import GraphState
from advisor.schemas.theme import ThemeReview
from advisor.score_past_calls import compute_track_record
from advisor.web.api_schemas import (
    ConfigUpdateRequest,
    FeedbackCandidateRequest,
    FeedbackRerunRequest,
    SearchConfigRequest,
    StartRequest,
)
from advisor.web.config_overrides import clear_ui_overrides, write_ui_overrides
from advisor.web.probes import (
    probe_llm_endpoint,
    probe_searxng,
    probe_tavily,
    short_error,
    validate_base_url,
)
from advisor.web.review_store import (
    latest_matching_feedback,
    list_review_summaries,
    load_review_result,
    review_result_payload,
    save_review_payload,
)
from advisor.web.sessions import TERMINAL_STATUSES, ReviewSession

router = APIRouter()
event_log = logging.getLogger("advisor.events")
UI_DIR = Path(__file__).resolve().parent / "ui"
SEARCH_PROVIDERS = ("tavily", "searxng")
live_reviews: dict[str, ReviewSession] = {}
TICKER_RE = re.compile(config.server.ticker_regex_pattern)


async def persist_and_evict_review(session: ReviewSession) -> None:
    await asyncio.to_thread(save_review_payload, review_result_payload(session))
    live_reviews.pop(session.review_id, None)


def live_session(review_id: str) -> ReviewSession:
    session = live_reviews.get(review_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return session


def review_payload(review_id: str) -> dict[str, Any]:
    session = live_reviews.get(review_id)
    if session is not None:
        return review_result_payload(session)
    stored = load_review_result(review_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return stored


def require_unlocked_settings() -> None:
    if config.server.lock_settings:
        raise HTTPException(status_code=403, detail="Settings are locked on this server.")


def parse_ticker(ticker: str) -> str:
    clean = ticker.strip().upper()
    if not clean or not TICKER_RE.match(clean):
        raise HTTPException(status_code=400, detail="Invalid ticker")
    return clean


@router.get("/", response_class=HTMLResponse)
async def index():
    html = (UI_DIR / "index.html").read_text()
    return HTMLResponse(
        html,
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


def config_payload() -> dict:
    # API keys are write-only: they are never sent back to the browser.
    return {
        "llm_base_url": config.llm.base_url,
        "llm_model": config.llm.model,
        "model_options": resolved_model_options(),
        "model_base_urls": resolved_model_base_urls(),
        "model_extra_args": config.llm.model_extra_args,
        "default_agent_models": configured_agent_models(),
        "search_provider": config.search.provider,
        "searxng_url": config.search.searxng_url,
        "min_allocated_capital": config.capital_allocation.min_allocated_capital,
        "max_cash_weight": 1.0 - config.capital_allocation.min_allocated_capital,
        "max_drawdown": config.capital_allocation.max_drawdown,
        "cash_yield_annual_pct": config.capital_allocation.cash_yield_annual_pct,
        "settings_locked": config.server.lock_settings,
    }


@router.get("/api/config")
async def get_config():
    return config_payload()


@router.post("/api/config")
async def update_config(body: ConfigUpdateRequest):
    require_unlocked_settings()
    if body.llm_base_url:
        validate_base_url(body.llm_base_url.strip(), "Endpoint")
    if body.searxng_url and body.searxng_url.strip():
        validate_base_url(body.searxng_url.strip(), "SearXNG")
    if body.search_provider is not None and body.search_provider not in SEARCH_PROVIDERS:
        raise HTTPException(
            status_code=400, detail=f"Unknown search provider: {body.search_provider!r}"
        )
    if body.agent_models:
        unknown = sorted(set(body.agent_models) - set(configured_agent_models()))
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown agent keys: {unknown}")
    if body.model_base_urls is not None:
        try:
            parse_model_base_urls(json.dumps(body.model_base_urls))
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid model endpoint map: {exc}"
            ) from exc
        for model_name, url in body.model_base_urls.items():
            if url and url.strip():
                validate_base_url(url.strip(), f"Endpoint for {model_name}")
    if body.model_extra_args is not None:
        try:
            parse_model_extra_args(body.model_extra_args)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid extra call arguments JSON: {exc}"
            ) from exc
    try:
        write_ui_overrides(
            base_url=body.llm_base_url,
            model=body.llm_model,
            api_key=body.llm_api_key,
            model_options=body.model_options,
            model_base_urls=body.model_base_urls,
            model_extra_args=body.model_extra_args,
            agent_models=body.agent_models,
            search_provider=body.search_provider,
            searxng_url=body.searxng_url,
            tavily_api_key=body.tavily_api_key,
            min_allocated_capital=body.min_allocated_capital,
            max_drawdown=body.max_drawdown,
            cash_yield_annual_pct=body.cash_yield_annual_pct,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not save settings: {exc}") from exc
    return config_payload()


@router.delete("/api/config")
async def reset_config():
    require_unlocked_settings()
    try:
        clear_ui_overrides()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not restore defaults: {exc}") from exc
    return config_payload()


@router.post("/api/config/test")
async def test_llm_config(body: ReviewLLMConfig):
    require_unlocked_settings()
    base_url = (body.llm_base_url or config.llm.base_url).strip()
    model = (body.llm_model or config.llm.model).strip()
    api_key = body.llm_api_key if body.llm_api_key is not None else config.llm.api_key

    if not base_url:
        raise HTTPException(status_code=400, detail="API URL is required")
    if not model:
        raise HTTPException(status_code=400, detail="Model name is required")

    await probe_llm_endpoint(base_url=base_url, model=model, api_key=api_key)
    return {"ok": True, "message": "Endpoint reachable.", "model": model}


@router.post("/api/config/search/test")
async def test_search_config(body: SearchConfigRequest):
    require_unlocked_settings()
    provider = (body.search_provider or config.search.provider).strip()

    if provider == "tavily":
        api_key = (
            body.tavily_api_key if body.tavily_api_key is not None else config.search.tavily_api_key
        ).strip()
        if not api_key:
            raise HTTPException(status_code=400, detail="Set a Tavily API key to test.")
        await probe_tavily(api_key)
        return {"ok": True, "message": "Tavily key OK."}

    if provider == "searxng":
        searxng_url = (
            body.searxng_url if body.searxng_url is not None else config.search.searxng_url
        ).strip()
        if not searxng_url:
            raise HTTPException(status_code=400, detail="Set a SearXNG URL to test.")
        await probe_searxng(searxng_url)
        return {"ok": True, "message": "SearXNG reachable."}

    raise HTTPException(status_code=400, detail=f"Unknown search provider: {provider!r}")


@router.get("/api/market/quote/{ticker}")
async def market_quote(ticker: str):
    snap = await asyncio.to_thread(fetch_position_snapshot, parse_ticker(ticker))
    return snap.model_dump()


@router.get("/api/market/profile/{ticker}")
async def market_profile(ticker: str):
    clean = parse_ticker(ticker)
    try:
        profile = await asyncio.to_thread(fetch_ticker_profile, clean)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Profile unavailable for {clean}") from exc
    return profile.model_dump()


@router.post("/api/review/start")
async def start_review(req: StartRequest):
    # A custom endpoint would receive the saved API key, so it counts as a settings change.
    custom_llm = req.llm is not None and (
        req.llm.llm_base_url is not None or req.llm.llm_api_key is not None
    )
    if custom_llm:
        require_unlocked_settings()
    try:
        portfolio = await enrich_portfolio(
            req.portfolio,
            "strict",
            warnings=[],
            deadline=None,
            progress_callback=None,
            started_monotonic=time.monotonic(),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    clear_advisor_log_files()
    review_id = str(uuid.uuid4())
    session = ReviewSession(
        review_id,
        portfolio,
        llm_overrides=llm_overrides_from_config(req.llm),
        inherited_feedback=[item.model_dump(mode="json") for item in req.inherited_feedback],
        on_terminal=persist_and_evict_review,
    )
    live_reviews[review_id] = session
    session.start()
    event_log.info("review_created review_id=%s", review_id)
    return {"review_id": review_id}


@router.post("/api/reviews/feedback-candidates")
async def get_feedback_candidates(body: FeedbackCandidateRequest):
    portfolio = body.portfolio.model_dump(mode="json")
    return {"match": await asyncio.to_thread(latest_matching_feedback, portfolio)}


def manager_rerun_state(payload: dict[str, Any]) -> GraphState:
    final_state = payload["final_state"]
    return {
        "portfolio": Portfolio.model_validate(final_state["portfolio"]),
        "inherited_feedback": final_state["inherited_feedback"],
        "news_focus": final_state["news_focus"],
        "market_data": final_state["market_data"],
        "news_collector_text": final_state["news_collector_text"],
        "news_review": NewsReview.model_validate(final_state["news_review"]),
        "risk_review": RiskReview.model_validate(final_state["risk_review"]),
        "regime_review": RegimeReview.model_validate(final_state["regime_review"]),
        "theme_review": ThemeReview.model_validate(final_state["theme_review"]),
        "allocation_review": AllocationReview.model_validate(final_state["allocation_review"]),
        "manager_review": None,
    }


@router.post("/api/review/{review_id}/feedback")
async def submit_review_feedback(review_id: str, body: FeedbackRerunRequest):
    comment = body.comment.strip()
    if not comment:
        raise HTTPException(status_code=400, detail="Feedback comment is required.")
    payload = review_payload(review_id)
    if payload["status"] != "done":
        raise HTTPException(status_code=409, detail="Review must be complete before feedback.")

    rounds = payload["feedback_rounds"]
    round_: dict[str, Any] = {
        "round_id": str(uuid.uuid4()),
        "submitted_at": datetime.now(UTC).isoformat(),
        "user_comment": comment,
        "status": "running",
    }
    rounds.append(round_)
    save_review_payload(payload)

    # A failed rerun is part of the review's history, so it is recorded on the round.
    try:
        state = manager_rerun_state(payload)
        human_msg = build_manager_feedback_prompt(
            state,
            user_comment=comment,
            previous_rounds=rounds[:-1],
        )
        manager_review = await asyncio.to_thread(run_manager_review, state, human_msg)
    except Exception as exc:
        event_log.exception("manager_rerun_failed review_id=%s", review_id)
        round_["status"] = "error"
        round_["error"] = short_error(exc)
    else:
        manager_payload = manager_review.model_dump(mode="json")
        round_["status"] = "done"
        round_["manager_review"] = manager_payload
        payload["final_state"]["manager_review"] = manager_payload
        payload["agent_outputs"]["manager"] = {"manager_review": manager_payload}
        payload["agent_output_updated_at"]["manager"] = datetime.now(UTC).isoformat()
    payload["saved_at"] = datetime.now(UTC).isoformat()
    save_review_payload(payload)
    return payload


@router.get("/api/reviews")
async def get_review_summaries(limit: int):
    clean_limit = max(1, min(limit, 100))
    live = [
        {
            "review_id": session.review_id,
            "status": session.status,
            "portfolio_name": session.portfolio.name,
            "saved_at": "",
            "preview": "",
        }
        for session in live_reviews.values()
        if session.status not in TERMINAL_STATUSES
    ]
    stored = await asyncio.to_thread(list_review_summaries, limit=clean_limit)
    return {"reviews": (live + stored)[:clean_limit]}


@router.get("/api/review/{review_id}/stream")
async def stream_events(review_id: str):
    session = live_session(review_id)

    async def generator():
        async for item in session.subscribe():
            yield {"data": json.dumps(item, default=str)}

    return EventSourceResponse(generator())


@router.get("/api/review/{review_id}/result")
async def get_result(review_id: str):
    return review_payload(review_id)


@router.get("/api/review/{review_id}/snapshot")
async def get_snapshot(review_id: str):
    payload = review_payload(review_id)
    keys = ("status", "agent_outputs", "agent_output_updated_at", "last_error")
    return {key: payload[key] for key in keys}


@router.get("/api/review/{review_id}/track-record")
async def get_track_record(review_id: str):
    payload = review_payload(review_id)
    if payload["status"] != "done":
        raise HTTPException(status_code=409, detail="Review is not complete")
    try:
        review = await asyncio.to_thread(compute_track_record, payload)
    except Exception as exc:
        event_log.warning("track record failed for review %s: %s", review_id, exc)
        raise HTTPException(
            status_code=502, detail=f"Could not compute track record: {exc}"
        ) from exc
    return review.model_dump(mode="json")


@router.post("/api/review/{review_id}/stop")
async def stop_review(review_id: str):
    session = live_session(review_id)
    stopped = await session.stop("Review stopped by user.")
    return {"review_id": review_id, "status": session.status, "stopped": stopped}
