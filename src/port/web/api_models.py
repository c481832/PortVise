from __future__ import annotations

from pydantic import BaseModel, Field

from port.config import LLMOverrides, freeze_agent_models


class LLMConfigBody(BaseModel):
    """Optional per-review overrides; omitted fields fall back to server settings."""

    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    agent_models: dict[str, str] | None = None


class ConfigUpdateBody(BaseModel):
    """LLM, search, and capital-policy settings persisted to config.local.toml.

    A ``None`` field is left unchanged on disk; this matters for the secret fields
    (``llm_api_key``, ``tavily_api_key``), which the UI only sends when the user types a new
    value (they are masked on load).
    """

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


class SearchConfigBody(BaseModel):
    """Optional search fields for the connectivity probe; omitted fields fall back to saved
    server settings (so a saved Tavily key can be tested without re-typing it). The probe tests
    whichever provider ``search_provider`` selects (or the saved provider when omitted)."""

    search_provider: str | None = None
    searxng_url: str | None = None
    tavily_api_key: str | None = None


class InheritedFeedbackItem(BaseModel):
    source_review_id: str
    round_id: str
    comment: str
    submitted_at: str | None = None


class StartRequest(BaseModel):
    portfolio: dict
    llm: LLMConfigBody | None = None
    locale: str | None = None
    inherited_feedback: list[InheritedFeedbackItem] = Field(default_factory=list)


class FeedbackCandidateRequest(BaseModel):
    portfolio: dict


class FeedbackRerunBody(BaseModel):
    comment: str


def llm_overrides_from_body(body: LLMConfigBody | None) -> LLMOverrides | None:
    if body is None:
        return None
    agent_models = freeze_agent_models(body.agent_models)
    has_overrides = any(
        value is not None
        for value in (body.llm_base_url, body.llm_model, body.llm_api_key)
    )
    if not has_overrides and not agent_models:
        return None
    return LLMOverrides(
        llm_base_url=body.llm_base_url,
        llm_model=body.llm_model,
        llm_api_key=body.llm_api_key,
        agent_models=agent_models,
    )
