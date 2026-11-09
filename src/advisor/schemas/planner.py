"""Planner schemas — search-plan focus produced before the news collector runs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PositionGoalFocus(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ticker: str
    goal: str
    latest_news_query: str = Field(
        default="",
        description=(
            "Single web search for this symbol, built in code as "
            "'latest news for {COMPANY NAME} ({TICKER})'"
        ),
    )


class NewsFocus(BaseModel):
    """Portfolio goal + per-position goals for targeted news context."""

    model_config = ConfigDict(extra="ignore")

    portfolio_goal: str = ""
    portfolio_search_queries: list[str] = Field(
        default_factory=list,
        description="Three macro / portfolio-wide web search strings (from planner LLM)",
    )
    position_goals: list[PositionGoalFocus] = Field(default_factory=list)


class NewsPlannerResult(BaseModel):
    """Structured planner output; merged into NewsFocus before the news collector runs."""

    model_config = ConfigDict(extra="ignore")

    portfolio_search_queries: list[str] = Field(
        description=(
            "Exactly three web search strings: top macro / cross-cutting topics inferred from the "
            "portfolio CONTEXT note and overall thesis mix "
            "(Fed, rates, USD, credit, growth, risk). "
            "No single-name stock angles — per-ticker searches are built in code."
        ),
    )
