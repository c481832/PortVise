from __future__ import annotations

import asyncio
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from advisor.config import config
from advisor.graph import build_graph, make_initial_state
from advisor.llm.client import llm_overrides_from_config, llm_runtime_overrides
from advisor.llm.context import review_stop_event, step_callback
from advisor.market_data import fetch_corporate_actions
from advisor.schemas.portfolio import Portfolio, Position
from advisor.schemas.runner import ReviewRequest, ReviewResult
from advisor.util import serialise

ProgressEvent = dict[str, Any]
ProgressCallback = Callable[[ProgressEvent], None]


class GraphTimeoutError(RuntimeError):
    """Graph/provider timeout raised before the runner's configured deadline."""


def emit_progress(
    callback: ProgressCallback | None,
    *,
    started_monotonic: float,
    **event: Any,
) -> None:
    if callback is None:
        return
    payload = {
        "ts": datetime.now(UTC).isoformat(),
        "elapsed_seconds": max(0.0, time.monotonic() - started_monotonic),
        **event,
    }
    callback(payload)


def needs_corporate_action_fetch(position: Position) -> bool:
    return position.dividend == 0.0 and position.split == 1.0


def corporate_action_fetch_timeout(deadline: float | None) -> float:
    timeout = config.market.yfinance_timeout_seconds
    if deadline is None:
        return timeout
    remaining = deadline - asyncio.get_running_loop().time()
    if remaining <= 0:
        raise TimeoutError
    return min(timeout, remaining)


async def enrich_portfolio(
    portfolio: Portfolio,
    mode: str,
    warnings: list[str],
    deadline: float | None,
    progress_callback: ProgressCallback | None,
    started_monotonic: float,
) -> Portfolio:
    if mode == "off":
        return portfolio

    emit_progress(
        progress_callback,
        started_monotonic=started_monotonic,
        type="corporate_actions_start",
        label="Fetching corporate actions...",
    )
    enriched: list[Position] = []
    for position in portfolio.positions:
        if not needs_corporate_action_fetch(position):
            enriched.append(position)
            continue
        emit_progress(
            progress_callback,
            started_monotonic=started_monotonic,
            type="corporate_actions_step",
            agent="data",
            label=f"Fetching corporate actions for {position.ticker}...",
        )
        fetch_timeout = corporate_action_fetch_timeout(deadline)
        try:
            dividend, split = await asyncio.to_thread(
                fetch_corporate_actions,
                position.ticker,
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

    emit_progress(
        progress_callback,
        started_monotonic=started_monotonic,
        type="corporate_actions_done",
        label="Corporate action enrichment complete.",
    )
    return portfolio.model_copy(update={"positions": enriched})


def result_from_state(
    *,
    review_id: str,
    status: str,
    started_at: str,
    warnings: list[str],
    final_state: dict[str, Any] | None,
    error: str | None,
) -> ReviewResult:
    state = final_state or {}
    return ReviewResult(
        review_id=review_id,
        status=status,  # type: ignore[arg-type]
        started_at=started_at,
        finished_at=datetime.now(UTC).isoformat(),
        warnings=warnings,
        error=error,
        manager_review=state.get("manager_review"),
        risk_review=state.get("risk_review"),
        regime_review=state.get("regime_review"),
        theme_review=state.get("theme_review"),
        allocation_review=state.get("allocation_review"),
        news_review=state.get("news_review"),
        market_data=state.get("market_data"),
        final_state=serialise(state) if state else None,
    )


async def run_review(
    request: ReviewRequest | dict[str, Any],
    *,
    progress_callback: ProgressCallback | None,
) -> ReviewResult:
    """Run the Portfolio Advisor graph directly for a local agent caller."""
    req = request if isinstance(request, ReviewRequest) else ReviewRequest(**request)
    review_id = str(uuid.uuid4())
    started_at = datetime.now(UTC).isoformat()
    warnings: list[str] = []
    stop_event = threading.Event()
    loop = asyncio.get_running_loop()
    started_monotonic = time.monotonic()
    deadline = loop.time() + req.timeout_seconds if req.timeout_seconds else None
    emit_progress(
        progress_callback,
        started_monotonic=started_monotonic,
        type="review_start",
        review_id=review_id,
        label="Review started.",
    )

    async def run_pipeline() -> dict[str, Any]:
        emit_progress(
            progress_callback,
            started_monotonic=started_monotonic,
            type="graph_start",
            review_id=review_id,
            label="Starting review graph...",
        )
        portfolio = await enrich_portfolio(
            req.portfolio,
            req.corporate_actions,
            warnings,
            deadline,
            progress_callback,
            started_monotonic,
        )
        graph = build_graph()
        config = {"configurable": {"thread_id": review_id}}
        initial_state = make_initial_state(portfolio, inherited_feedback=None)
        try:
            return await graph.ainvoke(initial_state, config)  # type: ignore[arg-type]
        except TimeoutError as exc:
            raise GraphTimeoutError(str(exc)) from exc

    llm_overrides = llm_overrides_from_config(req.llm)

    def step_sync(agent: str, step_index: int, label: str) -> None:
        emit_progress(
            progress_callback,
            started_monotonic=started_monotonic,
            type="agent_step",
            review_id=review_id,
            agent=agent,
            step_index=step_index,
            label=label,
        )

    stop_token = review_stop_event.set(stop_event)
    step_token = step_callback.set(step_sync)
    llm_token = None
    if llm_overrides is not None:
        llm_token = llm_runtime_overrides.set(llm_overrides)
    try:
        try:
            if req.timeout_seconds:
                final_state = await asyncio.wait_for(
                    run_pipeline(),
                    timeout=req.timeout_seconds,
                )
            else:
                final_state = await run_pipeline()
        except TimeoutError:
            stop_event.set()
            error = f"Review timed out after {req.timeout_seconds} seconds."
            emit_progress(
                progress_callback,
                started_monotonic=started_monotonic,
                type="review_timeout",
                review_id=review_id,
                label=error,
                error=error,
            )
            return result_from_state(
                review_id=review_id,
                status="timeout",
                started_at=started_at,
                warnings=warnings,
                final_state=None,
                error=error,
            )
        except Exception as exc:
            emit_progress(
                progress_callback,
                started_monotonic=started_monotonic,
                type="review_error",
                review_id=review_id,
                label=str(exc),
                error=str(exc),
            )
            return result_from_state(
                review_id=review_id,
                status="error",
                started_at=started_at,
                warnings=warnings,
                final_state=None,
                error=str(exc),
            )
    finally:
        if llm_token is not None:
            llm_runtime_overrides.reset(llm_token)
        step_callback.reset(step_token)
        review_stop_event.reset(stop_token)
        stop_event.set()

    emit_progress(
        progress_callback,
        started_monotonic=started_monotonic,
        type="review_done",
        review_id=review_id,
        label="Review complete.",
    )
    return result_from_state(
        review_id=review_id,
        status="done",
        started_at=started_at,
        warnings=warnings,
        final_state=final_state,
        error=None,
    )
