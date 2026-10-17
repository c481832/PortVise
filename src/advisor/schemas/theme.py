"""Theme assessments and portfolio-level synthesis."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ThemePositionProfile(BaseModel):
    """Step 1: portfolio → metadata + candidate themes (per position)."""

    model_config = ConfigDict(extra="ignore")

    ticker: str
    sector: str
    business_model: str
    revenue_drivers: str
    candidate_themes: list[str]


class ThemeAssessment(BaseModel):
    """Step 3: qualitative theme ↔ book ↔ news assessment."""

    model_config = ConfigDict(extra="ignore")

    theme: str
    supporting_assets: list[str]
    key_evidence: list[str]
    assessment: str
    implication: str
    narrative_kind: Literal["structural", "cyclical", "unknown"]


class ThemePortfolioSynthesis(BaseModel):
    """Step 4: book-level narrative."""

    model_config = ConfigDict(extra="ignore")

    dominant_themes: list[str]
    redundant_expressions: list[str] = Field(
        description="Multiple line items expressing the same macro or factor bet.",
    )
    missing_exposures: list[str] = Field(
        description="Hedges or themes implied by the thesis but absent from the book.",
    )
    theme_drift_note: str = Field(
        description="Drift vs last review if unknown, say so.",
    )


class ThemeReview(BaseModel):
    """Theme = f(portfolio structure, news flow); LLM interprets seeds + research."""

    model_config = ConfigDict(extra="ignore")

    implicit_portfolio_bet: str = Field(
        description="What the portfolio is implicitly betting on before checking the tape.",
    )
    position_profiles: list[ThemePositionProfile]
    theme_assessments: list[ThemeAssessment]
    synthesis: ThemePortfolioSynthesis
    crowding_risks: list[str]
    momentum_conflicts: list[str]
    summary: str
