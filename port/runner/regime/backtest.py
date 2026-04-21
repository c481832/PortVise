"""Historical analog matching from real market history."""

from __future__ import annotations

from math import sqrt
from typing import TYPE_CHECKING, Any

import pandas as pd
import yfinance as yf

if TYPE_CHECKING:
    from port.models import MarketData
    from port.portfolio import Portfolio


_MACRO_ORDER = ("rates", "equity", "em", "gold", "oil", "financials")
_MACRO_TICKERS: dict[str, str] = {
    "rates": "^TNX",
    "equity": "SPY",
    "em": "EEM",
    "gold": "GLD",
    "oil": "USO",
    "financials": "XLF",
}
_LOOKBACK_DAYS = 21
_FORWARD_DAYS = 21
_MIN_ANALOG_GAP_DAYS = 21


def _indicator_1m(md: MarketData | None, ticker: str) -> float:
    if not md or not md.indicators:
        raise RuntimeError("market_data.indicators is required for regime analog matching")
    wanted = ticker.upper()
    for row in md.indicators:
        if row.ticker.upper() == wanted:
            return float(row.change_1m_pct) / 100.0
    raise RuntimeError(f"missing indicator {ticker} in market_data")


def _current_macro_vector(md: MarketData | None) -> dict[str, float]:
    return {
        "rates": _indicator_1m(md, "^TNX"),
        "equity": _indicator_1m(md, "SPY"),
        "em": _indicator_1m(md, "EEM"),
        "gold": _indicator_1m(md, "GLD"),
        "oil": _indicator_1m(md, "USO"),
        "financials": _indicator_1m(md, "XLF"),
    }


def _distance(lhs: dict[str, float], rhs: dict[str, float]) -> float:
    sq = 0.0
    for key in _MACRO_ORDER:
        diff = lhs.get(key, 0.0) - rhs.get(key, 0.0)
        sq += diff * diff
    return sqrt(sq)


def _download_close(tickers: list[str], period: str) -> pd.DataFrame:
    if not tickers:
        raise RuntimeError("no portfolio holdings available for analog matching")
    raw = yf.download(
        tickers=sorted(set(tickers)),
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="column",
    )
    if raw.empty:
        raise RuntimeError("yfinance returned no data for analog matching")
    if isinstance(raw.columns, pd.MultiIndex):
        if "Close" not in raw.columns.get_level_values(0):
            raise RuntimeError("close prices missing from yfinance response")
        close = raw["Close"].copy()
    else:
        close = raw.to_frame(name=tickers[0]) if isinstance(raw, pd.Series) else raw.copy()
    close.columns = [str(c).upper() for c in close.columns]
    close = close.sort_index().dropna(how="all")
    if close.empty:
        raise RuntimeError("price history empty after cleanup")
    return close


