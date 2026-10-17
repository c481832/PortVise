"""News agent structured review."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NewsReview(BaseModel):
    """Lightweight market context passed to all downstream agents."""

    model_config = ConfigDict(extra="ignore")

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
