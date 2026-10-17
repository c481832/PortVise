from __future__ import annotations

from pydantic import BaseModel, Field

from advisor.schemas.portfolio import Portfolio
from advisor.schemas.runner import ReviewLLMConfig


class ConfigUpdateRequest(BaseModel):
    # A None field is left unchanged on disk; the UI only sends API keys when one is typed.
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    model_options: list[str] | None = None
    model_base_urls: dict[str, str] | None = None
    model_extra_args: str | None = None
    agent_models: dict[str, str] | None = None
    search_provider: str | None = None
    searxng_url: str | None = None
    tavily_api_key: str | None = None
    min_allocated_capital: float | None = Field(default=None, ge=0.0, le=1.0)
    max_drawdown: float | None = Field(default=None, ge=0.0, le=1.0)
    cash_yield_annual_pct: float | None = Field(default=None, ge=0.0)


class SearchConfigRequest(BaseModel):
    search_provider: str | None = None
    searxng_url: str | None = None
    tavily_api_key: str | None = None


class InheritedFeedbackItem(BaseModel):
    source_review_id: str
    round_id: str
    comment: str
    submitted_at: str | None = None


class StartRequest(BaseModel):
    portfolio: Portfolio
    llm: ReviewLLMConfig | None = None
    inherited_feedback: list[InheritedFeedbackItem] = Field(default_factory=list)


class FeedbackCandidateRequest(BaseModel):
    portfolio: Portfolio


class FeedbackRerunRequest(BaseModel):
    comment: str
