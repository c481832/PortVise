"""Data agent — fetches live prices and headlines via Yahoo Finance (no LLM call)."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import yfinance as yf

from port.state import GraphState, MarketData, MarketIndicator, PositionSnapshot

log = logging.getLogger(__name__)

_INDICATORS: list[tuple[str, str]] = [
    ("SPY",  "S&P 500"),
    ("QQQ",  "Nasdaq 100"),
    ("IWM",  "Russell 2000"),
    ("TLT",  "20Y Treasury"),
    ("HYG",  "High Yield Credit"),
    ("GLD",  "Gold"),
    ("^VIX", "VIX"),
    ("UUP",  "US Dollar"),
]


def _safe_pct(new: float, old: float) -> float:
    if not old or old != old:
        return 0.0
    return round((new - old) / old * 100, 2)


def _fetch_position_snapshot(ticker: str) -> PositionSnapshot | None:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y", interval="1d", auto_adjust=True)
        if hist.empty or len(hist) < 2:
            log.warning("No history returned for %s", ticker)
            return None

        close = hist["Close"]
        n = len(close)
        current     = float(close.iloc[-1])
        prev_close  = float(close.iloc[-2])
        price_1w    = float(close.iloc[max(-6,  -n)])
        price_1m    = float(close.iloc[max(-22, -n)])
        price_3m    = float(close.iloc[max(-66, -n)])
        week_52_high = float(hist["High"].max())
        week_52_low  = float(hist["Low"].min())

        raw_news = t.news or []
        headlines: list[str] = []
        for n_item in raw_news[:6]:
            title = n_item.get("title") or n_item.get("content", {}).get("title", "")
            if title:
                headlines.append(title)

        return PositionSnapshot(
            ticker=ticker,
            current_price=round(current, 2),
            prev_close=round(prev_close, 2),
            change_1d_pct=_safe_pct(current, prev_close),
            change_1w_pct=_safe_pct(current, price_1w),
            change_1m_pct=_safe_pct(current, price_1m),
            change_3m_pct=_safe_pct(current, price_3m),
            week_52_high=round(week_52_high, 2),
            week_52_low=round(week_52_low, 2),
            pct_from_52w_high=_safe_pct(current, week_52_high),
            recent_headlines=headlines[:5],
        )
    except Exception as exc:
        log.warning("Position fetch failed for %s: %s", ticker, exc)
        return None


def _fetch_indicator(ticker: str, label: str) -> MarketIndicator | None:
    try:
        hist = yf.Ticker(ticker).history(period="35d", interval="1d", auto_adjust=True)
        if hist.empty or len(hist) < 2:
            return None
        close = hist["Close"]
        n = len(close)
        current = float(close.iloc[-1])
        prev    = float(close.iloc[-2])
        price_1m = float(close.iloc[max(-22, -n)])
        return MarketIndicator(
            ticker=ticker,
            label=label,
            current=round(current, 2),
            change_1d_pct=_safe_pct(current, prev),
            change_1m_pct=_safe_pct(current, price_1m),
        )
    except Exception as exc:
        log.warning("Indicator fetch failed for %s: %s", ticker, exc)
        return None


def data_node(state: GraphState) -> dict:
    """Fetch live market data in parallel; no LLM call."""
    portfolio = state["portfolio"]
    position_tickers = [p.ticker for p in portfolio.positions]
    errors: list[str] = []
    snapshots: dict[str, PositionSnapshot] = {}
    indicators: list[MarketIndicator] = []

    with ThreadPoolExecutor(max_workers=12) as pool:
        pos_futures = {pool.submit(_fetch_position_snapshot, t): t for t in position_tickers}
        ind_futures = {
            pool.submit(_fetch_indicator, ticker, label): ticker
            for ticker, label in _INDICATORS
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

    # Preserve _INDICATORS order
    for ticker, _ in _INDICATORS:
        if ticker in ind_results:
            indicators.append(ind_results[ticker])

    return {
        "market_data": MarketData(
            positions=positions,
            indicators=indicators,
            fetched_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            errors=errors,
        )
    }
