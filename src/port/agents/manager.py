"""Manager agent — final action list from specialist reports after validation gate."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from port.config import config, invoke_structured
from port.config import step_callback as _step_cb
from port.models import ManagerReview
from port.portfolio import news_to_text, portfolio_to_text
from port.prompts import manager_system_prompt

if TYPE_CHECKING:
    from port.state import GraphState

log = logging.getLogger(__name__)


def _first(items, *, limit: int):
    return list(items[:limit])


def _append_list(lines: list[str], label: str, items, *, limit: int) -> None:
    selected = _first(items, limit=limit)
    if selected:
        lines.append(f"{label}: " + "; ".join(str(item) for item in selected))


def _render_manager_risk(r) -> str:
    p = config.prompts.manager
    lines = ["=== RISK REPORT (MANAGER COMPACT) ===", f"Summary: {r.summary}"]
    if r.worst_scenario:
        lines.append(
            f"Worst scenario: {r.worst_scenario.name} "
            f"({r.worst_scenario.estimated_portfolio_loss_pct:+.2f}%)"
        )
    if r.marginal_risk_by_ticker:
        ranked = sorted(
            r.marginal_risk_by_ticker.items(),
            key=lambda item: abs(item[1]),
            reverse=True,
        )
        selected = _first(ranked, limit=p.marginal_risk_tickers_max)
        lines.append("Largest marginal risks: " + ", ".join(f"{k}={v:.1%}" for k, v in selected))
    _append_list(lines, "Top risks", r.top_risks, limit=p.top_risks_max)
    _append_list(
        lines,
        "Concentration issues",
        r.concentration_issues,
        limit=p.concentration_issues_max,
    )
    _append_list(
        lines,
        "Hidden concentration",
        r.hidden_concentration,
        limit=p.hidden_concentration_max,
    )
    if r.scenario_losses:
        selected = _first(r.scenario_losses, limit=p.scenario_losses_max)
        lines.append(
            "Scenario losses: "
            + "; ".join(f"{s.scenario}: {s.estimated_portfolio_loss_pct:+.1f}%" for s in selected)
        )
    return "\n".join(lines)


def _render_manager_regime(r) -> str:
    p = config.prompts.manager
    sv = r.state_vector
    lines = [
        "=== REGIME REPORT (MANAGER COMPACT) ===",
        f"Regime: {r.current_regime}",
        (
            f"State vector: inflation {sv.inflation_trend}, rates {sv.rates_trend}, "
            f"growth {sv.growth_trend}, liquidity {sv.liquidity}, vol {sv.volatility}"
        ),
        f"Summary: {r.summary}",
    ]
    ho = r.historical_outcome
    lines.append(
        "Historical analogs: "
        f"periods={ho.analog_periods_identified}, avg_return={ho.avg_return}, "
        f"max_drawdown={ho.max_drawdown}, win_rate={ho.win_rate}; {ho.message}"
    )
    for period in _first(ho.top_similar_periods, limit=p.regime_analogs_max):
        lines.append(
            f"  - {period.period} -> {period.forward_window}: "
            f"return {period.portfolio_return:+.1%}, max drawdown {period.max_drawdown:+.1%}"
        )
    _append_list(lines, "Mismatch drivers", r.mismatch_drivers, limit=p.regime_mismatch_drivers_max)
    _append_list(lines, "Appropriate tilts", r.regime_appropriate_tilts, limit=p.regime_tilts_max)
    return "\n".join(lines)


def _render_manager_theme(t) -> str:
    p = config.prompts.manager
    lines = ["=== THEME REPORT (MANAGER COMPACT) ==="]
    if t.implicit_portfolio_bet:
        lines.append(f"Implicit bet: {t.implicit_portfolio_bet}")
    lines.append(f"Summary: {t.summary}")
    syn = t.synthesis
    _append_list(lines, "Dominant themes", syn.dominant_themes, limit=p.theme_list_items_max)
    _append_list(
        lines,
        "Redundant expressions",
        syn.redundant_expressions,
        limit=p.theme_list_items_max,
    )
    _append_list(lines, "Missing exposures", syn.missing_exposures, limit=p.theme_list_items_max)
    if t.theme_assessments:
        lines.append("Theme assessments:")
        for assessment in _first(t.theme_assessments, limit=p.theme_assessments_max):
            lines.append(
                f"  - {assessment.theme} ({', '.join(assessment.supporting_assets)}): "
                f"{assessment.assessment} Implication: {assessment.implication}"
            )
    _append_list(lines, "Crowding risks", t.crowding_risks, limit=p.theme_list_items_max)
    _append_list(lines, "Momentum conflicts", t.momentum_conflicts, limit=p.theme_list_items_max)
    return "\n".join(lines)


def _render_inherited_feedback(state: GraphState) -> str:
    items = state.get("inherited_feedback") or []
    comments = [
        str(item.get("comment") or "").strip()
        for item in items
        if isinstance(item, dict) and str(item.get("comment") or "").strip()
    ]
    if not comments:
        return ""
    return "\n".join(
        [
            "=== CARRIED-FORWARD USER GUIDANCE ===",
            *[f"- {comment}" for comment in comments],
            (
                "Address this guidance in the decision, but treat it as user preference and "
                "constraints, not as market evidence. Upstream facts remain authoritative."
            ),
        ]
    )


def build_manager_human_message(state: GraphState) -> str:
    portfolio = state["portfolio"]
    news = state["news_review"]
    risk = state["risk_results"][-1]
    regime = state["regime_results"][-1]
    theme = state["theme_results"][-1]
    validation = state["validation_review"]
    if validation is None:
        raise ValueError("manager requires validation_review before generating actions")

    required_tickers = ", ".join(p.ticker.upper() for p in portfolio.positions)
    return "\n\n".join(
        [
            f"ORIGINAL PORTFOLIO:\n{portfolio_to_text(portfolio)}",
            (
                "REQUIRED POSITION ACTION COVERAGE:\n"
                "Every current holding must have its own position-level action, with position "
                f"set to the exact single ticker: {required_tickers}."
            ),
            news_to_text(news),
            _render_manager_risk(risk),
            _render_manager_regime(regime),
            _render_manager_theme(theme),
            _render_inherited_feedback(state),
            "Based on all of the above, generate a ManagerReview with concrete actions.",
        ]
    )


def build_manager_feedback_human_message(
    state: GraphState,
    *,
    user_comment: str,
    previous_rounds: list[dict] | None = None,
) -> str:
    previous = []
    for index, round_ in enumerate(previous_rounds or [], start=1):
        comment = str(round_.get("user_comment") or "").strip()
        status = str(round_.get("status") or "").strip()
        if comment:
            previous.append(f"Round {index} ({status or 'done'}): {comment}")

    feedback_block = [
        "=== USER FEEDBACK FOR MANAGER RERUN ===",
        "Revise the ManagerReview in response to the user's comment below.",
        "Use the same upstream portfolio, news, risk, regime, theme, and validation inputs.",
        "Do not invent new market data or new upstream findings.",
    ]
    if previous:
        feedback_block.extend(["Prior feedback rounds:", *previous])
    feedback_block.extend(
        [
            "Current user comment:",
            user_comment,
            "Return a complete revised ManagerReview with the same schema.",
        ]
    )
    return "\n\n".join([build_manager_human_message(state), "\n".join(feedback_block)])


def _validate_action_coverage(result: ManagerReview, state: GraphState) -> None:
    expected = {p.ticker.upper() for p in state["portfolio"].positions}
    covered = {
        action.position.strip().upper()
        for action in result.actions
        if action.scope == "position" and action.position.strip()
    }
    missing = sorted(expected - covered)
    if missing:
        raise ValueError(
            "manager action plan missing position-level coverage for: " + ", ".join(missing)
        )


def run_manager_review(state: GraphState, human_msg: str) -> ManagerReview:
    result: ManagerReview = invoke_structured(  # type: ignore[assignment]
        ManagerReview,
        [SystemMessage(content=manager_system_prompt()), HumanMessage(content=human_msg)],
        agent="manager",
    )
    _validate_action_coverage(result, state)
    return result


def manager_node(state: GraphState) -> dict:
    t0 = time.monotonic()
    log.info("started")
    _cb = _step_cb.get(None)
    if _cb:
        _cb("manager", 0, "Building final decision packet…")
    human_msg = build_manager_human_message(state)

    if _cb:
        _cb("manager", 1, "Generating prioritized action plan…")

    result = run_manager_review(state, human_msg)
    if _cb:
        _cb("manager", 2, "Finalizing decision memo…")
    log.info("done in %.1fs", time.monotonic() - t0)
    return {"manager_review": result}
