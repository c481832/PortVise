"""Registered task: deterministic risk analysis."""

from __future__ import annotations

from typing import Any

from port.risk_engine import compute_risk_review_base
from port.runner.core.registry import register_task
from port.runner.data.loader import DataLoader
from port.runner.risk import contribution, factor, stress


@register_task("risk_analysis")
def risk_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    loader = DataLoader(payload)
    portfolio = loader.portfolio()
    md = loader.market_data()

    review = compute_risk_review_base(portfolio, md)
    return {
        "task": "risk_analysis",
        "factor_exposure": factor.extract_factor_exposure(review),
        "risk_contribution": contribution.extract_risk_contribution(review),
        "stress_tests": stress.extract_stress_tests(review),
        "risk_review": review.model_dump(mode="json"),
    }
