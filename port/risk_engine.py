"""Risk analytics from real return series and historical episodes."""

from __future__ import annotations

import logging
from math import sqrt
from typing import TYPE_CHECKING

import pandas as pd
import yfinance as yf

from port.models import RiskReview, ScenarioLoss, WorstScenario

if TYPE_CHECKING:
    from port.portfolio import Portfolio

log = logging.getLogger(__name__)

_HISTORY_PERIOD = "3y"
_YFINANCE_TIMEOUT_SECONDS = 8
_FACTOR_TICKERS: dict[str, str] = {
    "spy": "SPY",
    "qqq": "QQQ",
    "tlt": "TLT",
    "gld": "GLD",
    "uso": "USO",
    "uup": "UUP",
    "xlf": "XLF",
    "eem": "EEM",
}
_HISTORICAL_SCENARIOS: tuple[tuple[str, str, str], ...] = (
    ("COVID crash", "2020-02-19", "2020-03-23"),
    ("2022 inflation shock", "2022-01-03", "2022-10-14"),
    ("2023 regional bank stress", "2023-03-08", "2023-03-24"),
)


def _extract_close(raw: pd.DataFrame | pd.Series, requested: list[str]) -> pd.DataFrame:
    if raw.empty:
        raise RuntimeError("yfinance returned empty history")
    if isinstance(raw.columns, pd.MultiIndex):
        if "Close" not in raw.columns.get_level_values(0):
            raise RuntimeError("close prices missing from yfinance response")
        close = raw["Close"].copy()
    elif len(requested) == 1:
        ticker = requested[0]
        if isinstance(raw, pd.Series):
            close = raw.to_frame(name=ticker)
        elif "Close" in raw.columns:
            close = raw[["Close"]].copy()
            close.columns = [ticker]
        else:
            close = raw.copy()
            close.columns = [ticker]
    else:
        close = raw.to_frame(name=requested[0]) if isinstance(raw, pd.Series) else raw.copy()
    close.columns = [str(c).upper() for c in close.columns]
    close = close.sort_index().dropna(how="all")
    if close.empty:
        raise RuntimeError("close frame is empty after dropping missing rows")
    return close


def _download_close_frame(tickers: list[str]) -> pd.DataFrame:
    unique = sorted(set(t.strip().upper() for t in tickers if t and t.strip()))
    if not unique:
        raise ValueError("no tickers supplied")
    raw = yf.download(
        tickers=unique,
        period=_HISTORY_PERIOD,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=False,
        timeout=_YFINANCE_TIMEOUT_SECONDS,
        group_by="column",
    )
    close = _extract_close(raw, unique)
    missing = [ticker for ticker in unique if ticker not in close.columns]
    if missing:
        log.warning("batch yfinance download missing tickers %s; retrying individually", missing)
        for ticker in missing:
            try:
                single_raw = yf.download(
                    tickers=ticker,
                    period=_HISTORY_PERIOD,
                    interval="1d",
                    auto_adjust=True,
                    progress=False,
                    threads=False,
                    timeout=_YFINANCE_TIMEOUT_SECONDS,
                    group_by="column",
                )
                single_close = _extract_close(single_raw, [ticker])
                close[ticker] = single_close[ticker]
            except Exception:
                log.exception("failed to download retry history for %s", ticker)
    return close


def _portfolio_returns(close: pd.DataFrame, portfolio: Portfolio) -> tuple[pd.DataFrame, pd.Series]:
    tickers = [p.ticker.strip().upper() for p in portfolio.positions]
    missing = [t for t in tickers if t not in close.columns]
    if missing:
        raise RuntimeError(f"missing price history for holdings: {', '.join(sorted(set(missing)))}")
    position_close = close[tickers].dropna(how="any")
    if len(position_close) < 90:
        raise RuntimeError("insufficient aligned price history for holdings")
    returns = position_close.pct_change().dropna(how="any")
    if len(returns) < 60:
        raise RuntimeError("insufficient daily returns for holdings")
    weights = pd.Series({p.ticker.strip().upper(): float(p.weight) for p in portfolio.positions})
    port = returns.mul(weights, axis=1).sum(axis=1)
    return returns, port


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


def _factor_outputs(close: pd.DataFrame, portfolio_returns: pd.Series) -> tuple[dict[str, float], dict[str, float]]:
    all_returns = close.pct_change().dropna(how="any")
    loadings: dict[str, float] = {}
    raw_contrib: dict[str, float] = {}
    for name, ticker in _FACTOR_TICKERS.items():
        if ticker not in all_returns.columns:
            continue
        b = _beta(portfolio_returns, all_returns[ticker])
        key = f"beta_{name}"
        loadings[key] = round(b, 4)
        raw_contrib[key] = abs(b) * float(all_returns[ticker].var())
    denom = sum(raw_contrib.values())
    if denom <= 0:
        contrib = {k: 0.0 for k in loadings}
    else:
        contrib = {k: round(v / denom, 4) for k, v in raw_contrib.items()}
    return loadings, contrib


def _marginal_risk(returns: pd.DataFrame, portfolio: Portfolio) -> dict[str, float]:
    cov = returns.cov()
    ordered = [p.ticker.upper() for p in portfolio.positions]
    weights = pd.Series([float(p.weight) for p in portfolio.positions], index=ordered)
    mw = cov.dot(weights)
    port_var = float(weights.dot(mw))
    if port_var <= 0:
        raise RuntimeError("portfolio variance is non-positive")
    signed = {t: float(weights[t] * mw[t] / port_var) for t in ordered}
    total = sum(abs(v) for v in signed.values())
    if total <= 0:
        return {t: 0.0 for t in ordered}
    return {t: round(abs(v) / total, 4) for t, v in signed.items()}


