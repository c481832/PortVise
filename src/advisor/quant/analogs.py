from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import pandas as pd

from advisor.config import config
from advisor.market_data import load_saved_close_frame
from advisor.schemas.market import MarketData, MarketIndicator
from advisor.schemas.regime import HistoricalRegimeOutcome, HistoricalRegimePeriod

if TYPE_CHECKING:
    from advisor.schemas.portfolio import Portfolio

log = logging.getLogger(__name__)


def require_indicator(market_data: MarketData | None, ticker: str) -> MarketIndicator:
    if market_data is None or not market_data.indicators:
        raise RuntimeError("market_data.indicators is required for regime analysis")
    wanted = ticker.strip().upper()
    for row in market_data.indicators:
        if row.ticker.strip().upper() == wanted:
            return row
    raise RuntimeError(f"missing required regime indicator {ticker}")


def compute_max_drawdown(returns: pd.Series) -> float:
    path = (1.0 + returns).cumprod()
    return float((path / path.cummax() - 1.0).min())


def format_date_range(start: object, end: object) -> str:
    return f"{pd.Timestamp(start).date()} to {pd.Timestamp(end).date()}"  # type: ignore[arg-type]


def compute_macro_distances(market_data: MarketData | None) -> pd.Series:
    roles = dict(config.regime.analog_tickers)
    current = pd.Series(
        {
            role: float(require_indicator(market_data, ticker).change_1m_pct) / 100.0
            for role, ticker in roles.items()
        }
    )
    macro_close = load_saved_close_frame(
        list(roles.values()), purpose="Regime analog matching", allow_missing=False
    )
    macro_window = (
        macro_close.pct_change(periods=config.regime.backtest_lookback_days)
        .dropna(how="any")
        .rename(columns={ticker: role for role, ticker in roles.items()})
    )
    return ((macro_window[current.index] - current) ** 2).sum(axis=1).pow(0.5)


def load_position_close(portfolio: Portfolio) -> pd.DataFrame:
    tickers = [p.ticker for p in portfolio.positions]
    if not tickers:
        raise RuntimeError("no portfolio holdings available for analog matching")
    close = load_saved_close_frame(tickers, purpose="Regime analog matching", allow_missing=True)
    missing = sorted(set(tickers) - set(close.columns))
    if missing:
        log.warning(
            "analog matching missing history for %s; continuing with %d/%d positions",
            ", ".join(missing),
            len(close.columns),
            len(tickers),
        )
    return close.dropna(how="any")


def build_available_weights(portfolio: Portfolio, available_tickers: list[str]) -> pd.Series:
    all_weights = {p.ticker: float(p.weight) for p in portfolio.positions}
    total_weight = sum(abs(w) for w in all_weights.values())
    available_weight = sum(abs(all_weights[t]) for t in available_tickers)
    if available_weight <= 0.0:
        raise RuntimeError(
            "remaining holdings have zero total weight after dropping missing history"
        )
    scale = total_weight / available_weight
    return pd.Series({t: all_weights[t] * scale for t in available_tickers})


def find_similar_periods(
    market_data: MarketData | None, portfolio: Portfolio, *, top_n: int
) -> list[dict[str, Any]]:
    lookback_days = config.regime.backtest_lookback_days
    forward_days = config.regime.backtest_forward_days
    distances = compute_macro_distances(market_data)
    position_close = load_position_close(portfolio)
    weights = build_available_weights(portfolio, list(position_close.columns))
    position_daily = position_close.pct_change()

    distances = distances.loc[distances.index.isin(position_close.index[lookback_days:])]
    if len(distances) < config.regime.backtest_min_aligned_observations:
        raise RuntimeError("insufficient historical windows for analog matching")
    last_usable = position_close.index[len(position_close) - forward_days - 1]
    distances = distances.loc[distances.index <= last_usable].sort_values()

    selected: list[dict[str, Any]] = []
    for match_date, distance in distances.items():
        # Nearby dates describe the same regime episode and should not dominate the sample.
        if any(
            abs((match_date - prior["date"]).days) < config.regime.backtest_min_analog_gap_days
            for prior in selected
        ):
            continue
        match_idx = int(position_close.index.get_indexer([match_date])[0])
        # Outcomes begin strictly after the matched date to avoid leaking the setup window.
        forward = position_daily.iloc[match_idx + 1 : match_idx + 1 + forward_days]
        portfolio_daily = forward.mul(weights, axis=1).sum(axis=1)
        selected.append(
            {
                "date": match_date,
                "period": format_date_range(
                    position_close.index[match_idx - lookback_days], match_date
                ),
                "forward_window": format_date_range(forward.index[0], forward.index[-1]),
                "distance": round(float(distance), 4),
                "match_score": round(max(0.0, 1.0 - float(distance)), 4),
                "portfolio_return": round(float((1.0 + portfolio_daily).prod() - 1.0), 4),
                "max_drawdown": round(compute_max_drawdown(portfolio_daily), 4),
            }
        )
        if len(selected) >= max(1, top_n):
            break
    if not selected:
        raise RuntimeError("no valid analog windows found")
    return selected


def summarize_analogs(analogs: list[dict[str, Any]]) -> HistoricalRegimeOutcome:
    returns = [a["portfolio_return"] for a in analogs]
    closest = analogs[0]
    message = (
        f"Closest analog setup: {closest['period']} (distance={closest['distance']:.4f}). "
        f"Forward {config.regime.backtest_forward_days}-trading-day window: "
        f"{closest['forward_window']}. "
        f"Optimistic={max(returns):+.2%}, pessimistic={min(returns):+.2%}, "
        f"extreme={max(returns, key=abs):+.2%}."
    )
    return HistoricalRegimeOutcome(
        runner_available=True,
        message=message,
        analog_periods_identified=len(analogs),
        avg_return=round(sum(returns) / len(returns), 4),
        max_drawdown=min(a["max_drawdown"] for a in analogs),
        win_rate=round(sum(1 for r in returns if r > 0.0) / len(returns), 4),
        top_similar_periods=[HistoricalRegimePeriod.model_validate(a) for a in analogs],
    )
