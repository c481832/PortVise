from __future__ import annotations

from pydantic import BaseModel

from port.config import LLMOverrides, freeze_agent_models


class LLMConfigBody(BaseModel):
    """Optional per-review overrides; omitted fields fall back to server settings."""

    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    fast_llm_base_url: str | None = None
    fast_llm_model: str | None = None
    agent_models: dict[str, str] | None = None


class StartRequest(BaseModel):
    portfolio: dict
    llm: LLMConfigBody | None = None
    locale: str | None = None


def llm_overrides_from_body(body: LLMConfigBody | None) -> LLMOverrides | None:
    if body is None:
        return None
    agent_models = freeze_agent_models(body.agent_models)
    has_overrides = any(
        value is not None
        for value in (
            body.llm_base_url,
            body.llm_model,
            body.llm_api_key,
            body.fast_llm_base_url,
            body.fast_llm_model,
        )
    )
    if not has_overrides and not agent_models:
        return None
    return LLMOverrides(
        llm_base_url=body.llm_base_url,
        llm_model=body.llm_model,
        llm_api_key=body.llm_api_key,
        fast_llm_base_url=body.fast_llm_base_url,
        fast_llm_model=body.fast_llm_model,
        agent_models=agent_models,
    )
