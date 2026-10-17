from __future__ import annotations

import logging
import time

from langchain_core.messages import HumanMessage, SystemMessage

from advisor.config import config
from advisor.llm.context import report_step
from advisor.llm.structured import invoke_structured
from advisor.prompts import manager_system_prompt
from advisor.prompts.manager import (
    allocation_to_manager_text,
    regime_to_manager_text,
    risk_to_manager_text,
    theme_to_manager_text,
)
from advisor.prompts.news import news_to_text
from advisor.prompts.portfolio import portfolio_to_text
from advisor.schemas.manager import ManagerReview
from advisor.schemas.state import GraphState
from advisor.util import format_inherited_feedback

log = logging.getLogger(__name__)


def build_manager_prompt(state: GraphState) -> str:
    portfolio = state["portfolio"]
    news = state["news_review"]
    risk = state["risk_review"]
    regime = state["regime_review"]
    theme = state["theme_review"]
    allocation = state["allocation_review"]
    if news is None or risk is None or regime is None or theme is None or allocation is None:
        raise ValueError("manager requires news, risk, regime, theme, and allocation reviews")

    required_tickers = ", ".join(p.ticker for p in portfolio.positions)
    sections = [
        f"ORIGINAL PORTFOLIO:\n{portfolio_to_text(portfolio)}",
        f"REQUIRED POSITION ACTION COVERAGE: {required_tickers}",
        news_to_text(news),
        allocation_to_manager_text(allocation),
        risk_to_manager_text(risk),
        regime_to_manager_text(regime),
        theme_to_manager_text(theme),
        format_inherited_feedback(
            state.get("inherited_feedback") or [],
            heading="=== CARRIED-FORWARD USER GUIDANCE ===",
        ),
    ]
    return "\n\n".join(section for section in sections if section)


def build_manager_feedback_prompt(
    state: GraphState,
    *,
    user_comment: str,
    previous_rounds: list[dict] | None,
) -> str:
    previous = []
    for index, round_ in enumerate(previous_rounds or [], start=1):
        comment = str(round_.get("user_comment") or "").strip()
        status = str(round_.get("status") or "").strip()
        if comment:
            previous.append(f"Round {index} ({status or 'done'}): {comment}")

    feedback_block = ["=== USER FEEDBACK FOR MANAGER RERUN ==="]
    if previous:
        feedback_block.extend(["Prior feedback rounds:", *previous])
    feedback_block.extend(["Current user comment:", user_comment])
    return "\n\n".join([build_manager_prompt(state), "\n".join(feedback_block)])


def validate_action_coverage(result: ManagerReview, state: GraphState) -> None:
    expected = {p.ticker for p in state["portfolio"].positions}
    covered = {
        (action.position or "").strip().upper()
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
        max_tokens=config.llm.structured_max_tokens,
        temperature=config.llm.structured_temperature,
        use_agent_model=True,
    )
    validate_action_coverage(result, state)
    return result


def manager_node(state: GraphState) -> dict:
    t0 = time.monotonic()
    log.info("started")
    report_step("manager", 0, "Building final decision packet…")
    human_msg = build_manager_prompt(state)

    report_step("manager", 1, "Generating prioritized action plan…")

    result = run_manager_review(state, human_msg)
    report_step("manager", 2, "Finalizing decision memo…")
    log.info("done in %.1fs", time.monotonic() - t0)
    return {"manager_review": result}
