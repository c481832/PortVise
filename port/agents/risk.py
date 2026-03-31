"""Risk agent — parallel, runs after news agent."""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from port.config import make_llm
from port.portfolio import market_data_to_text, news_to_text, portfolio_to_text
from port.prompts import RISK_SYSTEM_PROMPT
from port.state import GraphState, RiskReview


def risk_node(state: GraphState) -> dict:
    portfolio = state["portfolio"]
    news = state["news_review"]
    market_data = state["market_data"]
    llm = make_llm(max_tokens=4096)
    structured_llm = llm.with_structured_output(RiskReview)

    content = (
        f"Portfolio to review:\n\n{portfolio_to_text(portfolio)}\n\n"
        f"{news_to_text(news)}"
    )
    if market_data:
        content += f"\n\n{market_data_to_text(market_data)}"

    result: RiskReview = structured_llm.invoke([
        SystemMessage(content=RISK_SYSTEM_PROMPT),
        HumanMessage(content=content),
    ])

    return {"risk_results": [result]}
