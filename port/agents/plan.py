"""Plan agent — human-in-the-loop portfolio confirmation."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt

from port.config import make_llm
from port.portfolio import Portfolio, portfolio_to_text
from port.prompts import PLAN_SYSTEM_PROMPT

if TYPE_CHECKING:
    from port.state import GraphState


def plan_node(state: GraphState) -> dict:
    """
    Present the portfolio to the user. The graph pauses here via interrupt().
    The user can reply 'ok' to proceed as-is, or describe changes.
    If changes are requested, an LLM call applies them and returns the updated portfolio.
    """
    portfolio = state["portfolio"]

    user_response: str = interrupt(
        {
            "portfolio_summary": portfolio_to_text(portfolio),
            "prompt": (
                "Review the portfolio above.\n"
                "Type 'ok' to proceed with this portfolio, "
                "or describe any changes you want to make before the review starts."
            ),
        }
    )

    if user_response.strip().lower() in ("ok", "yes", "proceed", ""):
        return {}  # no state change — portfolio unchanged

    updated = _apply_changes(portfolio, user_response)
    return {"portfolio": updated}


def _apply_changes(portfolio: Portfolio, change_description: str) -> Portfolio:
    """Use the LLM to apply natural-language change requests to the portfolio."""
    llm = make_llm(temperature=0.0)
    portfolio_json = portfolio.model_dump_json(indent=2)

    response = llm.invoke(
        [
            SystemMessage(content=PLAN_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Current portfolio (JSON):\n{portfolio_json}\n\n"
                    f"Requested change: {change_description}\n\n"
                    "Return the complete updated portfolio as JSON, with no other text."
                )
            ),
        ]
    )

    raw = str(response.content).strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    data = json.loads(raw)
    return Portfolio(**data)
