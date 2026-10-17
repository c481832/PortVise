from __future__ import annotations

import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any

from advisor.config import config
from advisor.llm.context import report_step
from advisor.market_data import fetch_indicator, fetch_position_snapshot, fetch_risk_factor_history
from advisor.quant.risk import list_factor_tickers
from advisor.schemas.market import MarketData, MarketIndicator, PositionSnapshot
from advisor.schemas.state import GraphState

log = logging.getLogger(__name__)


def format_progress_items(items: list[str], *, limit: int) -> str:
    if not items:
        return "none"
    shown = items[:limit]
    suffix = f", +{len(items) - limit} more" if len(items) > limit else ""
    return ", ".join(shown) + suffix


def format_indicator_label(ticker: str, label: str) -> str:
    return ticker if label == ticker else f"{ticker} ({label})"


def format_risk_factor_label(ticker: str, factors: tuple[str, ...]) -> str:
    if not factors:
        return ticker
    prefix = "factor" if len(factors) == 1 else "factors"
    return f"{ticker} ({prefix}: {', '.join(factors)})"


def collect_results(
    futures: dict[Future, str],
    labels: dict[str, str],
    *,
    step_index: int,
    plural: str,
    singular: str,
) -> dict[str, Any]:
    """Wait for one batch of fetches, reporting progress as each ticker completes."""
    total = len(futures)
    queued = format_progress_items(list(labels.values()), limit=8)
    report_step("data", step_index, f"Fetching {plural} 0/{total}: {queued}…")
    results: dict[str, Any] = {}
    for future in as_completed(futures):
        ticker = futures[future]
        results[ticker] = future.result()
        report_step(
            "data", step_index, f"Fetched {singular} {labels[ticker]} {len(results)}/{total}…"
        )
    return results


def data_node(state: GraphState) -> dict:
    t0 = time.monotonic()
    portfolio = state["portfolio"]
    position_labels = {p.ticker: p.ticker for p in portfolio.positions}
    indicator_names = {
        ticker: config.macro.indicator_labels[ticker] for ticker in config.macro.indicator_universe
    }
    indicator_names.setdefault(portfolio.benchmark, portfolio.benchmark)
    indicator_labels = {
        ticker: format_indicator_label(ticker, name) for ticker, name in indicator_names.items()
    }
    already_fetched = set(position_labels) | set(indicator_labels)
    risk_factors_by_ticker: dict[str, list[str]] = {}
    for factor_name, ticker in list_factor_tickers().items():
        if ticker not in already_fetched:
            risk_factors_by_ticker.setdefault(ticker, []).append(factor_name)
    risk_factor_labels = {
        ticker: format_risk_factor_label(ticker, tuple(sorted(factor_names)))
        for ticker, factor_names in sorted(risk_factors_by_ticker.items())
    }

    queued = (
        f"positions: {format_progress_items(list(position_labels), limit=8)}; "
        f"indicators: {format_progress_items(list(indicator_labels.values()), limit=8)}; "
        f"risk factors: {format_progress_items(list(risk_factor_labels.values()), limit=8)}"
    )
    log.info("started — queued %s", queued)
    report_step("data", 0, f"Queued {queued}…")

    with ThreadPoolExecutor(max_workers=config.macro.thread_pool_size) as pool:
        position_futures = {
            pool.submit(fetch_position_snapshot, p.ticker, p.entry_date): p.ticker
            for p in portfolio.positions
        }
        indicator_futures = {
            pool.submit(fetch_indicator, ticker, name): ticker
            for ticker, name in indicator_names.items()
        }
        risk_factor_futures = {
            pool.submit(fetch_risk_factor_history, ticker): ticker for ticker in risk_factor_labels
        }
        snapshots = collect_results(
            position_futures,
            position_labels,
            step_index=1,
            plural="position snapshots",
            singular="position",
        )
        indicator_results = collect_results(
            indicator_futures,
            indicator_labels,
            step_index=2,
            plural="macro indicators",
            singular="macro indicator",
        )
        collect_results(
            risk_factor_futures,
            risk_factor_labels,
            step_index=3,
            plural="risk-factor histories",
            singular="risk-factor history",
        )

    positions: list[PositionSnapshot] = [snapshots[ticker] for ticker in position_labels]
    indicators: list[MarketIndicator] = [indicator_results[ticker] for ticker in indicator_names]
    report_step("data", 4, "Assembling market snapshot…")
    log.info(
        "done in %.1fs — %d positions, %d indicators, %d risk factors",
        time.monotonic() - t0,
        len(positions),
        len(indicators),
        len(risk_factor_labels),
    )
    return {
        "market_data": MarketData(
            positions=positions,
            indicators=indicators,
            fetched_at=datetime.now(UTC).strftime(config.macro.fetched_at_format),
        )
    }
