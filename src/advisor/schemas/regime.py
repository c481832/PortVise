"""Macro regime state vector and historical analog outcomes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RegimeStateVector(BaseModel):
    """Rule-based macro state from live indicators."""

    model_config = ConfigDict(extra="ignore")

    inflation_trend: Literal["up", "down", "stable"]
    rates_trend: Literal["up", "down", "stable"]
    growth_trend: Literal["accelerating", "slowing", "stable"]
    liquidity: Literal["tight", "neutral", "loose"]
    volatility: Literal["high", "low"]


class HistoricalRegimePeriod(BaseModel):
    """Portfolio result from one historical regime analog."""

    model_config = ConfigDict(extra="ignore")

    period: str
    forward_window: str
    match_score: float
    portfolio_return: float
    max_drawdown: float


class HistoricalRegimeOutcome(BaseModel):
    """Historical analog summary from the regime runner."""

    model_config = ConfigDict(extra="ignore")

    runner_available: bool
    message: str
    analog_periods_identified: int
    avg_return: float | None
    max_drawdown: float | None
    win_rate: float | None
    top_similar_periods: list[HistoricalRegimePeriod]


class RegimeReview(BaseModel):
    model_config = ConfigDict(extra="ignore")

    current_regime: str = Field(
        description="Human-readable composite regime label aligned with state_vector."
    )
    state_vector: RegimeStateVector
    historical_outcome: HistoricalRegimeOutcome
    mismatch_drivers: list[str] = Field(
        description="Why the book is misaligned with the regime (duration, growth tilt, etc.).",
    )
    regime_appropriate_tilts: list[str]
    summary: str
