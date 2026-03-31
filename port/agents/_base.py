"""Shared helpers for agent nodes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from port.portfolio import market_data_to_text, news_to_text, portfolio_to_text

if TYPE_CHECKING:
    from port.state import GraphState


def build_analysis_prompt(state: GraphState, portfolio_prefix: str = "Portfolio to review") -> str:
    """Build the standard content string for parallel analysis agents."""
    portfolio = state["portfolio"]
    news = state["news_review"]
    market_data = state["market_data"]

    content = f"{portfolio_prefix}:\n\n{portfolio_to_text(portfolio)}\n\n{news_to_text(news)}"
    if market_data:
        content += f"\n\n{market_data_to_text(market_data)}"
    return content
