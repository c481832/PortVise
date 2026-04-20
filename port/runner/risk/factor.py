"""Factor-style exposure extracted from the risk engine output."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from port.models import RiskReview


def extract_factor_exposure(review: RiskReview) -> dict[str, float]:
    return dict(review.factor_loadings)


def factor_exposure_from_returns(
    _factor_columns: list[str],
    _factor_rows: list[list[float]],
    _portfolio_returns: list[float],
) -> dict[str, float] | None:
    """Hook for a future OLS factor model when return matrices are supplied."""
    return None
