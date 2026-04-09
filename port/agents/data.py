"""Data agent — fetches live prices and headlines via Yahoo Finance (no LLM call)."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import yfinance as yf

from port.config import step_callback as _step_cb
from port.market_data import fetch_position_snapshot
from port.models import MarketData, MarketIndicator, PositionSnapshot

if TYPE_CHECKING:
    from port.state import GraphState

log = logging.getLogger(__name__)

# Planner may request a subset; empty request → fetch all rows.
MACRO_INDICATOR_ROWS: list[tuple[str, str]] = [
    ("SPY", "S&P 500"),
    ("QQQ", "Nasdaq 100"),
    ("IWM", "Russell 2000"),
    ("TLT", "20Y Treasury"),
    ("HYG", "High Yield Credit"),
    ("GLD", "Gold"),
    ("^VIX", "VIX"),
    ("UUP", "US Dollar"),
]

_VALID_MACRO_TICKERS: frozenset[str] = frozenset(t for t, _ in MACRO_INDICATOR_ROWS)


def canonical_macro_indicator_ticker(raw: str) -> str | None:
    """Normalise planner / UI input to a key in MACRO_INDICATOR_ROWS."""
    s = (raw or "").strip().upper()
    if s in ("VIX", "^VIX"):
        return "^VIX"
    if s in _VALID_MACRO_TICKERS:
        return s
    return None


def macro_indicator_rows_for_focus(focus) -> list[tuple[str, str]]:
    """Rows to fetch for macro indicators.

    Returns the full configured list when focus is missing or has no valid tickers.
    """
    if focus is None or not getattr(focus, "macro_indicator_tickers", None):
        return list(MACRO_INDICATOR_ROWS)
    by_ticker = dict(MACRO_INDICATOR_ROWS)
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw in focus.macro_indicator_tickers:
        c = canonical_macro_indicator_ticker(str(raw))
        if c and c not in seen:
            seen.add(c)
            out.append((c, by_ticker[c]))
    return out if out else list(MACRO_INDICATOR_ROWS)


def _safe_pct(new: float, old: float) -> float:
    if not old or old != old or new != new:
        return 0.0
    return round((new - old) / old * 100, 2)


def _fetch_indicator(ticker: str, label: str) -> MarketIndicator | None:
    try:
        hist = yf.Ticker(ticker).history(period="35d", interval="1d", auto_adjust=True)
        if hist.empty or len(hist) < 2:
            return None
        close = hist["Close"]
        n = len(close)
        current = float(close.iloc[-1])
        prev = float(close.iloc[-2])
        price_1m = float(close.iloc[max(-22, -n)])
        return MarketIndicator(
            ticker=ticker,
            label=label,
            current=round(current, 2),
            change_1d_pct=_safe_pct(current, prev),
            change_1m_pct=_safe_pct(current, price_1m),
        )
    except Exception as exc:
        log.warning("indicator fetch failed for %s: %s", ticker, exc)
        return None


def data_node(state: GraphState) -> dict:
    """Fetch live market data in parallel; no LLM call."""
    t0 = time.monotonic()
    portfolio = state["portfolio"]
    position_tickers = [p.ticker for p in portfolio.positions]
    indicator_rows = macro_indicator_rows_for_focus(state.get("news_focus"))
    log.info(
        "started — fetching %d positions + %d indicators",
        len(position_tickers),
        len(indicator_rows),
    )

    errors: list[str] = []
    snapshots: dict[str, PositionSnapshot] = {}
    indicators: list[MarketIndicator] = []

    cb = _step_cb.get(None)
    if cb:
        cb(
            "data",
            0,
            f"Fetching {len(position_tickers)} symbols + {len(indicator_rows)} macro indicators…",
        )

    with ThreadPoolExecutor(max_workers=12) as pool:
        pos_futures = {pool.submit(fetch_position_snapshot, t): t for t in position_tickers}
        ind_futures = {
            pool.submit(_fetch_indicator, ticker, label): ticker for ticker, label in indicator_rows
        }

        for fut in as_completed(pos_futures):
            t = pos_futures[fut]
            result = fut.result()
            if result:
                snapshots[t] = result
            else:
                errors.append(t)

        ind_results: dict[str, MarketIndicator] = {}
        for fut in as_completed(ind_futures):
            t = ind_futures[fut]
            result = fut.result()
            if result:
                ind_results[t] = result

    # Preserve portfolio order for positions
    positions = [snapshots[t] for t in position_tickers if t in snapshots]

    for ticker, _ in indicator_rows:
        if ticker in ind_results:
            indicators.append(ind_results[ticker])

    log.info(
        "done in %.1fs — %d/%d positions fetched, %d indicators, %d errors",
        time.monotonic() - t0,
        len(positions),
        len(position_tickers),
        len(indicators),
        len(errors),
    )
    return {
        "market_data": MarketData(
            positions=positions,
            indicators=indicators,
            fetched_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
            errors=errors,
        )
    }
