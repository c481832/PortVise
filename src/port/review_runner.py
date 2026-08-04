from __future__ import annotations

import asyncio
import contextlib
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from port.agent_api_models import AgentLLMConfig, AgentReviewRequest, AgentReviewResult
from port.config import (
    LLMOverrides,
    freeze_agent_models,
    llm_runtime_overrides,
    locale_runtime_state,
    review_stop_event,
    step_callback,
)
from port.graph import build_graph, make_initial_state
from port.i18n import DEFAULT_LOCALE, LocaleRuntimeState, normalize_locale
from port.market_data import fetch_corporate_actions
from port.portfolio import Portfolio, Position

CORPORATE_ACTION_FETCH_TIMEOUT_SECONDS = 10.0
ProgressEvent = dict[str, Any]
ProgressCallback = Callable[[ProgressEvent], None]


class _GraphTimeoutError(RuntimeError):
    """Graph/provider timeout raised before the runner's configured deadline."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _emit_progress(
    callback: ProgressCallback | None,
    *,
    started_monotonic: float,
    **event: Any,
) -> None:
    if callback is None:
        return
    payload = {
        "ts": _now_iso(),
        "elapsed_seconds": max(0.0, time.monotonic() - started_monotonic),
        **event,
    }
    with contextlib.suppress(Exception):
        callback(payload)


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


def _llm_overrides_from_agent_config(body: AgentLLMConfig | None) -> LLMOverrides | None:
    if body is None:
        return None
    agent_models = freeze_agent_models(body.agent_models)
    has_overrides = any(
        value is not None
        for value in (body.llm_base_url, body.llm_model, body.llm_api_key)
    )
    if not has_overrides and not agent_models:
        return None
    return LLMOverrides(
        llm_base_url=body.llm_base_url,
        llm_model=body.llm_model,
        llm_api_key=body.llm_api_key,
        agent_models=agent_models,
    )


def _needs_corporate_action_fetch(position: Position) -> bool:
    return position.dividend == 0.0 and position.split == 1.0


def _corporate_action_fetch_timeout(deadline: float | None) -> float:
    if deadline is None:
        return CORPORATE_ACTION_FETCH_TIMEOUT_SECONDS
    remaining = deadline - asyncio.get_running_loop().time()
    if remaining <= 0:
        raise TimeoutError
    return min(CORPORATE_ACTION_FETCH_TIMEOUT_SECONDS, remaining)


async def _enrich_portfolio(
    portfolio: Portfolio,
    mode: str,
    warnings: list[str],
    deadline: float | None,
    progress_callback: ProgressCallback | None,
    started_monotonic: float,
) -> Portfolio:
    if mode == "off":
        return portfolio

    _emit_progress(
        progress_callback,
        started_monotonic=started_monotonic,
        type="corporate_actions_start",
        label="Fetching corporate actions...",
    )
    enriched: list[Position] = []
    for position in portfolio.positions:
        if not _needs_corporate_action_fetch(position):
            enriched.append(position)
            continue
        _emit_progress(
            progress_callback,
            started_monotonic=started_monotonic,
            type="corporate_actions_step",
            agent="data",
            label=f"Fetching corporate actions for {position.ticker}...",
        )
        fetch_timeout = _corporate_action_fetch_timeout(deadline)
        try:
            dividend, split = await asyncio.to_thread(
                fetch_corporate_actions,
                position.ticker,
                position.entry_date,
                timeout=fetch_timeout,
            )
        except Exception as exc:
            message = f"Corporate action fetch failed for {position.ticker}: {exc}"
            if mode == "strict":
                raise RuntimeError(message) from exc
            warnings.append(message)
            enriched.append(position)
            continue
        enriched.append(position.model_copy(update={"dividend": dividend, "split": split}))

    _emit_progress(
        progress_callback,
        started_monotonic=started_monotonic,
        type="corporate_actions_done",
        label="Corporate action enrichment complete.",
    )
    return portfolio.model_copy(update={"positions": enriched})


def _latest(items: list[Any] | None) -> Any | None:
    return items[-1] if items else None


def _result_from_state(
    *,
    review_id: str,
    status: str,
    started_at: str,
    locale_state: LocaleRuntimeState,
    warnings: list[str],
    final_state: dict[str, Any] | None,
    error: str | None = None,
) -> AgentReviewResult:
    state = final_state or {}
    return AgentReviewResult(
        review_id=review_id,
        status=status,  # type: ignore[arg-type]
        started_at=started_at,
        finished_at=_now_iso(),
        requested_locale=locale_state.requested_locale,
        content_locale=locale_state.content_locale,
        translation_fallback_used=locale_state.translation_fallback_used,
        warnings=warnings,
        error=error,
        manager_review=state.get("manager_review"),
        validation_review=state.get("validation_review"),
        risk_review=_latest(state.get("risk_results")),
        regime_review=_latest(state.get("regime_results")),
        theme_review=_latest(state.get("theme_results")),
        allocation_review=_latest(state.get("allocation_results")),
        news_review=state.get("news_review"),
        market_data=state.get("market_data"),
        final_state=_serialise(state) if state else None,
    )


async def run_review(
    request: AgentReviewRequest | dict[str, Any],
    *,
    progress_callback: ProgressCallback | None = None,
) -> AgentReviewResult:
    """Run the Portfolio Advisor graph directly for a local agent caller."""
    req = request if isinstance(request, AgentReviewRequest) else AgentReviewRequest(**request)
    review_id = str(uuid.uuid4())
    started_at = _now_iso()
    warnings: list[str] = []
    resolved_locale = normalize_locale(req.locale or DEFAULT_LOCALE)
    locale_state = LocaleRuntimeState(
        requested_locale=resolved_locale,
        content_locale=resolved_locale,
    )
    stop_event = threading.Event()
    loop = asyncio.get_running_loop()
    started_monotonic = time.monotonic()
    deadline = loop.time() + req.timeout_seconds if req.timeout_seconds else None
    _emit_progress(
        progress_callback,
        started_monotonic=started_monotonic,
        type="review_start",
        review_id=review_id,
        label="Review started.",
    )

    async def _run_pipeline() -> dict[str, Any]:
        _emit_progress(
            progress_callback,
            started_monotonic=started_monotonic,
            type="graph_start",
            review_id=review_id,
            label="Starting review graph...",
        )
        portfolio = await _enrich_portfolio(
            req.portfolio,
            req.corporate_actions,
            warnings,
            deadline,
            progress_callback,
            started_monotonic,
        )
        graph = build_graph()
        config = {"configurable": {"thread_id": review_id}}
        initial_state = make_initial_state(portfolio, requested_locale=resolved_locale)
        try:
            return await graph.ainvoke(initial_state, config)  # type: ignore[arg-type]
        except TimeoutError as exc:
            raise _GraphTimeoutError(str(exc)) from exc

    llm_overrides = _llm_overrides_from_agent_config(req.llm)

    def _step_sync(agent: str, step_index: int, label: str) -> None:
        _emit_progress(
            progress_callback,
            started_monotonic=started_monotonic,
            type="agent_step",
            review_id=review_id,
            agent=agent,
            step_index=step_index,
            label=label,
        )

    locale_token = locale_runtime_state.set(locale_state)
    stop_token = review_stop_event.set(stop_event)
    step_token = step_callback.set(_step_sync)
    llm_token = None
    if llm_overrides is not None:
        llm_token = llm_runtime_overrides.set(llm_overrides)
    try:
        try:
            if req.timeout_seconds:
                final_state = await asyncio.wait_for(
                    _run_pipeline(),
                    timeout=req.timeout_seconds,
                )
            else:
                final_state = await _run_pipeline()
        except TimeoutError:
            stop_event.set()
            error = f"Review timed out after {req.timeout_seconds} seconds."
            _emit_progress(
                progress_callback,
                started_monotonic=started_monotonic,
                type="review_timeout",
                review_id=review_id,
                label=error,
                error=error,
            )
            return _result_from_state(
                review_id=review_id,
                status="timeout",
                started_at=started_at,
                locale_state=locale_state,
                warnings=warnings,
                final_state=None,
                error=error,
            )
        except Exception as exc:
            _emit_progress(
                progress_callback,
                started_monotonic=started_monotonic,
                type="review_error",
                review_id=review_id,
                label=str(exc),
                error=str(exc),
            )
            return _result_from_state(
                review_id=review_id,
                status="error",
                started_at=started_at,
                locale_state=locale_state,
                warnings=warnings,
                final_state=None,
                error=str(exc),
            )
    finally:
        if llm_token is not None:
            llm_runtime_overrides.reset(llm_token)
        step_callback.reset(step_token)
        review_stop_event.reset(stop_token)
        locale_runtime_state.reset(locale_token)
        with contextlib.suppress(Exception):
            stop_event.set()

    _emit_progress(
        progress_callback,
        started_monotonic=started_monotonic,
        type="review_done",
        review_id=review_id,
        label="Review complete.",
    )
    return _result_from_state(
        review_id=review_id,
        status="done",
        started_at=started_at,
        locale_state=locale_state,
        warnings=warnings,
        final_state=final_state,
    )
