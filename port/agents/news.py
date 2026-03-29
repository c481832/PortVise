"""News agent — first to run, scans macro/market/position-level context."""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from port.config import make_llm
from port.portfolio import portfolio_to_text
from port.prompts import NEWS_SYSTEM_PROMPT
from port.state import GraphState, NewsReview


def news_node(state: GraphState) -> dict:
    portfolio = state["portfolio"]
    llm = make_llm()
    structured_llm = llm.with_structured_output(NewsReview)

    result: NewsReview = structured_llm.invoke([
        SystemMessage(content=NEWS_SYSTEM_PROMPT),
        HumanMessage(content=(
            f"Prepare a market briefing for the following portfolio:\n\n"
            f"{portfolio_to_text(portfolio)}"
        )),
    ])

    return {"news_review": result}
