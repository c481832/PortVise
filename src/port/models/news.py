"""News planning focus and the news agent's structured review."""

from __future__ import annotations

from pydantic import BaseModel, Field

from port.models.normalizers import IGNORE_EXTRA


class PositionGoalFocus(BaseModel):
    model_config = IGNORE_EXTRA

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

    model_config = IGNORE_EXTRA

    portfolio_goal: str = ""
    portfolio_search_queries: list[str] = Field(
        default_factory=list,
        description="Three macro / portfolio-wide web search strings (from planner LLM)",
    )
    position_goals: list[PositionGoalFocus] = Field(default_factory=list)


class PositionSearchPlan(BaseModel):
    """Per-ticker search plan produced by the planner LLM."""

    model_config = IGNORE_EXTRA

    ticker: str = Field(description="Same symbol as in the portfolio")
    latest_news_query: str = Field(
        description=(
            "REQUIRED: one web search string for fresh headlines on this holding. "
            "Use exactly: 'latest news for {TICKER}' with the portfolio symbol (e.g. "
            "'latest news for NVDA')."
        ),
    )


class NewsPlannerResult(BaseModel):
    """Structured planner output; merged into NewsFocus before news research runs."""

    model_config = IGNORE_EXTRA

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


class NewsReview(BaseModel):
    """Lightweight market context passed to all downstream agents."""

    model_config = IGNORE_EXTRA

    macro_context: str = Field(
        description="2-3 sentences: rates, USD, credit spreads, equity vol, central bank posture"
    )
    market_themes: list[str] = Field(
        description="3-5 dominant themes driving flows, short labels",
    )
    key_events: list[str] = Field(
        description="Up to 6 notable recent events relevant to the portfolio tickers/sectors",
    )
    thesis_risks: list[str] = Field(
        description="Tickers where recent events challenge the original entry thesis",
    )
    summary: str
