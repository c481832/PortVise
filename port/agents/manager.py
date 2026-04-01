"""Manager agent — final action list from validation + specialist reports."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from port.config import make_llm
from port.models import ManagerReview
from port.portfolio import (
    news_to_text,
    portfolio_to_text,
    render_regime,
    render_risk,
    render_theme,
    render_validation,
)
from port.prompts import MANAGER_SYSTEM_PROMPT

if TYPE_CHECKING:
    from port.state import GraphState


def build_manager_human_message(state: GraphState) -> str:
    portfolio = state["portfolio"]
    news = state["news_review"]
    risk = state["risk_results"][0]
    regime = state["regime_results"][0]
    theme = state["theme_results"][0]
    validation = state["validation_review"]

    return "\n\n".join(
        [
            f"ORIGINAL PORTFOLIO:\n{portfolio_to_text(portfolio)}",
            news_to_text(news),
            render_risk(risk),
            render_regime(regime),
            render_theme(theme),
            render_validation(validation) if validation is not None else "",
            "Based on all of the above, generate a ManagerReview with concrete actions.",
        ]
    )


def manager_node(state: GraphState) -> dict:
    llm = make_llm(max_tokens=4096)
    structured_llm = llm.with_structured_output(ManagerReview)

    human_msg = build_manager_human_message(state)

    result: ManagerReview = structured_llm.invoke(  # type: ignore[assignment]
        [
            SystemMessage(content=MANAGER_SYSTEM_PROMPT),
            HumanMessage(content=human_msg),
        ]
    )

    return {"manager_review": result}
