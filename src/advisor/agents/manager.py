from __future__ import annotations

import json
import logging
import time

from langchain_core.messages import HumanMessage, SystemMessage

from advisor.config import config
from advisor.llm.context import report_step
from advisor.llm.structured import invoke_structured
from advisor.prompts import manager_system_prompt
from advisor.prompts.manager import (
    allocation_to_manager_text,
    investor_profile_text,
    manager_conversation_system_prompt,
    regime_to_manager_text,
    risk_to_manager_text,
    theme_to_manager_text,
)
from advisor.prompts.news import news_to_text
from advisor.prompts.portfolio import portfolio_to_text
from advisor.schemas.manager import ManagerReply, ManagerReview
from advisor.schemas.state import GraphState

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
        investor_profile_text(),
    ]
    return "\n\n".join(section for section in sections if section)


def conversation_turn_text(index: int, turn: dict) -> str:
    reply = turn["reply"]
    lines = [f"Turn {index} - User: {turn['user_message']}", f"Manager: {reply['answer']}"]
    for adjustment in reply["suggested_adjustments"]:
        lines.append(
            f"  Suggested {adjustment['action_type']} {adjustment['position']}: "
            f"{adjustment['rationale']}"
        )
    return "\n".join(lines)


def build_manager_conversation_prompt(
    state: GraphState,
    *,
    decision: dict,
    previous_turns: list[dict],
    user_message: str,
) -> str:
    answered = [turn for turn in previous_turns if turn["status"] == "done"]
    history = [conversation_turn_text(index, turn) for index, turn in enumerate(answered, start=1)]
    sections = [
        build_manager_prompt(state),
        "=== YOUR DECISION ===\n" + json.dumps(decision, ensure_ascii=False, indent=2),
        "=== CONVERSATION SO FAR ===\n" + ("\n\n".join(history) if history else "(none)"),
        "=== CURRENT USER MESSAGE ===\n" + user_message,
    ]
    return "\n\n".join(sections)


def run_manager_reply(human_msg: str) -> ManagerReply:
    return invoke_structured(  # type: ignore[return-value]
        ManagerReply,
        [
            SystemMessage(content=manager_conversation_system_prompt()),
            HumanMessage(content=human_msg),
        ],
        agent="manager",
        max_tokens=config.llm.structured_max_tokens,
        temperature=config.llm.structured_temperature,
        use_agent_model=True,
    )


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
