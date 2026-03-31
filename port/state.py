from __future__ import annotations

import operator
from typing import TYPE_CHECKING, Annotated

from typing_extensions import TypedDict

if TYPE_CHECKING:
    from port.models import (
        MarketData,
        NewsReview,
        PlannerReview,
        RegimeReview,
        RiskReview,
        ThemeReview,
        ValidationReview,
    )
    from port.portfolio import Portfolio


class GraphState(TypedDict):
    portfolio: Portfolio

    market_data: MarketData | None
    news_review: NewsReview | None

    risk_results: Annotated[list[RiskReview], operator.add]
    regime_results: Annotated[list[RegimeReview], operator.add]
    theme_results: Annotated[list[ThemeReview], operator.add]

    validation_review: ValidationReview | None
    planner_review: PlannerReview | None
