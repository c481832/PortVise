"""Risk analytics from real return series and historical episodes."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

from port.config import config
from port.market_data import load_saved_close_frame
from port.models import RiskReview, ScenarioLoss, WorstScenario

if TYPE_CHECKING:
    from port.models import MarketData
    from port.portfolio import Portfolio

log = logging.getLogger(__name__)


def _factor_tickers() -> dict[str, str]:
    return dict(config.risk_engine.factor_tickers)


def _historical_scenarios() -> tuple[tuple[str, str, str], ...]:
    return tuple((s.name, s.start, s.end) for s in config.risk_engine.historical_scenarios)


@dataclass
class PreparedHistory:
    returns: pd.DataFrame | None
    portfolio_returns: pd.Series | None
    weights: pd.Series | None
    included_tickers: list[str]
    coverage_ratio: float
    notes: list[str]


def _series_from_frame(frame: pd.DataFrame, column: str) -> pd.Series:
    data = frame.loc[:, column]
    if isinstance(data, pd.DataFrame):
        return data.iloc[:, 0]
    return data


def _series_value(series: pd.Series, key: str) -> float:
    value = series.loc[key]
    if isinstance(value, pd.Series):
        return float(value.iloc[0])
    return float(value)


def _extract_close(raw: pd.DataFrame | pd.Series | None, requested: list[str]) -> pd.DataFrame:
    if raw is None or raw.empty:
        raise RuntimeError("yfinance returned empty history")
    if isinstance(raw, pd.DataFrame) and isinstance(raw.columns, pd.MultiIndex):
        if "Close" not in raw.columns.get_level_values(0):
            raise RuntimeError("close prices missing from yfinance response")
        close_slice = raw.xs("Close", axis=1, level=0, drop_level=True)
        close = (
            pd.DataFrame(close_slice)
            if isinstance(close_slice, pd.DataFrame)
            else close_slice.to_frame()
        )
    elif isinstance(raw, pd.Series):
        close = raw.to_frame(name=requested[0])
    elif len(requested) == 1:
        ticker = requested[0]
        if "Close" in raw.columns:
            close = raw[["Close"]].copy()
            close.columns = pd.Index([ticker])
        else:
            close = pd.DataFrame(raw.copy())
            close.columns = pd.Index([ticker])
    else:
        close = pd.DataFrame(raw.copy())
    close.columns = pd.Index([str(c).upper() for c in close.columns])
    close = close.sort_index().dropna(how="all")
    if close.empty:
        raise RuntimeError("close frame is empty after dropping missing rows")
    return pd.DataFrame(close)


def _load_close_frame(tickers: list[str]) -> pd.DataFrame:
    return load_saved_close_frame(tickers, purpose="Risk analysis")


def _prepare_history(close: pd.DataFrame, portfolio: Portfolio) -> PreparedHistory:
    tickers = [p.ticker.strip().upper() for p in portfolio.positions]
    if not tickers:
        return PreparedHistory(
            returns=None,
            portfolio_returns=None,
            weights=None,
            included_tickers=[],
            coverage_ratio=0.0,
            notes=["No holdings were provided for return-based risk analysis."],
        )

    weight_map = {p.ticker.strip().upper(): float(p.weight) for p in portfolio.positions}
    total_abs_weight = sum(abs(weight_map[t]) for t in tickers)
    history_counts = {
        ticker: int(_series_from_frame(close, ticker).dropna().shape[0])
        if ticker in close.columns
        else 0
        for ticker in tickers
    }
    eligible = [
        ticker
        for ticker in tickers
        if history_counts[ticker] >= config.risk_engine.min_observations
    ]
    excluded: list[str] = []
    for ticker in tickers:
        if ticker in eligible:
            continue
        days = history_counts[ticker]
        if days <= 0:
            excluded.append(f"{ticker} (no usable price history)")
        else:
            excluded.append(f"{ticker} ({days} trading days)")

    aligned: pd.DataFrame | None = None
    while eligible:
        candidate = pd.DataFrame(close.loc[:, eligible]).dropna(how="any")
        if len(candidate) >= config.risk_engine.min_observations:
            aligned = candidate
            break
        # Remove the least useful series until the remaining holdings have enough shared dates.
        worst = min(eligible, key=lambda ticker: (history_counts[ticker], abs(weight_map[ticker])))
        eligible.remove(worst)
        excluded.append(
            f"{worst} (insufficient overlap with peers; only {len(candidate)} aligned days)"
        )

    included_abs_weight = sum(abs(weight_map[t]) for t in eligible)
    coverage_ratio = included_abs_weight / total_abs_weight if total_abs_weight > 0 else 0.0
    notes: list[str] = []
    if excluded:
        notes.append(
            "Return-based risk excluded holdings with incomplete history: "
            + ", ".join(excluded[:8])
        )
    if coverage_ratio < 1.0:
        notes.append(f"Return-based risk covers {coverage_ratio:.0%} of invested portfolio weight.")
    if not eligible or aligned is None:
        notes.append("History coverage is too thin for factor and stress estimates.")
        return PreparedHistory(
            returns=None,
            portfolio_returns=None,
            weights=None,
            included_tickers=[],
            coverage_ratio=coverage_ratio,
            notes=notes,
        )

    returns = pd.DataFrame(aligned.pct_change()).dropna(how="any")
    if returns.empty:
        notes.append("Aligned price history produced no daily returns after cleanup.")
        return PreparedHistory(
            returns=None,
            portfolio_returns=None,
            weights=None,
            included_tickers=eligible,
            coverage_ratio=coverage_ratio,
            notes=notes,
        )

    weights = pd.Series({ticker: weight_map[ticker] for ticker in eligible}, dtype=float)
    included_abs_weight = float(weights.abs().sum())
    if included_abs_weight <= 0:
        notes.append("Included holdings have zero total weight; using structural-only risk output.")
        return PreparedHistory(
            returns=None,
            portfolio_returns=None,
            weights=None,
            included_tickers=eligible,
            coverage_ratio=coverage_ratio,
            notes=notes,
        )

    if coverage_ratio < config.risk_engine.min_return_coverage:
        notes.append(
            f"Coverage is below {config.risk_engine.min_return_coverage:.0%}; "
            "factor and stress outputs represent the covered subset only."
        )

    portfolio_returns = returns.mul(weights, axis=1).sum(axis=1)
    return PreparedHistory(
        returns=returns,
        portfolio_returns=portfolio_returns,
        weights=weights,
        included_tickers=eligible,
        coverage_ratio=coverage_ratio,
        notes=notes,
    )


def _beta(portfolio_returns: pd.Series, factor_returns: pd.Series) -> float:
    joined = pd.concat([portfolio_returns, factor_returns], axis=1).dropna(how="any")
    if len(joined) < 40:
        return 0.0
    p = joined.iloc[:, 0]
    f = joined.iloc[:, 1]
    f_var = float(f.var())
    if f_var <= 0:
        return 0.0
    return float(p.cov(f) / f_var)


def _factor_outputs(
    close: pd.DataFrame, portfolio_returns: pd.Series, included_weight: float
) -> tuple[dict[str, float], dict[str, float]]:
    factor_columns = [ticker for ticker in _factor_tickers().values() if ticker in close.columns]
    if not factor_columns:
        return {}, {}
    all_returns = pd.DataFrame(close.loc[:, factor_columns].pct_change()).dropna(how="any")
    if all_returns.empty:
        return {}, {}
    loadings: dict[str, float] = {}
    raw_contrib: dict[str, float] = {}
    for name, ticker in _factor_tickers().items():
        if ticker not in all_returns.columns:
            continue
        factor_series = _series_from_frame(all_returns, ticker)
        b = _beta(portfolio_returns, factor_series)
        key = f"beta_{name}"
        loadings[key] = round(b, 4)
        variance = float(factor_series.to_numpy(dtype=float).var(ddof=1))
        raw_contrib[key] = abs(b) * variance
    denom = sum(raw_contrib.values())
    # These are normalized exposure proxies, not an additive covariance attribution.
    if denom <= 0:
        contrib = dict.fromkeys(loadings, 0.0)
    else:
        contrib = {k: round((v / denom) * included_weight, 4) for k, v in raw_contrib.items()}
    return loadings, contrib


def _marginal_risk(returns: pd.DataFrame, weights: pd.Series) -> dict[str, float]:
    cov = returns.cov()
    ordered = [str(t) for t in weights.index]
    weights = weights.reindex(ordered)
    mw_raw = cov.dot(weights)
    mw = mw_raw if isinstance(mw_raw, pd.Series) else pd.Series(mw_raw, index=ordered, dtype=float)
    port_var = float(weights.to_numpy(dtype=float) @ mw.to_numpy(dtype=float))
    if port_var <= 0:
        raise RuntimeError("portfolio variance is non-positive")
    signed = {
        t: float(_series_value(weights, t) * _series_value(mw, t) / port_var) for t in ordered
    }
    total = sum(abs(v) for v in signed.values())
    if total <= 0:
        return dict.fromkeys(ordered, 0.0)
    included_weight = float(weights.abs().sum())
    return {t: round((abs(v) / total) * included_weight, 4) for t, v in signed.items()}


def _top5_concentration(portfolio: Portfolio) -> float:
    ws = sorted((abs(p.weight) for p in portfolio.positions), reverse=True)
    return sum(ws[:5])


def _cluster_overlap(returns: pd.DataFrame, weights: pd.Series) -> list[str]:
    corr = returns.corr()
    out: list[str] = []
    cols = list(corr.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1 :]:
            c = float(corr.loc[a, b])
            if c >= config.risk_engine.correlation_threshold:
                pair_weight = abs(_series_value(weights, str(a))) + abs(
                    _series_value(weights, str(b))
                )
                out.append(
                    f"{a}/{b} correlation {c:.2f}; combined portfolio weight {pair_weight:.1%}"
                )
    return out[:8]


def _stress_scenarios(
    returns: pd.DataFrame,
    portfolio_returns: pd.Series,
    portfolio: Portfolio,
    included_tickers: list[str],
    weights: pd.Series,
) -> tuple[list[ScenarioLoss], WorstScenario | None]:
    def _most_affected_positions(slice_pos: pd.DataFrame) -> list[str]:
        if slice_pos.empty:
            return _top_tickers_by_weight(portfolio, 4, limit_to=included_tickers)
        contribution: dict[str, float] = {}
        for ticker in included_tickers:
            t = ticker.upper()
            if t not in slice_pos.columns:
                continue
            position_returns = _series_from_frame(slice_pos, t)
            growth = float((1.0 + position_returns.to_numpy(dtype=float)).prod() - 1.0)
            contribution[t] = abs(_series_value(weights, t) * growth)
        ranked = sorted(contribution, key=lambda t: contribution[t], reverse=True)
        return (
            ranked[:4]
            if ranked
            else _top_tickers_by_weight(portfolio, 4, limit_to=included_tickers)
        )

    def _fallback_windows() -> list[ScenarioLoss]:
        scenarios: list[ScenarioLoss] = []
        window_specs = (
            (10, "Worst 2-week window (available history)"),
            (21, "Worst 1-month window (available history)"),
            (63, "Worst 1-quarter window (available history)"),
        )
        for window, label in window_specs:
            if len(portfolio_returns) < window:
                continue
            rolling_growth = (
                (1.0 + portfolio_returns).rolling(window).apply(lambda x: float(x.prod()))
            )
            rolling_loss = rolling_growth - 1.0
            worst_end = rolling_loss.idxmin()
            if pd.isna(worst_end) or not isinstance(worst_end, pd.Timestamp):
                continue
            worst_loss_pct = float(rolling_loss.loc[worst_end]) * 100.0
            end_loc = portfolio_returns.index.get_loc(worst_end)
            if not isinstance(end_loc, int):
                continue
            start_loc = end_loc - window + 1
            if start_loc < 0:
                continue
            worst_start = portfolio_returns.index[start_loc]
            slice_pos = returns.loc[worst_start:worst_end]
            scenarios.append(
                ScenarioLoss(
                    scenario=label,
                    estimated_portfolio_loss_pct=round(worst_loss_pct, 4),
                    most_affected_positions=_most_affected_positions(slice_pos),
                    scenario_kind="historical",
                )
            )
        return scenarios

    scenarios: list[ScenarioLoss] = []
    for label, start, end in _historical_scenarios():
        slice_port = portfolio_returns.loc[start:end]
        if slice_port.empty:
            continue
        pnl = float((1.0 + slice_port).prod() - 1.0) * 100.0
        slice_pos = returns.loc[start:end]
        scenarios.append(
            ScenarioLoss(
                scenario=label,
                estimated_portfolio_loss_pct=round(pnl, 4),
                most_affected_positions=_most_affected_positions(slice_pos),
                scenario_kind="historical",
            )
        )
    if not scenarios:
        log.warning(
            "historical stress windows outside available history; "
            "using worst available rolling windows"
        )
        # Recent listings may not span named crises, so retain a data-backed stress result.
        scenarios = _fallback_windows()
    if not scenarios:
        raise RuntimeError("no stress scenarios could be computed from available data")
    worst = min(scenarios, key=lambda s: s.estimated_portfolio_loss_pct)
    return scenarios, WorstScenario(
        name=worst.scenario,
        estimated_portfolio_loss_pct=worst.estimated_portfolio_loss_pct,
    )


def _top_tickers_by_weight(
    portfolio: Portfolio, n: int, *, limit_to: list[str] | None = None
) -> list[str]:
    allowed = {ticker.upper() for ticker in limit_to} if limit_to else None
    ranked = sorted(
        (p for p in portfolio.positions if allowed is None or p.ticker.upper() in allowed),
        key=lambda p: abs(p.weight),
        reverse=True,
    )
    if not ranked and limit_to:
        ranked = sorted(portfolio.positions, key=lambda p: abs(p.weight), reverse=True)
    return [p.ticker.upper() for p in ranked[:n]]


def compute_risk_review_base(portfolio: Portfolio, _md: MarketData | None = None) -> RiskReview:
    all_tickers = [p.ticker.upper() for p in portfolio.positions] + list(_factor_tickers().values())
    close = _load_close_frame(all_tickers)
    prepared = _prepare_history(close, portfolio)
    top5 = _top5_concentration(portfolio)
    if prepared.returns is None or prepared.portfolio_returns is None or prepared.weights is None:
        detail = "; ".join(prepared.notes) if prepared.notes else "no aligned return history"
        raise RuntimeError(f"Risk analysis unavailable: {detail}")

    included_weight = float(prepared.weights.abs().sum())
    loadings, fr_contrib = _factor_outputs(close, prepared.portfolio_returns, included_weight)
    marginal = _marginal_risk(prepared.returns, prepared.weights)
    scenarios, worst = _stress_scenarios(
        prepared.returns,
        prepared.portfolio_returns,
        portfolio,
        prepared.included_tickers,
        prepared.weights,
    )
    clusters = _cluster_overlap(prepared.returns, prepared.weights)

    return RiskReview(
        factor_loadings=loadings,
        factor_risk_contribution=fr_contrib,
        marginal_risk_by_ticker=marginal,
        exposure_links=[],
        concentration_issues=(
            [f"Top 5 names ≈ {top5 * 100:.0f}% of portfolio"] if top5 > 0.55 else []
        ),
        concentration_top5_pct=round(top5, 4),
        liquidity_notes=[],
        scenario_losses=scenarios,
        top_risks=[],
        worst_scenario=worst,
        hidden_concentration=clusters,
        summary="",
    )


def format_risk_python_block(base: RiskReview) -> str:
    lines = [
        "=== PYTHON RISK ENGINE (authoritative numbers — add interpretation only) ===",
        "",
        "factor_loadings (real-data betas): "
        + ", ".join(f"{k}={v:.2f}" for k, v in sorted(base.factor_loadings.items())),
        "factor_risk_contribution (cash-aware): "
        + ", ".join(f"{k}={v:.2f}" for k, v in sorted(base.factor_risk_contribution.items())),
        "marginal_risk_by_ticker (cash-aware; scaled by included portfolio weight): "
        + ", ".join(f"{k}={v:.2f}" for k, v in sorted(base.marginal_risk_by_ticker.items())[:12]),
        f"concentration_top5_pct: {base.concentration_top5_pct:.2f}",
        f"worst_scenario (engine): {base.worst_scenario.name if base.worst_scenario else 'n/a'} "
        f"({base.worst_scenario.estimated_portfolio_loss_pct:.2f}%)"
        if base.worst_scenario
        else "worst_scenario: n/a",
    ]
    if base.hidden_concentration:
        lines.append("hidden_concentration: " + "; ".join(base.hidden_concentration))
    return "\n".join(lines)
