from __future__ import annotations

import operator
from typing import Annotated

from typing_extensions import TypedDict

from port.models.allocation import AllocationReview
from port.models.manager import ManagerReview
from port.models.market import MarketData
from port.models.news import NewsFocus, NewsReview
from port.models.portfolio import Portfolio
from port.models.regime import RegimeReview
from port.models.risk import RiskReview
from port.models.theme import ThemeReview
from port.models.validation import ValidationReview


class GraphState(TypedDict):
    portfolio: Portfolio
    inherited_feedback: list[dict[str, str | None]]

    news_focus: NewsFocus | None
    market_data: MarketData | None
    news_research_text: str | None
    news_research_query_count: int | None
    news_review: NewsReview | None
    risk_results: Annotated[list[RiskReview], operator.add]
    regime_results: Annotated[list[RegimeReview], operator.add]
    theme_results: Annotated[list[ThemeReview], operator.add]

    allocation_results: Annotated[list[AllocationReview], operator.add]

    validation_review: ValidationReview | None
    validation_needs_more: bool
    validation_missing_inputs: list[str]
    validation_request_note: str | None
    validation_retry_count: int
    manager_review: ManagerReview | None
