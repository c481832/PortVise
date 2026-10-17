from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from advisor.schemas.allocation import AllocationReview
from advisor.schemas.manager import ManagerReview
from advisor.schemas.market import MarketData
from advisor.schemas.news import NewsReview
from advisor.schemas.portfolio import Portfolio
from advisor.schemas.regime import RegimeReview
from advisor.schemas.risk import RiskReview
from advisor.schemas.theme import ThemeReview

CorporateActionMode = Literal["best_effort", "strict", "off"]
ReviewStatus = Literal["done", "error", "timeout", "cancelled"]


class ReviewLLMConfig(BaseModel):
    """Optional per-review LLM overrides for local runner calls."""

    model_config = ConfigDict(extra="ignore")

    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    agent_models: dict[str, str] | None = None


class ReviewRequest(BaseModel):
    """Stable review-runner request contract."""

    model_config = ConfigDict(extra="ignore")

    portfolio: Portfolio
    corporate_actions: CorporateActionMode = "best_effort"
    timeout_seconds: int = Field(default=1800, ge=0)
    llm: ReviewLLMConfig | None = None


class ReviewResult(BaseModel):
    """Stable review-runner result contract."""

    model_config = ConfigDict(extra="ignore")

    review_id: str
    status: ReviewStatus
    started_at: str
    finished_at: str | None = None
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    manager_review: ManagerReview | None = None
    risk_review: RiskReview | None = None
    regime_review: RegimeReview | None = None
    theme_review: ThemeReview | None = None
    allocation_review: AllocationReview | None = None
    news_review: NewsReview | None = None
    market_data: MarketData | None = None
    final_state: dict[str, Any] | None = None
