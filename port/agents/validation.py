"""Validation agent — fan-in, synthesises all four upstream reports."""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from port.config import make_llm
from port.portfolio import news_to_text, portfolio_to_text
from port.prompts import VALIDATION_SYSTEM_PROMPT
from port.state import (
    GraphState,
    NewsReview,
    RegimeReview,
    RiskReview,
    ThemeReview,
    ValidationReview,
)


def _render_risk(r: RiskReview) -> str:
    lines = [f"=== RISK REPORT (risk score: {r.risk_score}/10) ==="]
    lines.append(f"Summary: {r.summary}")
    if r.factor_exposures:
        lines.append("Factor exposures:")
        for fe in r.factor_exposures:
            lines.append(f"  - {fe.factor} ({fe.direction}, {fe.magnitude}): {', '.join(fe.positions_driving)}")
    if r.concentration_issues:
        lines.append("Concentration issues: " + "; ".join(r.concentration_issues))
    if r.scenario_losses:
        lines.append("Scenario losses:")
        for s in r.scenario_losses:
            lines.append(f"  - {s.scenario}: {s.estimated_portfolio_loss_pct:+.1f}%")
    if r.fragilities:
        lines.append("Fragilities: " + "; ".join(r.fragilities))
    return "\n".join(lines)


def _render_regime(r: RegimeReview) -> str:
    lines = [
        f"=== REGIME REPORT (fit score: {r.portfolio_fit_score}/10, "
        f"regime confidence: {r.regime_confidence}/10) ===",
        f"Regime: {r.current_regime}",
        f"Summary: {r.summary}",
    ]
    if r.mismatches:
        lines.append("Mismatches: " + "; ".join(r.mismatches))
    if r.regime_appropriate_tilts:
        lines.append("Appropriate tilts: " + "; ".join(r.regime_appropriate_tilts))
    return "\n".join(lines)


def _render_theme(t: ThemeReview) -> str:
    lines = [f"=== THEME REPORT (alignment score: {t.alignment_score}/10) ==="]
    lines.append(f"Summary: {t.summary}")
    if t.theme_alignments:
        lines.append("Theme alignments:")
        for ta in t.theme_alignments:
            lines.append(f"  - {ta.theme}: {ta.portfolio_stance} ({', '.join(ta.relevant_positions)})")
    if t.crowding_risks:
        lines.append("Crowding risks: " + "; ".join(t.crowding_risks))
    if t.momentum_conflicts:
        lines.append("Momentum conflicts: " + "; ".join(t.momentum_conflicts))
    return "\n".join(lines)


def build_validation_human_message(
    portfolio,
    news: NewsReview,
    risk: RiskReview,
    regime: RegimeReview,
    theme: ThemeReview,
) -> str:
    return "\n\n".join([
        f"ORIGINAL PORTFOLIO:\n{portfolio_to_text(portfolio)}",
        news_to_text(news),
        _render_risk(risk),
        _render_regime(regime),
        _render_theme(theme),
        "Synthesise the above into a ValidationReview. Elevate disagreements and thesis breaks.",
    ])


def validation_node(state: GraphState) -> dict:
    portfolio = state["portfolio"]
    news = state["news_review"]
    risk = state["risk_results"][0]
    regime = state["regime_results"][0]
    theme = state["theme_results"][0]

    llm = make_llm()
    structured_llm = llm.with_structured_output(ValidationReview)

    human_msg = build_validation_human_message(portfolio, news, risk, regime, theme)

    result: ValidationReview = structured_llm.invoke([
        SystemMessage(content=VALIDATION_SYSTEM_PROMPT),
        HumanMessage(content=human_msg),
    ])

    return {"validation_review": result}