def _portfolio_max_drawdown(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    path = (1.0 + returns).cumprod()
    drawdown = path / path.cummax() - 1.0
    return float(drawdown.min())


def find_similar_periods(
    md: MarketData | None, regime_id: str, portfolio: Portfolio, top_n: int = 3
) -> list[dict[str, Any]]:
    current = _current_macro_vector(md)
    macro_close = _download_close(list(_MACRO_TICKERS.values()), period="10y")
    macro_window = macro_close.pct_change(periods=_LOOKBACK_DAYS).dropna(how="any")

    pos_tickers = [p.ticker.upper() for p in portfolio.positions]
    pos_close = _download_close(pos_tickers, period="10y")
    missing_positions = [t for t in pos_tickers if t not in pos_close.columns]
    if missing_positions:
        raise RuntimeError(
            "missing portfolio history for analog matching: "
            + ", ".join(sorted(set(missing_positions)))
        )
    pos_close = pos_close[pos_tickers].dropna(how="any")
    pos_window = pos_close.pct_change(periods=_LOOKBACK_DAYS).dropna(how="any")
    pos_daily = pos_close.pct_change().dropna(how="any")
    weights = pd.Series({p.ticker.upper(): float(p.weight) for p in portfolio.positions})
    common_dates = macro_window.index.intersection(pos_window.index)
    if len(common_dates) < 120:
        raise RuntimeError("insufficient historical windows for analog matching")

    rows: list[tuple[pd.Timestamp, dict[str, Any]]] = []
    for date in common_dates:
        macro_row = macro_window.loc[date]
        vector = {
            key: float(macro_row[ticker])
            for key, ticker in _MACRO_TICKERS.items()
            if ticker in macro_row.index
        }
        if len(vector) != len(_MACRO_ORDER):
            continue
        d = _distance(current, vector)
        score = max(0.0, 1.0 - min(1.0, d))
        idx = pos_close.index.get_indexer([date])[0]
        if idx < _LOOKBACK_DAYS:
            continue
        start = pos_close.index[idx - _LOOKBACK_DAYS]
        forward_start_idx = pos_daily.index.searchsorted(date, side="right")
        forward_end_idx = forward_start_idx + _FORWARD_DAYS
        if forward_end_idx > len(pos_daily):
            continue
        forward_slice = pos_daily.iloc[forward_start_idx:forward_end_idx]
        if forward_slice.empty:
            continue
        portfolio_daily = forward_slice.mul(weights, axis=1).sum(axis=1)
        portfolio_return = float((1.0 + portfolio_daily).prod() - 1.0)
        portfolio_drawdown = _portfolio_max_drawdown(portfolio_daily)
        forward_start = forward_slice.index[0]
        forward_end = forward_slice.index[-1]
        period_label = f"{start.date()} to {date.date()}"
        rows.append(
            (
                date,
                {
                    "period": period_label,
                    "forward_window": f"{forward_start.date()} to {forward_end.date()}",
                    "forward_horizon_days": _FORWARD_DAYS,
                    "regime_id": regime_id,
                    "distance": round(d, 4),
                    "match_score": round(score, 4),
                    "regime_match": True,
                    "portfolio_return": round(portfolio_return, 4),
                    "forward_return": round(portfolio_return, 4),
                    "forward_max_drawdown": round(portfolio_drawdown, 4),
                    "macro_vector": {k: round(v, 4) for k, v in vector.items()},
                },
            )
        )
    if not rows:
        raise RuntimeError("no valid analog windows found")
    rows.sort(key=lambda item: (item[1]["distance"], -item[1]["match_score"]))
    selected: list[dict[str, Any]] = []
    selected_dates: list[pd.Timestamp] = []
    for date, row in rows:
        if any(abs((date - prior).days) < _MIN_ANALOG_GAP_DAYS for prior in selected_dates):
            continue
        selected.append(row)
        selected_dates.append(date)
        if len(selected) >= max(1, top_n):
            break
    return selected if selected else [rows[0][1]]


def portfolio_performance(analogs: list[dict[str, Any]]) -> dict[str, Any]:
    if not analogs:
        return {
            "available": False,
            "message": "No historical analogs available for this regime.",
            "optimistic_return": None,
            "pessimistic_return": None,
            "extreme_return": None,
            "avg_return": None,
            "win_rate": None,
            "max_drawdown_proxy": None,
        }
    returns = [float(x.get("forward_return", x["portfolio_return"])) for x in analogs]
    drawdowns = [
        float(x.get("forward_max_drawdown"))
        for x in analogs
        if x.get("forward_max_drawdown") is not None
    ]
    optimistic = max(returns)
    pessimistic = min(returns)
    extreme = pessimistic
    wins = sum(1 for x in returns if x > 0.0)
    horizon = analogs[0].get("forward_horizon_days", _FORWARD_DAYS)
    forward_window = analogs[0].get("forward_window", "n/a")
    return {
        "available": True,
        "message": (
            f"Closest analog setup: {analogs[0]['period']} "
            f"(distance={analogs[0]['distance']:.4f}). "
            f"Forward {horizon}-trading-day window: {forward_window}. "
            f"Optimistic={optimistic:+.2%}, pessimistic={pessimistic:+.2%}, "
            f"extreme={extreme:+.2%}."
        ),
        "optimistic_return": round(optimistic, 4),
        "pessimistic_return": round(pessimistic, 4),
        "extreme_return": round(extreme, 4),
        "avg_return": round(sum(returns) / len(returns), 4),
        "win_rate": round(wins / len(returns), 4),
        "max_drawdown_proxy": round(min(drawdowns), 4) if drawdowns else round(pessimistic, 4),
    }
