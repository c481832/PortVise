"""Validation agent — fan-in, synthesises all four upstream reports."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from port.config import make_llm
from port.models import (
    NewsReview,
    RegimeReview,
    RiskReview,
    ThemeReview,
    ValidationReview,
)
from port.portfolio import news_to_text, portfolio_to_text, render_regime, render_risk, render_theme
from port.prompts import VALIDATION_SYSTEM_PROMPT

if TYPE_CHECKING:
    from port.state import GraphState


def build_validation_human_message(
    portfolio,
    news: NewsReview,
    risk: RiskReview,
    regime: RegimeReview,
    theme: ThemeReview,
) -> str:
    return "\n\n".join(
        [
            f"ORIGINAL PORTFOLIO:\n{portfolio_to_text(portfolio)}",
            news_to_text(news),
            render_risk(risk),
            render_regime(regime),
            render_theme(theme),
            "Synthesise the above into a ValidationReview."
            " Elevate disagreements and thesis breaks.",
        ]
    )


def validation_node(state: GraphState) -> dict:
    portfolio = state["portfolio"]
    news = state["news_review"]
    risk = state["risk_results"][0]
    regime = state["regime_results"][0]
    theme = state["theme_results"][0]

    llm = make_llm(max_tokens=4096)
    structured_llm = llm.with_structured_output(ValidationReview)

    human_msg = build_validation_human_message(portfolio, news, risk, regime, theme)  # type: ignore[arg-type]

    result: ValidationReview = structured_llm.invoke(  # type: ignore[assignment]
        [
            SystemMessage(content=VALIDATION_SYSTEM_PROMPT),
            HumanMessage(content=human_msg),
        ]
    )

    return {"validation_review": result}
