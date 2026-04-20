"""Stress scenarios from the risk engine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from port.models import RiskReview


def extract_stress_tests(review: RiskReview) -> list[dict[str, Any]]:
    return [s.model_dump(mode="json") for s in review.scenario_losses]
