"""Regime agent — parallel, runs after news agent."""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from port.config import make_llm
from port.portfolio import market_data_to_text, news_to_text, portfolio_to_text
from port.prompts import REGIME_SYSTEM_PROMPT
from port.models import RegimeReview
from port.state import GraphState


def regime_node(state: GraphState) -> dict:
    portfolio = state["portfolio"]
    news = state["news_review"]
    market_data = state["market_data"]
    llm = make_llm(max_tokens=4096)
    structured_llm = llm.with_structured_output(RegimeReview)

    content = (
        f"Portfolio to assess:\n\n{portfolio_to_text(portfolio)}\n\n"
        f"{news_to_text(news)}"
    )
    if market_data:
        content += f"\n\n{market_data_to_text(market_data)}"

    result: RegimeReview = structured_llm.invoke([
        SystemMessage(content=REGIME_SYSTEM_PROMPT),
        HumanMessage(content=content),
    ])

    return {"regime_results": [result]}
