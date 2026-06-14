from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from port.models import (
    ManagerReview,
    MarketData,
    NewsReview,
    RegimeReview,
    RiskReview,
    ThemeReview,
    ValidationReview,
)
from port.portfolio import Portfolio

CorporateActionMode = Literal["best_effort", "strict", "off"]
AgentReviewStatus = Literal["done", "error", "timeout", "cancelled"]


class AgentLLMConfig(BaseModel):
    """Optional per-review LLM overrides for local agent runs."""

    model_config = ConfigDict(extra="ignore")

    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    agent_models: dict[str, str] | None = None


class AgentReviewRequest(BaseModel):
    """Stable local-agent request contract."""

    model_config = ConfigDict(extra="ignore")

    portfolio: Portfolio
    locale: str = "en"
    corporate_actions: CorporateActionMode = "best_effort"
    timeout_seconds: int = Field(default=1800, ge=0)
    llm: AgentLLMConfig | None = None


class AgentReviewResult(BaseModel):
    """Stable local-agent result contract."""

    model_config = ConfigDict(extra="ignore")

    review_id: str
    status: AgentReviewStatus
    started_at: str
    finished_at: str | None = None
    requested_locale: str = "en"
    content_locale: str = "en"
    translation_fallback_used: bool = False
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    manager_review: ManagerReview | None = None
    validation_review: ValidationReview | None = None
    risk_review: RiskReview | None = None
    regime_review: RegimeReview | None = None
    theme_review: ThemeReview | None = None
    news_review: NewsReview | None = None
    market_data: MarketData | None = None
    final_state: dict[str, Any] | None = None
