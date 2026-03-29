"""Theme agent — parallel, runs after news agent."""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from port.config import make_llm
from port.portfolio import news_to_text, portfolio_to_text
from port.prompts import THEME_SYSTEM_PROMPT
from port.state import GraphState, ThemeReview


def theme_node(state: GraphState) -> dict:
    portfolio = state["portfolio"]
    news = state["news_review"]
    llm = make_llm(max_tokens=1500)
    structured_llm = llm.with_structured_output(ThemeReview)

    result: ThemeReview = structured_llm.invoke([
        SystemMessage(content=THEME_SYSTEM_PROMPT),
        HumanMessage(content=(
            f"Portfolio to review:\n\n{portfolio_to_text(portfolio)}\n\n"
            f"{news_to_text(news)}"
        )),
    ])

    return {"theme_results": [result]}
