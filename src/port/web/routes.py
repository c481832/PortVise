from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse

from port.agents.manager import build_manager_feedback_human_message, run_manager_review
from port.config import (
    AGENT_MODEL_KEYS,
    clear_ui_overrides,
    config,
    default_agent_models,
    locale_runtime_state,
    parse_model_base_urls,
    parse_model_extra_args,
    resolved_model_base_urls,
    resolved_model_options,
    write_ui_overrides,
)
from port.i18n import DEFAULT_LOCALE, LocaleRuntimeState, normalize_locale
from port.logging_config import clear_port_log_files
from port.market_data import fetch_corporate_actions, fetch_position_snapshot, fetch_ticker_profile
from port.models import (
    AllocationReview,
    ManagerReview,
    NewsReview,
    RegimeReview,
    RiskReview,
    ThemeReview,
    ValidationReview,
)
from port.past_performance import compute_track_record
from port.portfolio import Portfolio
from port.web.api_models import (
    ConfigUpdateBody,
    FeedbackCandidateRequest,
    FeedbackRerunBody,
    LLMConfigBody,
    SearchConfigBody,
    StartRequest,
    llm_overrides_from_body,
)
from port.web.review_store import (
    latest_matching_feedback,
    list_review_summaries,
    load_review_result,
    review_result_payload,
    save_review_payload,
    save_review_result,
)
from port.web.sessions import ReviewSession

router = APIRouter()
event_log = logging.getLogger("port.events")
STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
_reviews: dict[str, ReviewSession] = {}
_TICKER_RE = re.compile(config.server.ticker_regex_pattern)


async def _persist_and_evict_review(session: ReviewSession) -> None:
    save_review_result(session)
    _reviews.pop(session.review_id, None)


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
    html = (STATIC_DIR / "index.html").read_text()
    return HTMLResponse(
        html,
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


def _config_payload() -> dict:
    """Current effective model, search, and capital policy config. Secret keys are never
    returned — only whether each is set — so they can't leak back to the browser."""
    return {
        "llm_base_url": config.llm.base_url,
        "llm_model": config.llm.model,
        "llm_api_key_set": bool(config.llm.api_key.strip()),
        "model_options": resolved_model_options(),
        "model_base_urls": resolved_model_base_urls(),
        "model_extra_args": config.llm.model_extra_args,
        "default_agent_models": default_agent_models(),
        "llm_connect_timeout": config.llm.connect_timeout,
        "llm_read_timeout": config.llm.read_timeout,
        "search_provider": config.search.provider,
        "searxng_url": config.search.searxng_url,
        "tavily_api_key_set": bool(config.search.tavily_api_key.strip()),
        "min_allocated_capital": config.capital_allocation.min_allocated_capital,
        "max_cash_weight": 1.0 - config.capital_allocation.min_allocated_capital,
        "max_drawdown": config.capital_allocation.max_drawdown,
        "cash_yield_annual_pct": config.capital_allocation.cash_yield_annual_pct,
    }


SEARCH_PROVIDERS = ("tavily", "searxng")


@router.get("/api/config")
async def get_config():
    return _config_payload()


@router.post("/api/config")
async def update_config(body: ConfigUpdateBody):
    """Persist UI-managed model, search, and capital-policy settings and apply them."""
    if body.llm_base_url:
        _validate_base_url(body.llm_base_url.strip(), "Endpoint")
    if body.searxng_url and body.searxng_url.strip():
        _validate_base_url(body.searxng_url.strip(), "SearXNG")
    if body.search_provider is not None and body.search_provider not in SEARCH_PROVIDERS:
        raise HTTPException(
            status_code=400, detail=f"Unknown search provider: {body.search_provider!r}"
        )
    if body.agent_models:
        unknown = sorted(set(body.agent_models) - AGENT_MODEL_KEYS)
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
                _validate_base_url(url.strip(), f"Endpoint for {model_name}")
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
    return _config_payload()


@router.delete("/api/config")
async def reset_config():
    """Restore defaults: drop all UI-managed overrides from config.local.toml."""
    try:
        clear_ui_overrides()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not restore defaults: {exc}") from exc
    return _config_payload()


def _llm_chat_completions_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/chat/completions"


_BASE_URL_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)


def _validate_base_url(url: str, label: str) -> None:
    if not _BASE_URL_SCHEME_RE.match(url):
        raise HTTPException(
            status_code=400,
            detail=f"{label} API URL must start with http:// or https:// (got {url!r})",
        )


