"""Shared Yahoo Finance snapshot fetch for position quotes and the data agent."""

from __future__ import annotations

import logging
from datetime import date

import yfinance as yf

from port.models import PositionSnapshot

log = logging.getLogger(__name__)


def _safe_pct(new: float, old: float) -> float:
    if not old or old != old or new != new:
        return 0.0
    return round((new - old) / old * 100, 2)


def _corporate_actions_from_history(hist) -> tuple[float, float]:
    dividend = 0.0
    split = 1.0
    if hist.empty:
        return dividend, split

    for _, row in hist.iterrows():
        cash = float(row.get("Dividends", 0.0) or 0.0)
        if cash:
            dividend += cash * split

        ratio = float(row.get("Stock Splits", 0.0) or 0.0)
        if ratio:
            split *= ratio

    return round(dividend, 6), round(split, 6)


def fetch_corporate_actions(ticker: str, start: date) -> tuple[float, float]:
    """Return cumulative dividends and split ratio from ``start`` through today."""
    hist = yf.Ticker(ticker).history(
        start=start.isoformat(),
        interval="1d",
        actions=True,
        auto_adjust=False,
    )
    return _corporate_actions_from_history(hist)


def fetch_position_snapshot(
    ticker: str,
    actions_start: date | None = None,
) -> PositionSnapshot | None:
    """Load ~1y daily history and build a PositionSnapshot including ~1y return."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y", interval="1d", auto_adjust=True)
        if hist.empty or len(hist) < 2:
            log.info("No history returned for %s", ticker)
            return None

        close = hist["Close"]
        n = len(close)
        current = float(close.iloc[-1])
        prev_close = float(close.iloc[-2])
        price_1w = float(close.iloc[max(-6, -n)])
        price_1m = float(close.iloc[max(-22, -n)])
        price_3m = float(close.iloc[max(-66, -n)])
        idx_1y = max(0, n - 252)
        price_1y = float(close.iloc[idx_1y])
        week_52_high = float(hist["High"].max())  # type: ignore[arg-type]
        week_52_low = float(hist["Low"].min())  # type: ignore[arg-type]

        raw_news = t.news or []
        headlines: list[str] = []
        for n_item in raw_news[:6]:
            title = n_item.get("title") or n_item.get("content", {}).get("title", "")
            if title:
                headlines.append(title)

        dividend, split = (0.0, 1.0)
        if actions_start is not None:
            dividend, split = fetch_corporate_actions(ticker, actions_start)

        return PositionSnapshot(
            ticker=ticker,
            current_price=round(current, 2),
            prev_close=round(prev_close, 2),
            change_1d_pct=_safe_pct(current, prev_close),
            change_1w_pct=_safe_pct(current, price_1w),
            change_1m_pct=_safe_pct(current, price_1m),
            change_3m_pct=_safe_pct(current, price_3m),
            change_1y_pct=_safe_pct(current, price_1y),
            week_52_high=round(week_52_high, 2),
            week_52_low=round(week_52_low, 2),
            pct_from_52w_high=_safe_pct(current, week_52_high),
            dividend=dividend,
            split=split,
            recent_headlines=headlines[:5],
        )
    except Exception as exc:
        log.warning("Position fetch failed for %s: %s", ticker, exc)
        return None
