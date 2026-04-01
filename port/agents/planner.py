"""Planner agent — derives search priorities from portfolio + position goals for the news step."""

from __future__ import annotations

from typing import TYPE_CHECKING

from port.models import NewsFocus, PositionGoalFocus
from port.portfolio import Portfolio

if TYPE_CHECKING:
    from port.state import GraphState


def build_news_focus(portfolio: Portfolio) -> NewsFocus:
    """Portfolio goal (`context_note`) + each position's entry thesis as explicit search targets."""
    return NewsFocus(
        portfolio_goal=(portfolio.context_note or "").strip(),
        position_goals=[
            PositionGoalFocus(ticker=p.ticker, goal=(p.entry_thesis or "").strip())
            for p in portfolio.positions
        ],
    )


def planner_node(state: GraphState) -> dict:
    return {"news_focus": build_news_focus(state["portfolio"])}
