"""Data agent — fetches and persists market history via Yahoo Finance (no LLM call)."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import yfinance as yf

from port._retry import with_retry
from port.config import config
from port.config import step_callback as _step_cb
from port.market_data import fetch_position_snapshot, save_price_history
from port.models import MarketData, MarketIndicator, PositionSnapshot
from port.yfinance_compat import suppress_yfinance_pandas4_warnings

if TYPE_CHECKING:
    from port.state import GraphState

log = logging.getLogger(__name__)


def _safe_pct(new: float, old: float) -> float:
    if not old or old != old or new != new:
        raise ValueError(f"degenerate inputs for pct change: new={new!r} old={old!r}")
    return round((new - old) / old * 100, 2)


class _EmptyHistory(RuntimeError):
    pass


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


def _fetch_indicator(ticker: str, label: str) -> MarketIndicator:
    """Fetch a single macro indicator. Raises on failure — no silent None return."""
    period = config.macro.lookback_period
    interval = config.macro.interval
    window = config.macro.change_window_days
    max_attempts = config.market.fetch_max_attempts
    base_seconds = config.market.fetch_backoff_base_seconds
    cap_seconds = config.market.fetch_backoff_max_seconds

    def attempt():
        with suppress_yfinance_pandas4_warnings():
            hist = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
        if hist.empty or len(hist) < 2:
            raise _EmptyHistory(f"{ticker} returned <2 rows")
        save_price_history("indicators", ticker, hist)
        return hist

    def log_retry(att: int, exc: Exception, delay: float) -> None:
        level = log.info if isinstance(exc, _EmptyHistory) else log.warning
        level(
            "indicator fetch failed for %s attempt=%d/%d err=%s — retrying in %.1fs",
            ticker,
            att,
            max_attempts,
            exc,
            delay,
        )

    hist = with_retry(
        attempt,
        attempts=max_attempts,
        base=base_seconds,
        cap=cap_seconds,
        on_attempt=log_retry,
    )
    close = hist["Close"]
    n = len(close)
    current = float(close.iloc[-1])
    prev = float(close.iloc[-2])
    price_1w = float(close.iloc[max(-6, -n)])
    price_1m = float(close.iloc[max(-window, -n)])
    price_3m = float(close.iloc[max(-66, -n)])
    idx_1y = max(0, n - 252)
    price_1y = float(close.iloc[idx_1y])
    trailing_year = hist.tail(min(252, n))
    week_52_high = float(trailing_year["High"].max())  # type: ignore[arg-type]
    week_52_low = float(trailing_year["Low"].min())  # type: ignore[arg-type]

    return MarketIndicator(
        ticker=ticker,
        label=label,
        current=round(current, 2),
        prev_close=round(prev, 2),
        change_1d_pct=_safe_pct(current, prev),
        change_1w_pct=_safe_pct(current, price_1w),
        change_1m_pct=_safe_pct(current, price_1m),
        change_3m_pct=_safe_pct(current, price_3m),
        change_1y_pct=_safe_pct(current, price_1y),
        week_52_high=round(week_52_high, 2),
        week_52_low=round(week_52_low, 2),
        pct_from_52w_high=_safe_pct(current, week_52_high),
    )


def _fetch_risk_factor_history(ticker: str) -> str:
    """Fetch and persist a risk-factor price history for later deterministic risk analysis."""
    max_attempts = config.market.fetch_max_attempts
    base_seconds = config.market.fetch_backoff_base_seconds
    cap_seconds = config.market.fetch_backoff_max_seconds

    def attempt():
        with suppress_yfinance_pandas4_warnings():
            hist = yf.Ticker(ticker).history(
                period=config.market.price_history_period,
                interval="1d",
                auto_adjust=True,
            )
        if hist.empty or len(hist) < 2:
            raise _EmptyHistory(f"{ticker} returned <2 rows")
        save_price_history("risk_factors", ticker, hist)
        return ticker

    def log_retry(att: int, exc: Exception, delay: float) -> None:
        level = log.info if isinstance(exc, _EmptyHistory) else log.warning
        level(
            "risk factor history fetch failed for %s attempt=%d/%d err=%s — retrying in %.1fs",
            ticker,
            att,
            max_attempts,
            exc,
            delay,
        )

    return with_retry(
        attempt,
        attempts=max_attempts,
        base=base_seconds,
        cap=cap_seconds,
        on_attempt=log_retry,
    )


def data_node(state: GraphState) -> dict:
    """Fetch live market data in parallel; no LLM call.

    Raises on any indicator fetch failure — the regime/risk pipeline requires complete macro
    context. (Position snapshot failures are still tolerated and surfaced via ``errors``.)
    """
    t0 = time.monotonic()
    portfolio = state["portfolio"]
    position_rows = [(p.ticker, p.entry_date) for p in portfolio.positions]
    position_tickers = [ticker for ticker, _ in position_rows]
    indicator_rows = [
        (ticker, config.macro.indicator_labels[ticker])
        for ticker in config.macro.indicator_universe
    ]
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

    errors: list[str] = []
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
            pool.submit(_fetch_indicator, ticker, label): ticker for ticker, label in indicator_rows
        }
        risk_factor_futures = {
            pool.submit(_fetch_risk_factor_history, ticker): ticker
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
            result = fut.result()
            if result:
                snapshots[t] = result
                status = "Fetched"
            else:
                errors.append(t)
                status = "Missing"
            if cb:
                completed = len(snapshots) + len(errors)
                cb(
                    "data",
                    1,
                    f"{status} position {t} {completed}/{len(position_tickers)}…",
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

    positions = [snapshots[t] for t in position_tickers if t in snapshots]

    for ticker, _ in indicator_rows:
        indicators.append(ind_results[ticker])

    if cb:
        cb("data", 4, "Assembling market snapshot…")

    log.info(
        "done in %.1fs — %d/%d positions fetched, %d indicators, %d risk factors, %d errors",
        time.monotonic() - t0,
        len(positions),
        len(position_tickers),
        len(indicators),
        len(risk_factor_tickers),
        len(errors),
    )
    return {
        "market_data": MarketData(
            positions=positions,
            indicators=indicators,
            fetched_at=datetime.now(UTC).strftime(config.macro.fetched_at_format),
            errors=sorted(set(errors)),
        )
    }
