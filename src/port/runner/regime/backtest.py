"""Historical analog matching from real market history."""

from __future__ import annotations

import logging
from datetime import date, datetime
from math import sqrt
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from port.config import config
from port.market_data import load_saved_close_frame

if TYPE_CHECKING:
    from port.models import MarketData
    from port.portfolio import Portfolio

log = logging.getLogger(__name__)


_MACRO_TICKERS: dict[str, str] = {
    "rates": "^TNX",
    "equity": "SPY",
    "em": "EEM",
    "gold": "GLD",
    "oil": "USO",
    "financials": "XLF",
}
_MACRO_ORDER = tuple(_MACRO_TICKERS.keys())


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


def _as_timestamp(value: object) -> pd.Timestamp | None:
    if isinstance(value, pd.Timestamp):
        return value
    if isinstance(value, (datetime, date, str, int, float)):
        timestamp = pd.Timestamp(value)
        return None if pd.isna(timestamp) else cast(pd.Timestamp, timestamp)
    return None


def _load_close(tickers: list[str]) -> pd.DataFrame:
    if not tickers:
        raise RuntimeError("no portfolio holdings available for analog matching")
    return load_saved_close_frame(
        tickers,
        purpose="Regime analog matching",
        allow_missing=True,
    )


def _portfolio_max_drawdown(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    path = (1.0 + returns).cumprod()
    drawdown = path / path.cummax() - 1.0
    return float(drawdown.min())


def find_similar_periods(
    md: MarketData | None, portfolio: Portfolio, *, top_n: int
) -> list[dict[str, Any]]:
    current = _current_macro_vector(md)
    macro_close = _load_close(list(_MACRO_TICKERS.values()))
    macro_window = macro_close.pct_change(periods=config.regime.backtest_lookback_days).dropna(
        how="any"
    )

    pos_tickers = [p.ticker.upper() for p in portfolio.positions]
    pos_close = _load_close(pos_tickers)
    missing_positions = sorted({t for t in pos_tickers if t not in pos_close.columns})
    available_tickers = [t for t in pos_tickers if t in pos_close.columns]
    if not available_tickers:
        raise RuntimeError(
            "missing portfolio history for analog matching: " + ", ".join(missing_positions)
        )
    if missing_positions:
        log.warning(
            "analog matching missing history for %s; continuing with %d/%d positions",
            ", ".join(missing_positions),
            len(available_tickers),
            len(pos_tickers),
        )
    pos_close = pos_close[available_tickers].dropna(how="any")
    pos_window = pos_close.pct_change(periods=config.regime.backtest_lookback_days).dropna(
        how="any"
    )
    pos_daily = pos_close.pct_change().dropna(how="any")
    raw_weights = {
        p.ticker.upper(): float(p.weight)
        for p in portfolio.positions
        if p.ticker.upper() in available_tickers
    }
    weight_total = sum(abs(w) for w in raw_weights.values())
    if weight_total <= 0.0:
        raise RuntimeError(
            "remaining holdings have zero total weight after dropping missing history"
        )
    weights = pd.Series(raw_weights)
    common_dates = macro_window.index.intersection(pos_window.index)
    if len(common_dates) < config.regime.backtest_min_aligned_observations:
        raise RuntimeError("insufficient historical windows for analog matching")

    rows: list[tuple[pd.Timestamp, dict[str, Any]]] = []
    for match_date in common_dates:
        macro_row = macro_window.loc[match_date]
        vector = {
            key: float(macro_row[ticker])
            for key, ticker in _MACRO_TICKERS.items()
            if ticker in macro_row.index
        }
        if len(vector) != len(_MACRO_ORDER):
            continue
        d = _distance(current, vector)
        score = max(0.0, 1.0 - min(1.0, d))
        idx = pos_close.index.get_indexer([match_date])[0]
        if idx < config.regime.backtest_lookback_days:
            continue
        start = pos_close.index[idx - config.regime.backtest_lookback_days]
        # Outcomes begin strictly after the matched date to avoid leaking the setup window.
        forward_start_idx = pos_daily.index.searchsorted(match_date, side="right")
        forward_end_idx = forward_start_idx + config.regime.backtest_forward_days
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
        start_ts = _as_timestamp(start)
        end_ts = _as_timestamp(match_date)
        forward_start_ts = _as_timestamp(forward_start)
        forward_end_ts = _as_timestamp(forward_end)
        if start_ts is None or end_ts is None or forward_start_ts is None or forward_end_ts is None:
            continue
        period_label = f"{start_ts.date()} to {end_ts.date()}"
        forward_window = f"{forward_start_ts.date()} to {forward_end_ts.date()}"
        rows.append(
            (
                match_date,
                {
                    "period": period_label,
                    "forward_window": forward_window,
                    "forward_horizon_days": config.regime.backtest_forward_days,
                    "distance": round(d, 4),
                    "match_score": round(score, 4),
                    "forward_return": round(portfolio_return, 4),
                    "forward_max_drawdown": round(portfolio_drawdown, 4),
                },
            )
        )
    if not rows:
        raise RuntimeError("no valid analog windows found")
    rows.sort(key=lambda item: (item[1]["distance"], -item[1]["match_score"]))
    selected: list[dict[str, Any]] = []
    selected_dates: list[pd.Timestamp] = []
    for match_date, row in rows:
        # Nearby dates describe the same regime episode and should not dominate the sample.
        if any(
            abs((match_date - prior).days) < config.regime.backtest_min_analog_gap_days
            for prior in selected_dates
        ):
            continue
        selected.append(row)
        selected_dates.append(match_date)
        if len(selected) >= max(1, top_n):
            break
    return selected if selected else [rows[0][1]]


def portfolio_performance(analogs: list[dict[str, Any]]) -> dict[str, Any]:
    if not analogs:
        return {
            "available": False,
            "message": "No historical analogs available for this regime.",
            "avg_return": None,
            "win_rate": None,
            "max_drawdown_proxy": None,
            "top_similar_periods": [],
        }
    returns = [float(x["forward_return"]) for x in analogs]
    drawdowns = [float(x["forward_max_drawdown"]) for x in analogs if "forward_max_drawdown" in x]
    optimistic = max(returns)
    pessimistic = min(returns)
    extreme = max(returns, key=abs)
    wins = sum(1 for x in returns if x > 0.0)
    horizon = int(analogs[0]["forward_horizon_days"])
    forward_window = str(analogs[0]["forward_window"])
    top_similar_periods = [
        {
            "period": str(item["period"]),
            "forward_window": str(item["forward_window"]),
            "forward_horizon_days": int(item["forward_horizon_days"]),
            "distance": float(item["distance"]),
            "match_score": float(item["match_score"]),
            "portfolio_return": float(item["forward_return"]),
            "max_drawdown": float(item["forward_max_drawdown"]),
        }
        for item in analogs
    ]
    return {
        "available": True,
        "message": (
            f"Closest analog setup: {analogs[0]['period']} "
            f"(distance={analogs[0]['distance']:.4f}). "
            f"Forward {horizon}-trading-day window: {forward_window}. "
            f"Optimistic={optimistic:+.2%}, pessimistic={pessimistic:+.2%}, "
            f"extreme={extreme:+.2%}."
        ),
        "avg_return": round(sum(returns) / len(returns), 4),
        "win_rate": round(wins / len(returns), 4),
        "max_drawdown_proxy": round(min(drawdowns), 4) if drawdowns else round(pessimistic, 4),
        "top_similar_periods": top_similar_periods,
    }
