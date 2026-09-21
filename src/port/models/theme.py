"""Theme assessments and portfolio-level synthesis."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from port.models.exposure import ExposureLayer
from port.models.normalizers import IGNORE_EXTRA


class ThemePositionProfile(BaseModel):
    """Step 1: portfolio → metadata + candidate themes (per position)."""

    model_config = IGNORE_EXTRA

    ticker: str
    sector: str
    business_model: str
    revenue_drivers: str
    candidate_themes: list[str]


class ThemeAssessment(BaseModel):
    """Step 3: qualitative theme ↔ book ↔ news assessment."""

    model_config = IGNORE_EXTRA

    theme: str
    supporting_assets: list[str]
    key_evidence: list[str]
    assessment: str
    implication: str
    narrative_kind: Literal["structural", "cyclical", "unknown"]

    @field_validator("supporting_assets", "key_evidence", mode="before")
    @classmethod
    def _coerce_list_fields(cls, value):
        """Handle common LLM singleton-string emissions for list[str] fields."""
        if value is None:
            raise ValueError("supporting_assets / key_evidence cannot be None")
        if isinstance(value, str):
            s = value.strip()
            if not s:
                raise ValueError("supporting_assets / key_evidence cannot be an empty string")
            return [s]
        if isinstance(value, list):
            out: list[str] = []
            for item in value:
                if item is None:
                    raise ValueError("list field contains None")
                if not isinstance(item, str):
                    raise TypeError("ThemeAssessment list fields must contain strings only")
                s = item.strip()
                if s:
                    out.append(s)
            return out
        raise TypeError("ThemeAssessment list fields must be a string or list of strings")


class ThemePortfolioSynthesis(BaseModel):
    """Step 4: book-level narrative."""

    model_config = IGNORE_EXTRA

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

    model_config = IGNORE_EXTRA

    implicit_portfolio_bet: str = Field(
        description="What the portfolio is implicitly betting on before checking the tape.",
    )
    position_profiles: list[ThemePositionProfile]
    theme_assessments: list[ThemeAssessment]
    synthesis: ThemePortfolioSynthesis
    crowding_risks: list[str]
    momentum_conflicts: list[str]
    exposure_links: list[ExposureLayer] = Field(
        description="Map dominant themes to factor / regime hooks.",
    )
    summary: str
