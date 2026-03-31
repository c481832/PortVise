"""Planner/PM agent — final action generator."""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from port.config import make_llm
from port.portfolio import news_to_text, portfolio_to_text
from port.prompts import PLANNER_SYSTEM_PROMPT
from port.state import (
    GraphState,
    PlannerReview,
    ValidationReview,
)


def _render_validation(v: ValidationReview) -> str:
    lines = [f"=== VALIDATION SYNTHESIS (confidence score: {v.confidence_score}/10) ==="]
    lines.append(f"Summary: {v.summary}")
    if v.critical_issues:
        lines.append("Critical issues:")
        for ci in v.critical_issues:
            lines.append(
                f"  [{ci.severity.upper()}] {ci.issue} "
                f"(positions: {', '.join(ci.affected_positions)}; "
                f"flagged by: {', '.join(ci.source_agents)})"
            )
    if v.thesis_breaks:
        lines.append("Thesis breaks: " + "; ".join(v.thesis_breaks))
    if v.internal_contradictions:
        lines.append("Internal contradictions: " + "; ".join(v.internal_contradictions))
    return "\n".join(lines)


def build_planner_human_message(state: GraphState) -> str:
    portfolio = state["portfolio"]
    news = state["news_review"]
    risk = state["risk_results"][0]
    regime = state["regime_results"][0]
    theme = state["theme_results"][0]
    validation = state["validation_review"]

    from port.agents.validation import _render_risk, _render_regime, _render_theme

    return "\n\n".join([
        f"ORIGINAL PORTFOLIO:\n{portfolio_to_text(portfolio)}",
        news_to_text(news),
        _render_risk(risk),
        _render_regime(regime),
        _render_theme(theme),
        _render_validation(validation),
        "Based on all of the above, generate a PlannerReview with concrete actions.",
    ])


def planner_node(state: GraphState) -> dict:
    llm = make_llm(max_tokens=4096)
    structured_llm = llm.with_structured_output(PlannerReview)

    human_msg = build_planner_human_message(state)

    result: PlannerReview = structured_llm.invoke([
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=human_msg),
    ])

    return {"planner_review": result}
