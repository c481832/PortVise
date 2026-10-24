from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from advisor.config import config
from advisor.market_data import load_saved_close_frame
from advisor.schemas.portfolio import Portfolio
from advisor.schemas.risk import RiskReview, ScenarioLoss, WorstScenario

log = logging.getLogger(__name__)

ROLLING_STRESS_WINDOWS = (
    (10, "Worst 2-week window (available history)"),
    (21, "Worst 1-month window (available history)"),
    (63, "Worst 1-quarter window (available history)"),
)


def prepare_history(
    close: pd.DataFrame, portfolio: Portfolio
) -> tuple[pd.DataFrame, pd.Series, pd.Series, list[str]]:
    weight_map = {p.ticker: float(p.weight) for p in portfolio.positions}
    if not weight_map:
        raise RuntimeError("Risk analysis unavailable: no holdings were provided")
    min_observations = config.risk_engine.min_observations
    counts = close.loc[:, list(weight_map)].count()
    history_counts = {str(t): int(n) for t, n in counts.items()}
    eligible = [t for t, days in history_counts.items() if days >= min_observations]
    excluded = [
        f"{t} ({days} trading days)" for t, days in history_counts.items() if t not in eligible
    ]

    aligned = close.loc[:, eligible].dropna(how="any")
    while eligible and len(aligned) < min_observations:
        worst = min(eligible, key=lambda t: (history_counts[t], abs(weight_map[t])))
        eligible.remove(worst)
        excluded.append(
            f"{worst} (insufficient overlap with peers; only {len(aligned)} aligned days)"
        )
        aligned = close.loc[:, eligible].dropna(how="any")

    total_weight = sum(abs(w) for w in weight_map.values())
    included_weight = sum(abs(weight_map[t]) for t in eligible)
    coverage = included_weight / total_weight if total_weight > 0 else 0.0
    notes: list[str] = []
    if excluded:
        notes.append(
            "Return-based risk excluded holdings with incomplete history: "
            + ", ".join(excluded[:8])
        )
    if coverage < 1.0:
        notes.append(f"Return-based risk covers {coverage:.0%} of invested portfolio weight.")
    if coverage < config.risk_engine.min_return_coverage:
        notes.append(
            f"Coverage is below {config.risk_engine.min_return_coverage:.0%}; "
            "factor and stress outputs represent the covered subset only."
        )
    if not eligible or included_weight <= 0:
        raise RuntimeError(
            "Risk analysis unavailable: history coverage is too thin for factor and stress "
            "estimates; " + "; ".join(notes)
        )

    returns = aligned.pct_change().dropna(how="any")
    weights = pd.Series({t: weight_map[t] for t in eligible}, dtype=float)
    return returns, returns.mul(weights, axis=1).sum(axis=1), weights, notes


def list_factor_tickers() -> dict[str, str]:
    model = config.risk_engine.factor_model
    return {
        "market": model.market,
        **dict(model.tilts),
        **dict(model.macro),
        **dict(model.spread_changes),
        **dict(model.scores),
    }


def build_factor_returns(close: pd.DataFrame) -> pd.DataFrame:
    model = config.risk_engine.factor_model
    levels = close.loc[:, list(list_factor_tickers().values())].dropna(how="any")
    if levels.empty:
        raise RuntimeError("no shared dates across factor series")

    market = levels.loc[:, model.market].pct_change()
    factors = {"market": market}
    for name, ticker in model.tilts.items():
        factors[f"{name}_vs_market"] = levels.loc[:, ticker].pct_change() - market
    for name, ticker in model.macro.items():
        factors[name] = levels.loc[:, ticker].pct_change()
    for name, ticker in model.spread_changes.items():
        factors[name] = levels.loc[:, ticker].diff()
    for name, ticker in model.scores.items():
        factors[name] = levels.loc[:, ticker]
    return pd.DataFrame(factors).dropna(how="any")


def compute_factor_exposures(
    factor_returns: pd.DataFrame, portfolio_returns: pd.Series
) -> tuple[dict[str, float], dict[str, float]]:
    joined = pd.concat([portfolio_returns.rename("portfolio"), factor_returns], axis=1).dropna(
        how="any"
    )
    if len(joined) < config.risk_engine.min_observations:
        raise RuntimeError(f"only {len(joined)} days of shared portfolio and factor history")
    names = list(factor_returns.columns)
    y = joined.loc[:, "portfolio"].to_numpy(dtype=float)
    x = joined.loc[:, names].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(x)), x])
    coef = np.linalg.lstsq(design, y, rcond=None)[0]
    betas = coef[1:]
    total_variance = float(y.var(ddof=1))
    if total_variance <= 0:
        raise RuntimeError("portfolio return variance is non-positive")
    factor_shares = betas * (np.cov(x, rowvar=False) @ betas) / total_variance
    idiosyncratic_share = float((y - design @ coef).var(ddof=1)) / total_variance

    loadings = {name: round(float(b), 4) for name, b in zip(names, betas, strict=True)}
    contrib = {name: round(float(v), 4) for name, v in zip(names, factor_shares, strict=True)}
    contrib["idiosyncratic"] = round(idiosyncratic_share, 4)
    return loadings, contrib


