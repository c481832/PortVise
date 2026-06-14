"""Registered task: deterministic risk analysis."""

from __future__ import annotations

from typing import Any

from port.risk_engine import compute_risk_review_base
from port.runner.core.registry import register_task
from port.runner.data.loader import DataLoader


@register_task("risk_analysis")
def risk_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    loader = DataLoader(payload)
    portfolio = loader.portfolio()
    md = loader.market_data()
    review = compute_risk_review_base(portfolio, md)
    return {"risk_review": review.model_dump(mode="json")}