async def _probe_llm_endpoint(
    *, base_url: str, model: str, api_key: str | None, label: str
) -> None:
    """Send a tiny chat completion to confirm the endpoint accepts the model. Raises on failure."""
    _validate_base_url(base_url, label)
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
        raise HTTPException(
            status_code=502, detail=f"{label} connection failed: {exc}"
        ) from exc

    if response.status_code >= 400:
        detail = (
            response.text.strip()[: config.truncation.error_detail_chars] or response.reason_phrase
        )
        raise HTTPException(
            status_code=502,
            detail=f"{label} returned HTTP {response.status_code}: {detail}",
        )
    try:
        response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502, detail=f"{label} test message did not return JSON"
        ) from exc


@router.post("/api/config/test")
async def test_llm_config(body: LLMConfigBody):
    base_url = (body.llm_base_url or config.llm.base_url).strip()
    model = (body.llm_model or config.llm.model).strip()
    api_key = body.llm_api_key if body.llm_api_key is not None else config.llm.api_key

    if not base_url:
        raise HTTPException(status_code=400, detail="API URL is required")
    if not model:
        raise HTTPException(status_code=400, detail="Model name is required")

    await _probe_llm_endpoint(base_url=base_url, model=model, api_key=api_key, label="Endpoint")

    return {"ok": True, "message": "Endpoint reachable.", "model": model}


def _short_error(exc: Exception) -> str:
    return str(exc).strip()[: config.truncation.error_detail_chars] or exc.__class__.__name__


async def _probe_searxng(base_url: str) -> dict:
    """Confirm a SearXNG instance answers the JSON ``/search`` API. Returns a status dict."""
    if not _BASE_URL_SCHEME_RE.match(base_url):
        return {"ok": False, "message": "SearXNG URL must start with http:// or https://."}
    url = f"{base_url.rstrip('/')}/search"
    params = {"q": "market", "format": "json", "categories": "news"}
    headers = {"User-Agent": config.search.user_agent, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            timeout=config.search.request_timeout_seconds, trust_env=False
        ) as client:
            response = await client.get(url, params=params, headers=headers)
    except httpx.RequestError as exc:
        return {"ok": False, "message": f"SearXNG unreachable: {_short_error(exc)}"}
    if response.status_code >= 400:
        return {"ok": False, "message": f"SearXNG returned HTTP {response.status_code}."}
    try:
        response.json()
    except ValueError:
        return {"ok": False, "message": "SearXNG did not return JSON (enable the JSON format)."}
    return {"ok": True, "message": "SearXNG reachable."}


async def _probe_tavily(api_key: str) -> dict:
    """Make one tiny live Tavily search to confirm the key works. Returns a status dict."""
    from tavily import TavilyClient

    def call() -> None:
        TavilyClient(api_key=api_key).search("market news", max_results=1, topic="news")

    try:
        await asyncio.wait_for(
            asyncio.to_thread(call), timeout=config.search.request_timeout_seconds
        )
    except Exception as exc:
        return {"ok": False, "message": f"Tavily key rejected: {_short_error(exc)}"}
    return {"ok": True, "message": "Tavily key OK."}


@router.post("/api/config/search/test")
async def test_search_config(body: SearchConfigBody):
    """Probe the selected provider only — a live Tavily call or a SearXNG ping. Fields omitted
    from the body (including the provider) fall back to the saved config."""
    provider = (body.search_provider or config.search.provider).strip()

    if provider == "tavily":
        api_key = (
            body.tavily_api_key if body.tavily_api_key is not None else config.search.tavily_api_key
        ).strip()
        if not api_key:
            raise HTTPException(status_code=400, detail="Set a Tavily API key to test.")
        result = await _probe_tavily(api_key)
    elif provider == "searxng":
        searxng_url = (
            body.searxng_url if body.searxng_url is not None else config.search.searxng_url
        ).strip()
        if not searxng_url:
            raise HTTPException(status_code=400, detail="Set a SearXNG URL to test.")
        result = await _probe_searxng(searxng_url)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown search provider: {provider!r}")

    if not result["ok"]:
        raise HTTPException(status_code=502, detail=result["message"])
    return {"ok": True, "message": result["message"]}


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


