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
            "Single web search for this symbol — use the planner form: "
            "'latest news for {TICKER}' (filled by planner output)"
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


class PositionSearchPlan(BaseModel):
    """Per-ticker search plan produced by the planner LLM."""

    model_config = ConfigDict(extra="ignore")

    ticker: str = Field(description="Same symbol as in the portfolio")
    latest_news_query: str = Field(
        description=(
            "REQUIRED: one web search string for fresh headlines on this holding. "
            "Use exactly: 'latest news for {TICKER}' with the portfolio symbol (e.g. "
            "'latest news for NVDA')."
        ),
    )


class NewsPlannerResult(BaseModel):
    """Structured planner output; merged into NewsFocus before the news collector runs."""

    model_config = ConfigDict(extra="ignore")

    portfolio_search_queries: list[str] = Field(
        description=(
            "Exactly three web search strings: top macro / cross-cutting topics inferred from the "
            "portfolio CONTEXT note and overall thesis mix "
            "(Fed, rates, USD, credit, growth, risk). "
            "No single-name stock angles — those are only in per-ticker latest_news_query."
        ),
    )
    position_plans: list[PositionSearchPlan] = Field(
        description=(
            "One entry per portfolio line: latest_news_query only (see PositionSearchPlan)."
        ),
    )
