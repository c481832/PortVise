from __future__ import annotations

import operator
from typing import Annotated

from typing_extensions import TypedDict

from port.portfolio import Portfolio
from port.schemas.manager import ManagerReview
from port.schemas.market import MarketData
from port.schemas.news import NewsReview
from port.schemas.planner import NewsFocus
from port.schemas.regime import RegimeReview
from port.schemas.risk import RiskReview
from port.schemas.theme import ThemeReview
from port.schemas.validation import ValidationReview


class GraphState(TypedDict):
    portfolio: Portfolio
    requested_locale: str
    inherited_feedback: list[dict[str, str | None]]

    news_focus: NewsFocus | None
    market_data: MarketData | None
    news_research_text: str | None
    news_research_query_count: int | None
    news_review: NewsReview | None
    risk_results: Annotated[list[RiskReview], operator.add]
    regime_results: Annotated[list[RegimeReview], operator.add]
    theme_results: Annotated[list[ThemeReview], operator.add]

    validation_review: ValidationReview | None
    validation_needs_more: bool
    validation_missing_inputs: list[str]
    validation_request_note: str | None
    validation_retry_count: int
    manager_review: ManagerReview | None