@router.get("/api/market/profile/{ticker}")
async def market_profile(ticker: str):
    clean = ticker.strip().upper()
    if not clean or not _TICKER_RE.match(clean):
        raise HTTPException(status_code=400, detail="Invalid ticker")
    try:
        profile = await asyncio.to_thread(fetch_ticker_profile, clean)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Profile unavailable for {clean}") from exc
    return profile.model_dump()


@router.post("/api/review/start")
async def start_review(req: StartRequest):
    try:
        portfolio = Portfolio(**req.portfolio)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    portfolio = await _enrich_portfolio_actions(portfolio, req.portfolio)
    clear_port_log_files()
    review_id = str(uuid.uuid4())
    session = ReviewSession(
        review_id,
        portfolio,
        llm_overrides=llm_overrides_from_body(req.llm),
        locale=req.locale or DEFAULT_LOCALE,
        inherited_feedback=[
            item.model_dump(mode="json") for item in req.inherited_feedback
        ],
        on_terminal=_persist_and_evict_review,
    )
    _reviews[review_id] = session
    session.start()
    event_log.info("review_created review_id=%s", review_id)
    return {"review_id": review_id}


@router.post("/api/reviews/feedback-candidates")
async def get_feedback_candidates(body: FeedbackCandidateRequest):
    try:
        portfolio = Portfolio(**body.portfolio)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    match = latest_matching_feedback(portfolio.model_dump(mode="json"))
    return {"match": match}


