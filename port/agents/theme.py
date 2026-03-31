"""Theme agent — parallel, runs after news agent."""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from port.config import make_llm
from port.portfolio import market_data_to_text, news_to_text, portfolio_to_text
from port.prompts import THEME_SYSTEM_PROMPT
from port.models import ThemeReview
from port.state import GraphState


def theme_node(state: GraphState) -> dict:
    portfolio = state["portfolio"]
    news = state["news_review"]
    market_data = state["market_data"]
    llm = make_llm(max_tokens=4096)
    structured_llm = llm.with_structured_output(ThemeReview)

    content = (
        f"Portfolio to review:\n\n{portfolio_to_text(portfolio)}\n\n"
        f"{news_to_text(news)}"
    )
    if market_data:
        content += f"\n\n{market_data_to_text(market_data)}"

    result: ThemeReview = structured_llm.invoke([
        SystemMessage(content=THEME_SYSTEM_PROMPT),
        HumanMessage(content=content),
    ])

    return {"theme_results": [result]}
