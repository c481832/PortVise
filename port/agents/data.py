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
    ("GLD", "Gold"),
    ("USO", "Oil (WTI proxy)"),
    ("^TNX", "US 10Y Yield"),
    ("EEM", "Developing Markets Equity"),
    ("EFA", "Developed Markets Equity"),
    ("SPY", "S&P 500"),
    ("QQQ", "Nasdaq 100"),
    ("XLF", "Sector ETF"),
    ("^VIX", "VIX"),
]

_VALID_MACRO_TICKERS: frozenset[str] = frozenset(t for t, _ in MACRO_INDICATOR_ROWS)
_REQUIRED_REGIME_TICKERS: frozenset[str] = frozenset(
    {"^TNX", "SPY", "EEM", "XLF", "GLD", "USO", "^VIX"}
)


def canonical_macro_indicator_ticker(raw: str) -> str | None:
    """Normalise planner / UI input to a key in MACRO_INDICATOR_ROWS."""
    s = (raw or "").strip().upper()
    aliases = {
        "GOLD": "GLD",
        "OIL": "USO",
        "VIX": "^VIX",
        "10Y": "^TNX",
        "10-YEAR YIELD": "^TNX",
        "10 YEAR YIELD": "^TNX",
        "US 10Y YIELD": "^TNX",
        "DEVELOPING MARKET EQUITY INDEX": "EEM",
        "DEVELOPING MARKETS EQUITY INDEX": "EEM",
        "EMERGING MARKET EQUITY INDEX": "EEM",
        "EMERGING MARKETS EQUITY INDEX": "EEM",
        "DEVELOPED MARKET EQUITY INDEX": "EFA",
        "DEVELOPED MARKETS EQUITY INDEX": "EFA",
        "SECTOR ETF": "XLF",
    }
    if s in aliases:
        return aliases[s]
    if s in _VALID_MACRO_TICKERS:
        return s
    return None


def macro_indicator_rows_for_focus(focus) -> list[tuple[str, str]]:
    """Rows to fetch for macro indicators.

    Returns the full configured list when focus is missing or has no valid tickers.
    For non-empty planner subsets, always includes the regime-required indicators.
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
    if not out:
        return list(MACRO_INDICATOR_ROWS)
    # Keep planner-picked order first, then append hard requirements for regime/risk engines.
    for ticker, label in MACRO_INDICATOR_ROWS:
        if ticker in _REQUIRED_REGIME_TICKERS and ticker not in seen:
            out.append((ticker, label))
            seen.add(ticker)
    return out


def _safe_pct(new: float, old: float) -> float:
    if not old or old != old or new != new:
        return 0.0
    return round((new - old) / old * 100, 2)


_INDICATOR_MAX_ATTEMPTS = 3
_INDICATOR_BACKOFF_BASE = 0.75
_INDICATOR_BACKOFF_MAX = 4.0


def _indicator_backoff(attempt: int) -> float:
    return min(_INDICATOR_BACKOFF_BASE * (2 ** max(0, attempt - 1)), _INDICATOR_BACKOFF_MAX)


def _fetch_indicator(ticker: str, label: str) -> MarketIndicator | None:
    last_exc: Exception | None = None
    for attempt in range(1, _INDICATOR_MAX_ATTEMPTS + 1):
        try:
            hist = yf.Ticker(ticker).history(period="35d", interval="1d", auto_adjust=True)
        except Exception as exc:
            last_exc = exc
            if attempt < _INDICATOR_MAX_ATTEMPTS:
                delay = _indicator_backoff(attempt)
                log.warning(
                    "indicator fetch failed for %s attempt=%d/%d err=%s — retrying in %.1fs",
                    ticker,
                    attempt,
                    _INDICATOR_MAX_ATTEMPTS,
                    exc,
                    delay,
                )
                time.sleep(delay)
                continue
            log.warning(
                "indicator fetch failed for %s after %d attempts: %s",
                ticker,
                _INDICATOR_MAX_ATTEMPTS,
                exc,
            )
            return None

        if hist.empty or len(hist) < 2:
            if attempt < _INDICATOR_MAX_ATTEMPTS:
                delay = _indicator_backoff(attempt)
                log.info(
                    "indicator empty history for %s (attempt %d/%d) — retrying in %.1fs",
                    ticker,
                    attempt,
                    _INDICATOR_MAX_ATTEMPTS,
                    delay,
                )
                time.sleep(delay)
                continue
            return None

        try:
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
            log.warning("indicator parse failed for %s: %s", ticker, exc)
            return None

    if last_exc is not None:
        log.warning("indicator fetch exhausted retries for %s: %s", ticker, last_exc)
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
        else:
            errors.append(ticker)

    if errors:
        missing = ", ".join(sorted(set(errors)))
        log.warning(
            "live market data fetch incomplete; continuing with missing symbols: %s", missing
        )
    if not positions and not indicators:
        raise RuntimeError(
            "live market data fetch failed for all requested positions and indicators"
        )

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
            errors=sorted(set(errors)),
        )
    }
