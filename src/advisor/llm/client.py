from __future__ import annotations

import contextvars
import json
import logging

import httpx
from langchain_openai import ChatOpenAI

from advisor.config import config
from advisor.schemas.runner import ReviewLLMConfig

log = logging.getLogger(__name__)

llm_runtime_overrides: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "llm_runtime_overrides", default=None
)


def resolved_model_options() -> list[str]:
    raw = config.llm.model_options.replace("\n", ",")
    extra = [part.strip() for part in raw.split(",") if part.strip()]
    core = [config.llm.model.strip()] if config.llm.model.strip() else []
    return list(dict.fromkeys(extra + core))


def configured_agent_models() -> dict[str, str]:
    return {key: config.agents[key] for key in config.agents}


def parse_json_object(raw: str, setting: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"{setting} must be a JSON object")
    return parsed


def parse_model_base_urls(raw: str) -> dict[str, str]:
    parsed = parse_json_object(raw, "llm.model_base_urls")
    out: dict[str, str] = {}
    for key, value in parsed.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("llm.model_base_urls keys must be non-empty model names")
        if not isinstance(value, str):
            raise ValueError(f"llm.model_base_urls[{key!r}] must be a string")
        if value.strip():
            out[key.strip()] = value.strip()
    return out


def parse_model_extra_args(raw: str) -> dict:
    parsed = parse_json_object(raw, "llm.model_extra_args")
    for key, value in parsed.items():
        if not isinstance(key, str):
            raise ValueError("llm.model_extra_args keys must be model names")
        if not isinstance(value, dict):
            raise ValueError(f"llm.model_extra_args[{key!r}] must be a JSON object")
    return parsed


def resolved_model_base_urls() -> dict[str, str]:
    return parse_model_base_urls(config.llm.model_base_urls)


def extra_args_for_model(model: str) -> dict:
    configured = parse_model_extra_args(config.llm.model_extra_args)
    return {**configured.get("*", {}), **configured.get(model, {})}


def select_model(agent: str | None, overrides: dict | None) -> str:
    if overrides is not None:
        agent_models = overrides.get("agent_models")
        if agent and agent_models:
            override = agent_models.get(agent)
            if override is not None:
                return override
        if overrides.get("llm_model") is not None:
            return overrides["llm_model"]

    if agent is not None:
        models = configured_agent_models()
        if agent not in models:
            raise ValueError(f"unknown agent model key: {agent!r}")
        configured_model = models[agent].strip()
        if configured_model:
            return configured_model

    return config.llm.model


def effective_llm_params(agent: str | None) -> tuple[str, str]:
    overrides = llm_runtime_overrides.get()
    model = select_model(agent, overrides)
    if overrides is not None and overrides.get("llm_base_url") is not None:
        return overrides["llm_base_url"], model
    base_url = resolved_model_base_urls().get(model.strip()) or config.llm.base_url
    return base_url, model


def make_llm(*, temperature: float, max_tokens: int, agent: str | None) -> ChatOpenAI:
    overrides = llm_runtime_overrides.get()
    base_url, model = effective_llm_params(agent)
    api_key = config.llm.api_key
    if overrides is not None and overrides.get("llm_api_key") is not None:
        api_key = overrides["llm_api_key"]
    if not api_key.strip():
        raise ValueError(
            "llm.api_key must be set in config.toml, config.local.toml, or LLM_API_KEY"
        )

    extra_kwargs = extra_args_for_model(model)
    log.info(
        "LLM extra call args agent=%r model=%r sent=%s keys=%s",
        agent,
        model,
        bool(extra_kwargs),
        sorted(extra_kwargs),
    )
    timeout = httpx.Timeout(
        connect=config.llm.connect_timeout,
        read=config.llm.read_timeout,
        write=config.llm.read_timeout,
        pool=config.llm.read_timeout,
    )
    return ChatOpenAI(
        base_url=base_url,
        model=model,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,  # type: ignore[call-arg]
        **extra_kwargs,
        timeout=timeout,
        max_retries=config.llm.max_retries,
        http_client=httpx.Client(timeout=timeout, trust_env=False),
        http_async_client=httpx.AsyncClient(timeout=timeout, trust_env=False),
    )


def freeze_agent_models(raw: dict[str, str] | None) -> dict[str, str] | None:
    if raw is None:
        return None
    known = set(config.agents)
    out: dict[str, str] = {}
    for key, value in raw.items():
        if key not in known:
            continue
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"agent model for {key!r} must be a non-empty string")
        out[key] = value.strip()
    return out


def llm_overrides_from_config(llm: ReviewLLMConfig | None) -> dict | None:
    if llm is None:
        return None
    frozen = freeze_agent_models(llm.agent_models)
    fields = (llm.llm_base_url, llm.llm_model, llm.llm_api_key)
    if all(value is None for value in fields) and not frozen:
        return None
    return {
        "llm_base_url": llm.llm_base_url,
        "llm_model": llm.llm_model,
        "llm_api_key": llm.llm_api_key,
        "agent_models": frozen,
    }