def compute_holding_risk(
    returns: pd.DataFrame, weights: pd.Series
) -> tuple[dict[str, float], dict[str, float], float]:
    w = weights.to_numpy(dtype=float)
    cov = returns.cov().to_numpy(dtype=float) * config.risk_engine.trading_days_per_year
    marginal = cov @ w
    variance = float(w @ marginal)
    if variance <= 0:
        raise RuntimeError("portfolio variance is non-positive")
    volatility = float(np.sqrt(variance))
    tickers = [str(t) for t in weights.index]
    risk_share = {
        t: round(float(v), 4) for t, v in zip(tickers, w * marginal / variance, strict=True)
    }
    vol_contrib = {
        t: round(float(v), 4) for t, v in zip(tickers, w * marginal / volatility, strict=True)
    }
    return risk_share, vol_contrib, round(volatility, 4)


def find_correlated_pairs(returns: pd.DataFrame, weights: pd.Series) -> list[str]:
    corr = returns.corr()
    weight_by_ticker = {str(t): float(w) for t, w in weights.items()}
    tickers = list(corr.columns)
    pairs: list[str] = []
    for i, left in enumerate(tickers):
        for right in tickers[i + 1 :]:
            correlation = float(corr.loc[left, right])
            if correlation < config.risk_engine.correlation_threshold:
                continue
            pair_weight = abs(weight_by_ticker[left]) + abs(weight_by_ticker[right])
            pairs.append(
                f"{left}/{right} correlation {correlation:.2f}; "
                f"combined portfolio weight {pair_weight:.1%}"
            )
    return pairs[:8]


def compute_rolling_stress(portfolio_returns: pd.Series) -> list[ScenarioLoss]:
    log_returns = pd.Series(np.log1p(portfolio_returns), index=portfolio_returns.index)
    scenarios: list[ScenarioLoss] = []
    for window, label in ROLLING_STRESS_WINDOWS:
        if len(portfolio_returns) < window:
            continue
        worst_loss = float(np.expm1(log_returns.rolling(window).sum().min()))
        scenarios.append(
            ScenarioLoss(scenario=label, estimated_portfolio_loss_pct=round(worst_loss * 100.0, 4))
        )
    return scenarios


def compute_stress_scenarios(portfolio_returns: pd.Series) -> list[ScenarioLoss]:
    scenarios: list[ScenarioLoss] = []
    for scenario in config.risk_engine.historical_scenarios:
        window = portfolio_returns.loc[scenario.start : scenario.end]
        if window.empty:
            continue
        loss = float((1.0 + window).prod() - 1.0)
        scenarios.append(
            ScenarioLoss(
                scenario=scenario.name, estimated_portfolio_loss_pct=round(loss * 100.0, 4)
            )
        )
    if scenarios:
        return scenarios
    log.warning("historical stress windows outside available history; using rolling windows")
    scenarios = compute_rolling_stress(portfolio_returns)
    if not scenarios:
        raise RuntimeError("no stress scenarios could be computed from available data")
    return scenarios


def compute_risk_review_base(portfolio: Portfolio) -> RiskReview:
    position_tickers = [p.ticker for p in portfolio.positions]
    close = load_saved_close_frame(
        position_tickers + list(list_factor_tickers().values()),
        purpose="Risk analysis",
        allow_missing=False,
    )
    returns, portfolio_returns, weights, notes = prepare_history(close, portfolio)
    loadings, factor_contrib = compute_factor_exposures(
        build_factor_returns(close), portfolio_returns
    )
    risk_share, vol_contrib, volatility = compute_holding_risk(returns, weights)
    scenarios = compute_stress_scenarios(portfolio_returns)
    worst = min(scenarios, key=lambda s: s.estimated_portfolio_loss_pct)
    top5 = sum(sorted((abs(p.weight) for p in portfolio.positions), reverse=True)[:5])

    return RiskReview(
        factor_loadings=loadings,
        factor_risk_contribution=factor_contrib,
        risk_contribution_by_ticker=risk_share,
        volatility_contribution_by_ticker=vol_contrib,
        portfolio_volatility=volatility,
        concentration_issues=(
            [f"Top 5 names ≈ {top5 * 100:.0f}% of portfolio"] if top5 > 0.55 else []
        ),
        concentration_top5_pct=round(top5, 4),
        scenario_losses=scenarios,
        top_risks=notes,
        worst_scenario=WorstScenario(
            name=worst.scenario, estimated_portfolio_loss_pct=worst.estimated_portfolio_loss_pct
        ),
        hidden_concentration=find_correlated_pairs(returns, weights),
        summary="",
    )
