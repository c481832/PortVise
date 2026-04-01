"""Shared Yahoo Finance snapshot fetch for position quotes and the data agent."""

from __future__ import annotations

import logging

import yfinance as yf

from port.models import PositionSnapshot

log = logging.getLogger(__name__)


def _safe_pct(new: float, old: float) -> float:
    if not old or old != old or new != new:
        return 0.0
    return round((new - old) / old * 100, 2)


def fetch_position_snapshot(ticker: str) -> PositionSnapshot | None:
    """Load ~1y daily history and build a PositionSnapshot including ~1y return."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y", interval="1d", auto_adjust=True)
        if hist.empty or len(hist) < 2:
            log.warning("No history returned for %s", ticker)
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
            recent_headlines=headlines[:5],
        )
    except Exception as exc:
        log.warning("Position fetch failed for %s: %s", ticker, exc)
        return None
