from __future__ import annotations

import operator
from typing import Annotated, Optional

from typing_extensions import TypedDict

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

    market_data: Optional[MarketData]
    news_review: Optional[NewsReview]

    risk_results: Annotated[list[RiskReview], operator.add]
    regime_results: Annotated[list[RegimeReview], operator.add]
    theme_results: Annotated[list[ThemeReview], operator.add]

    validation_review: Optional[ValidationReview]
    planner_review: Optional[PlannerReview]
