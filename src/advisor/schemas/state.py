from __future__ import annotations

from typing_extensions import TypedDict

from advisor.schemas.allocation import AllocationReview
from advisor.schemas.manager import ManagerReview
from advisor.schemas.market import MarketData
from advisor.schemas.news import NewsReview
from advisor.schemas.planner import NewsFocus
from advisor.schemas.portfolio import Portfolio
from advisor.schemas.regime import RegimeReview
from advisor.schemas.risk import RiskReview
from advisor.schemas.theme import ThemeReview


class GraphState(TypedDict):
    portfolio: Portfolio
    inherited_feedback: list[dict[str, str | None]]

    news_focus: NewsFocus | None
    market_data: MarketData | None
    news_collector_text: str | None
    news_review: NewsReview | None
    risk_review: RiskReview | None
    regime_review: RegimeReview | None
    theme_review: ThemeReview | None
    allocation_review: AllocationReview | None
    manager_review: ManagerReview | None
