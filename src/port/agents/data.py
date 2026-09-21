"""Data agent — fetches and persists market history via Yahoo Finance (no LLM call)."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from port.config import config
from port.llm.context import step_callback as _step_cb
from port.market_data import fetch_indicator, fetch_position_snapshot, fetch_risk_factor_history
from port.models.market import MarketData, MarketIndicator, PositionSnapshot

if TYPE_CHECKING:
    from port.state import GraphState

log = logging.getLogger(__name__)


def _format_progress_items(items: list[str], *, limit: int = 8) -> str:
    if not items:
        return "none"
    shown = items[:limit]
    suffix = f", +{len(items) - limit} more" if len(items) > limit else ""
    return ", ".join(shown) + suffix


def _indicator_progress_label(ticker: str, label: str) -> str:
    return ticker if label == ticker else f"{ticker} ({label})"


def _risk_factor_progress_label(ticker: str, factors: tuple[str, ...]) -> str:
    if not factors:
        return ticker
    prefix = "factor" if len(factors) == 1 else "factors"
    return f"{ticker} ({prefix}: {', '.join(factors)})"


def data_node(state: GraphState) -> dict:
    """Fetch live market data in parallel; no LLM call.

    Raises on any Yahoo fetch failure — the regime/risk pipeline requires complete market
    history for positions, indicators, and risk factors.
    """
    t0 = time.monotonic()
    portfolio = state["portfolio"]
    position_rows = [(p.ticker, p.entry_date) for p in portfolio.positions]
    position_tickers = [ticker for ticker, _ in position_rows]
    indicator_rows = [
        (ticker, config.macro.indicator_labels[ticker])
        for ticker in config.macro.indicator_universe
    ]
    if portfolio.benchmark not in {ticker for ticker, _label in indicator_rows}:
        indicator_rows.append((portfolio.benchmark, portfolio.benchmark))
    indicator_labels = {
        ticker: _indicator_progress_label(ticker, label) for ticker, label in indicator_rows
    }
    persisted_by_position_or_indicator = set(position_tickers) | {
        ticker for ticker, _label in indicator_rows
    }
    risk_factors_by_ticker: dict[str, list[str]] = {}
    for factor_name, ticker in config.risk_engine.factor_tickers.items():
        if ticker not in persisted_by_position_or_indicator:
            risk_factors_by_ticker.setdefault(ticker, []).append(factor_name)
    risk_factor_rows = [
        (ticker, tuple(sorted(factor_names)))
        for ticker, factor_names in sorted(risk_factors_by_ticker.items())
    ]
    risk_factor_tickers = [ticker for ticker, _factor_names in risk_factor_rows]
    risk_factor_labels = {
        ticker: _risk_factor_progress_label(ticker, factor_names)
        for ticker, factor_names in risk_factor_rows
    }
    indicator_progress_items = [indicator_labels[ticker] for ticker, _label in indicator_rows]
    risk_factor_progress_items = [risk_factor_labels[ticker] for ticker in risk_factor_tickers]
    log.info(
        "started — fetching %d positions + %d indicators + %d risk factors",
        len(position_tickers),
        len(indicator_rows),
        len(risk_factor_tickers),
    )
    log.info(
        "queued positions=[%s] indicators=[%s] risk_factors=[%s]",
        _format_progress_items(position_tickers),
        _format_progress_items(indicator_progress_items),
        _format_progress_items(risk_factor_progress_items),
    )

    snapshots: dict[str, PositionSnapshot] = {}
    indicators: list[MarketIndicator] = []

    cb = _step_cb.get(None)
    if cb:
        cb(
            "data",
            0,
            (
                f"Queued positions: {_format_progress_items(position_tickers)}; "
                f"indicators: {_format_progress_items(indicator_progress_items)}; "
                f"risk factors: {_format_progress_items(risk_factor_progress_items)}…"
            ),
        )

    with ThreadPoolExecutor(max_workers=config.macro.thread_pool_size) as pool:
        pos_futures = {
            pool.submit(fetch_position_snapshot, ticker, entry_date): ticker
            for ticker, entry_date in position_rows
        }
        ind_futures = {
            pool.submit(fetch_indicator, ticker, label): ticker for ticker, label in indicator_rows
        }
        risk_factor_futures = {
            pool.submit(fetch_risk_factor_history, ticker): ticker
            for ticker, _factor_names in risk_factor_rows
        }

        if cb:
            cb(
                "data",
                1,
                (
                    f"Fetching position snapshots 0/{len(position_tickers)}: "
                    f"{_format_progress_items(position_tickers)}…"
                ),
            )
        for fut in as_completed(pos_futures):
            t = pos_futures[fut]
            snapshots[t] = fut.result()
            if cb:
                cb(
                    "data",
                    1,
                    f"Fetched position {t} {len(snapshots)}/{len(position_tickers)}…",
                )

        ind_results: dict[str, MarketIndicator] = {}
        if cb:
            cb(
                "data",
                2,
                (
                    f"Fetching macro indicators 0/{len(indicator_rows)}: "
                    f"{_format_progress_items(indicator_progress_items)}…"
                ),
            )
        for fut in as_completed(ind_futures):
            t = ind_futures[fut]
            ind_results[t] = fut.result()
            if cb:
                cb(
                    "data",
                    2,
                    (
                        f"Fetched macro indicator {indicator_labels[t]} "
                        f"{len(ind_results)}/{len(indicator_rows)}…"
                    ),
                )

        if cb:
            cb(
                "data",
                3,
                (
                    f"Fetching risk-factor histories 0/{len(risk_factor_tickers)}: "
                    f"{_format_progress_items(risk_factor_progress_items)}…"
                ),
            )
        for risk_factor_done, fut in enumerate(as_completed(risk_factor_futures), start=1):
            ticker = fut.result()
            if cb:
                cb(
                    "data",
                    3,
                    (
                        f"Fetched risk-factor history {risk_factor_labels[ticker]} "
                        f"{risk_factor_done}/{len(risk_factor_tickers)}…"
                    ),
                )

    positions = [snapshots[t] for t in position_tickers]

    for ticker, _ in indicator_rows:
        indicators.append(ind_results[ticker])

    if cb:
        cb("data", 4, "Assembling market snapshot…")

    log.info(
        "done in %.1fs — %d/%d positions fetched, %d indicators, %d risk factors",
        time.monotonic() - t0,
        len(positions),
        len(position_tickers),
        len(indicators),
        len(risk_factor_tickers),
    )
    return {
        "market_data": MarketData(
            positions=positions,
            indicators=indicators,
            fetched_at=datetime.now(UTC).strftime(config.macro.fetched_at_format),
        )
    }
