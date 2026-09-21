"""Render specialist agent reviews as prompt text, including the authoritative
Python-engine blocks the risk and regime agents prepend to their prompts."""

from __future__ import annotations

from port.models.regime import RegimeReview
from port.models.risk import RiskReview
from port.models.theme import ThemeReview
from port.models.validation import ValidationReview


def render_risk(r: RiskReview) -> str:
    lines = ["=== RISK REPORT ==="]
    lines.append(f"Summary: {r.summary}")
    if r.factor_loadings:
        lines.append(
            "Factor loadings (engine): "
            + ", ".join(f"{k}={v:+.2f}" for k, v in r.factor_loadings.items())
        )
    if r.marginal_risk_by_ticker:
        lines.append(
            "Marginal risk by ticker (cash-aware): "
            + ", ".join(f"{k}={v:.1%}" for k, v in r.marginal_risk_by_ticker.items())
        )
    if r.top_risks:
        lines.append("Top risks: " + "; ".join(r.top_risks))
    if r.worst_scenario:
        lines.append(
            f"Worst scenario (engine): {r.worst_scenario.name} "
            f"({r.worst_scenario.estimated_portfolio_loss_pct:+.2f}%)"
        )
    if r.hidden_concentration:
        lines.append("Hidden concentration: " + "; ".join(r.hidden_concentration))
    if r.concentration_issues:
        lines.append("Concentration issues: " + "; ".join(r.concentration_issues))
    if r.scenario_losses:
        lines.append("Scenario losses:")
        for s in r.scenario_losses:
            lines.append(f"  - {s.scenario}: {s.estimated_portfolio_loss_pct:+.1f}%")
    return "\n".join(lines)

def render_regime(r: RegimeReview) -> str:
    sv = r.state_vector
    lines = [
        "=== REGIME REPORT ===",
        f"Regime: {r.current_regime}",
        (
            f"State vector: inflation {sv.inflation_trend}, rates {sv.rates_trend}, "
            f"growth {sv.growth_trend}, liquidity {sv.liquidity}, vol {sv.volatility}"
        ),
        f"Summary: {r.summary}",
    ]
    ho = r.historical_outcome
    lines.append(f"Historical analogs: {ho.message}")
    for period in ho.top_similar_periods:
        ret = f"{period.portfolio_return:+.1%}"
        drawdown = f"{period.max_drawdown:+.1%}"
        lines.append(
            f"  - {period.period} -> {period.forward_window}: return {ret}, max drawdown {drawdown}"
        )
    if r.mismatch_drivers:
        lines.append("Mismatch drivers: " + "; ".join(r.mismatch_drivers))
    if r.regime_appropriate_tilts:
        lines.append("Appropriate tilts: " + "; ".join(r.regime_appropriate_tilts))
    return "\n".join(lines)

def render_theme(t: ThemeReview) -> str:
    lines = ["=== THEME REPORT ==="]
    if t.implicit_portfolio_bet:
        lines.append(f"Implicit bet: {t.implicit_portfolio_bet}")
    lines.append(f"Summary: {t.summary}")
    if t.theme_assessments:
        lines.append("Theme assessments:")
        for assessment in t.theme_assessments:
            lines.append(
                f"  - {assessment.theme}: {assessment.assessment} "
                f"({', '.join(assessment.supporting_assets)})"
            )
            if assessment.implication:
                lines.append(f"    Implication: {assessment.implication}")
    syn = t.synthesis
    if syn.dominant_themes:
        lines.append("Dominant themes: " + "; ".join(syn.dominant_themes))
    if syn.redundant_expressions:
        lines.append("Redundant expressions: " + "; ".join(syn.redundant_expressions))
    if syn.missing_exposures:
        lines.append("Missing exposures: " + "; ".join(syn.missing_exposures))
    if syn.theme_drift_note:
        lines.append(f"Theme drift: {syn.theme_drift_note}")
    if t.crowding_risks:
        lines.append("Crowding risks: " + "; ".join(t.crowding_risks))
    if t.momentum_conflicts:
        lines.append("Momentum conflicts: " + "; ".join(t.momentum_conflicts))
    return "\n".join(lines)

def render_validation(v: ValidationReview) -> str:
    return f"=== VALIDATION ===\nSummary: {v.summary}"

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

def format_regime_python_block(base: RegimeReview) -> str:
    sv = base.state_vector
    h = base.historical_outcome
    lines = [
        "=== PYTHON REGIME SIGNALS (authoritative — you refine wording only in summary/tilts) ===",
        "",
        f"current_regime: {base.current_regime}",
        f"state_vector: inflation={sv.inflation_trend}, rates={sv.rates_trend}, "
        f"growth={sv.growth_trend}, liquidity={sv.liquidity}, volatility={sv.volatility}",
    ]
    if h.runner_available:
        avg = f"{h.avg_return:+.2%}" if h.avg_return is not None else "n/a"
        dd = f"{h.max_drawdown:+.2%}" if h.max_drawdown is not None else "n/a"
        wr = f"{h.win_rate:.0%}" if h.win_rate is not None else "n/a"
        lines.append(
            f"historical_outcome: runner_available=True, "
            f"analog_periods={h.analog_periods_identified}, "
            f"avg_return={avg}, max_drawdown={dd}, win_rate={wr}"
        )
        for idx, period in enumerate(h.top_similar_periods, start=1):
            ret = f"{period.portfolio_return:+.2%}"
            drawdown = f"{period.max_drawdown:+.2%}"
            lines.append(
                f"analog_{idx}: period={period.period}, forward_window={period.forward_window}, "
                f"portfolio_return={ret}, max_drawdown={drawdown}, "
                f"match_score={period.match_score}"
            )
    else:
        lines.append("historical_outcome: runner_available=False")
    lines += [
        h.message,
        "",
        "Explain mismatch drivers and tilts in plain language; "
        "do not contradict the state_vector labels.",
    ]
    return "\n".join(lines)
