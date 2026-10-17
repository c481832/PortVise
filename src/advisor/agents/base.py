from __future__ import annotations

from advisor.prompts.market import market_data_to_text
from advisor.prompts.news import news_to_text
from advisor.prompts.portfolio import portfolio_to_text
from advisor.schemas.state import GraphState


def build_analysis_prompt(state: GraphState) -> str:
    portfolio = state["portfolio"]
    news = state["news_review"]
    market_data = state["market_data"]

    content = portfolio_to_text(portfolio)
    if news:
        content += f"\n\n{news_to_text(news)}"
    if market_data:
        content += f"\n\n{market_data_to_text(market_data)}"
    return content
