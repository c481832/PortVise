"""Risk contribution breakdowns (factor vs name)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from port.models import RiskReview


def extract_risk_contribution(review: RiskReview) -> dict[str, Any]:
    return {
        "by_factor": dict(review.factor_risk_contribution),
        "by_ticker": dict(review.marginal_risk_by_ticker),
    }


def risk_contribution_weights_cov(weights: list[float], cov: list[list[float]]) -> list[float]:
    """Marginal risk contribution w * (Cov w) / (w' Cov w); pure Python."""
    n = len(weights)
    if n == 0 or len(cov) != n or any(len(row) != n for row in cov):
        raise ValueError("weights and cov must be square and aligned")
    # Cov @ w
    mw = [sum(cov[i][j] * weights[j] for j in range(n)) for i in range(n)]
    port_var = sum(weights[i] * mw[i] for i in range(n))
    if port_var == 0:
        return [0.0] * n
    return [weights[i] * mw[i] / port_var for i in range(n)]
