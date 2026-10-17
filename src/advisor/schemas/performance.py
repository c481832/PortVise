"""Scored outcomes for a prior review's calls."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class PastCallOutcome(BaseModel):
    """How one prior reduce/exit/add recommendation has performed since the review.

    ``daily_outperf_pct`` is the average per-trading-day return of the named position minus
    the benchmark over the window since the review (length-unbiased). It is ``None`` while the
    call is ``pending`` (too few trading days elapsed) or when price history is unavailable.
    """

    model_config = ConfigDict(extra="ignore")

    position: str
    action_type: Literal["reduce", "exit", "add"]
    days_elapsed: int
    daily_outperf_pct: float | None
    verdict: Literal["validated", "invalidated", "pending"]
    note: str = ""


class PastPerformanceReview(BaseModel):
    """Deterministic scorecard for a single past review's reduce/exit/add calls."""

    model_config = ConfigDict(extra="ignore")

    review_id: str
    review_date: str
    benchmark: str
    matured_count: int
    validated_count: int
    outcomes: list[PastCallOutcome]
