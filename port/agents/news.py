"""News agent — first to run, scans macro/market/position-level context."""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from port.config import make_llm
from port.portfolio import market_data_to_text, portfolio_to_text
from port.prompts import NEWS_SYSTEM_PROMPT
from port.models import NewsReview
from port.state import GraphState


def news_node(state: GraphState) -> dict:
    portfolio = state["portfolio"]
    market_data = state["market_data"]
    llm = make_llm(max_tokens=4096)
    structured_llm = llm.with_structured_output(NewsReview)

    content = (
        f"Prepare a market briefing for the following portfolio:\n\n"
        f"{portfolio_to_text(portfolio)}"
    )
    if market_data:
        content += f"\n\n{market_data_to_text(market_data)}"

    result: NewsReview = structured_llm.invoke([
        SystemMessage(content=NEWS_SYSTEM_PROMPT),
        HumanMessage(content=content),
    ])

    return {"news_review": result}