def _top5_concentration(portfolio: Portfolio) -> float:
    ws = sorted((abs(p.weight) for p in portfolio.positions), reverse=True)
    return sum(ws[:5])


def _cluster_overlap(returns: pd.DataFrame) -> list[str]:
    corr = returns.corr()
    out: list[str] = []
    cols = list(corr.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1 :]:
            c = float(corr.loc[a, b])
            if c >= 0.8:
                out.append(f"{a}/{b} correlation {c:.2f}")
    return out[:8]


def _stress_scenarios(
    returns: pd.DataFrame,
    portfolio_returns: pd.Series,
    portfolio: Portfolio,
) -> tuple[list[ScenarioLoss], WorstScenario | None]:
    def _most_affected_positions(slice_pos: pd.DataFrame) -> list[str]:
        if slice_pos.empty:
            return _top_tickers_by_weight(portfolio, 4)
        contribution: dict[str, float] = {}
        for p in portfolio.positions:
            t = p.ticker.upper()
            if t not in slice_pos.columns:
                continue
            contribution[t] = abs(float(p.weight) * float((1.0 + slice_pos[t]).prod() - 1.0))
        ranked = sorted(contribution, key=lambda t: contribution[t], reverse=True)
        return ranked[:4] if ranked else _top_tickers_by_weight(portfolio, 4)

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
            rolling_growth = (1.0 + portfolio_returns).rolling(window).apply(lambda x: float(x.prod()))
            rolling_loss = rolling_growth - 1.0
            worst_end = rolling_loss.idxmin()
            if pd.isna(worst_end):
                continue
            worst_loss_pct = float(rolling_loss.loc[worst_end]) * 100.0
            end_loc = portfolio_returns.index.get_loc(worst_end)
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
    for label, start, end in _HISTORICAL_SCENARIOS:
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
            "historical stress windows outside available history; using worst available rolling windows"
        )
        scenarios = _fallback_windows()
    if not scenarios:
        raise RuntimeError("no stress scenarios could be computed from available data")
    worst = min(scenarios, key=lambda s: s.estimated_portfolio_loss_pct)
    return scenarios, WorstScenario(
        name=worst.scenario,
        estimated_portfolio_loss_pct=worst.estimated_portfolio_loss_pct,
    )


def _top_tickers_by_weight(portfolio: Portfolio, n: int) -> list[str]:
    ranked = sorted(portfolio.positions, key=lambda p: abs(p.weight), reverse=True)
    return [p.ticker.upper() for p in ranked[:n]]


def _concentration_score(top5_weight: float) -> int:
    """0-100 where higher means more concentrated."""
    return max(0, min(100, int(round(top5_weight * 100))))


def _risk_score(portfolio_returns: pd.Series, top5: float) -> int:
    ann_vol = float(portfolio_returns.std()) * sqrt(252.0)
    vol_component = min(1.0, ann_vol / 0.45)
    concentration_component = min(1.0, top5)
    raw = 1.0 + 9.0 * (0.65 * vol_component + 0.35 * concentration_component)
    return max(1, min(10, int(round(raw))))


def compute_risk_review_base(portfolio: Portfolio, _md=None) -> RiskReview:
    all_tickers = [p.ticker.upper() for p in portfolio.positions] + list(_FACTOR_TICKERS.values())
    close = _download_close_frame(all_tickers)
    returns, port_returns = _portfolio_returns(close, portfolio)
    loadings, fr_contrib = _factor_outputs(close, port_returns)
    marginal = _marginal_risk(returns, portfolio)
    scenarios, worst = _stress_scenarios(returns, port_returns, portfolio)
    top5 = _top5_concentration(portfolio)
    concentration_score = _concentration_score(top5)
    clusters = _cluster_overlap(returns)
    rs = _risk_score(port_returns, top5)
    liq_notes: list[str] = []

    return RiskReview(
        factor_loadings=loadings,
        factor_risk_contribution=fr_contrib,
        marginal_risk_by_ticker=marginal,
        exposure_links=[],
        concentration_issues=(
            [
                f"Top 5 names ≈ {top5 * 100:.0f}% of portfolio",
                f"Concentration score: {concentration_score}/100",
            ]
            if top5 > 0.55
            else [f"Concentration score: {concentration_score}/100"]
        ),
        concentration_top5_pct=round(top5, 4),
        liquidity_notes=liq_notes[:6],
        scenario_losses=scenarios,
        top_risks=[],
        worst_scenario=worst,
        hidden_concentration=clusters,
        fragilities=[],
        risk_score=rs,
        summary="",
    )


def format_risk_python_block(base: RiskReview) -> str:
    lines = [
        "=== PYTHON RISK ENGINE (authoritative numbers — add interpretation only) ===",
        "",
        "factor_loadings (real-data betas): "
        + ", ".join(f"{k}={v:.2f}" for k, v in sorted(base.factor_loadings.items())),
        "marginal_risk_by_ticker (sums to 1): "
        + ", ".join(f"{k}={v:.2f}" for k, v in sorted(base.marginal_risk_by_ticker.items())[:12]),
        f"concentration_top5_pct: {base.concentration_top5_pct:.2f}",
        (
            next(
                (x for x in base.concentration_issues if x.startswith("Concentration score:")),
                "Concentration score: n/a",
            )
        ),
        f"worst_scenario (engine): {base.worst_scenario.name if base.worst_scenario else 'n/a'} "
        f"({base.worst_scenario.estimated_portfolio_loss_pct:.2f}%)"
        if base.worst_scenario
        else "worst_scenario: n/a",
    ]
    if base.hidden_concentration:
        lines.append("hidden_concentration: " + "; ".join(base.hidden_concentration))
    return "\n".join(lines)