def _serialise(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {key: _serialise(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_serialise(item) for item in obj]
    if isinstance(obj, date):
        return obj.isoformat()
    return obj


def _latest_required(items: Any, label: str) -> Any:
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=409, detail=f"Review is missing {label}.")
    return items[-1]


def _feedback_payload_for_review(review_id: str) -> dict[str, Any]:
    session = _reviews.get(review_id)
    if session:
        if session.status != "done":
            raise HTTPException(status_code=409, detail="Review must be complete before feedback.")
        return review_result_payload(session)
    stored = load_review_result(review_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Review not found")
    if stored.get("status") != "done":
        raise HTTPException(status_code=409, detail="Review must be complete before feedback.")
    return stored


def _state_from_review_payload(payload: dict[str, Any]) -> dict[str, Any]:
    final_state = payload.get("final_state")
    if not isinstance(final_state, dict):
        raise HTTPException(status_code=409, detail="Review is missing final state.")
    try:
        return {
            "portfolio": Portfolio.model_validate(final_state.get("portfolio")),
            "requested_locale": normalize_locale(
                payload.get("requested_locale") or final_state.get("requested_locale")
            ),
            "inherited_feedback": final_state.get("inherited_feedback")
            or payload.get("inherited_feedback")
            or [],
            "news_focus": final_state.get("news_focus"),
            "market_data": final_state.get("market_data"),
            "news_research_text": final_state.get("news_research_text"),
            "news_research_query_count": final_state.get("news_research_query_count"),
            "news_review": NewsReview.model_validate(final_state.get("news_review")),
            "risk_results": [
                RiskReview.model_validate(
                    _latest_required(final_state.get("risk_results"), "risk results")
                )
            ],
            "regime_results": [
                RegimeReview.model_validate(
                    _latest_required(final_state.get("regime_results"), "regime results")
                )
            ],
            "theme_results": [
                ThemeReview.model_validate(
                    _latest_required(final_state.get("theme_results"), "theme results")
                )
            ],
            "allocation_results": [
                AllocationReview.model_validate(
                    _latest_required(final_state.get("allocation_results"), "allocation results")
                )
            ],
            "validation_review": ValidationReview.model_validate(
                final_state.get("validation_review")
            ),
            "validation_needs_more": False,
            "validation_missing_inputs": [],
            "validation_request_note": final_state.get("validation_request_note"),
            "validation_retry_count": final_state.get("validation_retry_count") or 0,
            "manager_review": None,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Review does not contain complete manager rerun inputs: {exc}",
        ) from exc


def _set_latest_manager_review(payload: dict[str, Any], manager_review: ManagerReview) -> None:
    manager_payload = manager_review.model_dump(mode="json")
    final_state = payload.setdefault("final_state", {})
    if isinstance(final_state, dict):
        final_state["manager_review"] = manager_payload
    agent_outputs = payload.setdefault("agent_outputs", {})
    if isinstance(agent_outputs, dict):
        manager_output = agent_outputs.get("manager")
        if not isinstance(manager_output, dict):
            manager_output = {}
        manager_output["manager_review"] = manager_payload
        agent_outputs["manager"] = manager_output
    updated_at = payload.setdefault("agent_output_updated_at", {})
    if isinstance(updated_at, dict):
        updated_at["manager"] = datetime.now(UTC).isoformat()


@router.post("/api/review/{review_id}/feedback")
async def submit_review_feedback(review_id: str, body: FeedbackRerunBody):
    comment = body.comment.strip()
    if not comment:
        raise HTTPException(status_code=400, detail="Feedback comment is required.")

    payload = _feedback_payload_for_review(review_id)
    rounds = payload.setdefault("feedback_rounds", [])
    if not isinstance(rounds, list):
        rounds = []
        payload["feedback_rounds"] = rounds

    round_ = {
        "round_id": str(uuid.uuid4()),
        "submitted_at": datetime.now(UTC).isoformat(),
        "user_comment": comment,
        "status": "running",
    }
    rounds.append(round_)
    save_review_payload(payload)

    try:
        state = _state_from_review_payload(payload)
        human_msg = build_manager_feedback_human_message(
            state,
            user_comment=comment,
            previous_rounds=rounds[:-1],
        )
        locale_state = LocaleRuntimeState(
            requested_locale=normalize_locale(payload.get("requested_locale")),
            content_locale=normalize_locale(payload.get("content_locale")),
            translation_fallback_used=bool(payload.get("translation_fallback_used")),
        )
        token = locale_runtime_state.set(locale_state)
        try:
            manager_review = await asyncio.to_thread(run_manager_review, state, human_msg)
        finally:
            locale_runtime_state.reset(token)
    except Exception as exc:
        round_["status"] = "error"
        round_["error"] = _short_error(exc)
        payload["saved_at"] = datetime.now(UTC).isoformat()
        save_review_payload(payload)
        return payload

    round_["status"] = "done"
    round_["manager_review"] = manager_review.model_dump(mode="json")
    _set_latest_manager_review(payload, manager_review)
    payload["saved_at"] = datetime.now(UTC).isoformat()
    save_review_payload(payload)
    return payload


@router.get("/api/reviews")
async def get_review_summaries(limit: int = 30):
    clean_limit = max(1, min(limit, 100))
    live = [
        {
            "review_id": session.review_id,
            "status": session.status,
            "portfolio_name": session.portfolio.name,
            "saved_at": "",
            "requested_locale": session.locale_state.requested_locale,
            "content_locale": session.locale_state.content_locale,
            "translation_fallback_used": session.locale_state.translation_fallback_used,
            "preview": "",
        }
        for session in _reviews.values()
        if session.status not in {"done", "error", "stopped"}
    ]
    return {"reviews": (live + list_review_summaries(limit=clean_limit))[:clean_limit]}


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
    if session:
        return review_result_payload(session)
    stored = load_review_result(review_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return stored


@router.get("/api/review/{review_id}/track-record")
async def get_track_record(review_id: str):
    session = _reviews.get(review_id)
    payload = review_result_payload(session) if session else load_review_result(review_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Review not found")
    if payload.get("status") != "done":
        raise HTTPException(status_code=409, detail="Review is not complete")
    try:
        review = compute_track_record(payload)
    except Exception as exc:
        event_log.warning("track record failed for review %s: %s", review_id, exc)
        raise HTTPException(
            status_code=502, detail=f"Could not compute track record: {exc}"
        ) from exc
    return review.model_dump(mode="json")


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
    if session:
        return _session_snapshot(session)
    stored = load_review_result(review_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return {
        "status": stored.get("status"),
        "agent_outputs": stored.get("agent_outputs") or {},
        "agent_output_updated_at": stored.get("agent_output_updated_at") or {},
        "requested_locale": stored.get("requested_locale"),
        "content_locale": stored.get("content_locale"),
        "translation_fallback_used": bool(stored.get("translation_fallback_used")),
        "last_error": stored.get("last_error"),
    }


def _session_snapshot(session: ReviewSession) -> dict:
    return {
        "status": session.status,
        "agent_outputs": session.agent_outputs,
        "agent_output_updated_at": session.agent_output_updated_at,
        "requested_locale": session.locale_state.requested_locale,
        "content_locale": session.locale_state.content_locale,
        "translation_fallback_used": session.locale_state.translation_fallback_used,
        "last_error": session.last_error_event,
    }
