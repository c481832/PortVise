"""Build configured `ChatOpenAI` clients and resolve per-agent model settings.

Runtime overrides (set per review from the UI or the agent API) take
precedence over the values in the config file.
"""

from __future__ import annotations

import contextvars
import json
import logging
from dataclasses import dataclass

import httpx
from langchain_openai import ChatOpenAI

from port.config import config

log = logging.getLogger(__name__)

AGENT_MODEL_KEYS: frozenset[str] = frozenset(
    {
        "planner",
        "news_tools",
        "news_synthesis",
        "risk",
        "regime",
        "theme",
        "validation",
        "allocation",
        "manager",
        "agent_summary",
    }
)
def resolved_model_options() -> list[str]:
    raw = config.llm.model_options.replace("\n", ",")
    extra = [p.strip() for p in raw.split(",") if p.strip()]
    core = [config.llm.model.strip()] if config.llm.model.strip() else []
    seen: set[str] = set()
    out: list[str] = []
    for x in extra + core:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
def parse_model_base_urls(raw: str) -> dict[str, str]:
    raw = (raw or "").strip()
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("llm.model_base_urls must be a JSON object")
    out: dict[str, str] = {}
    for key, value in parsed.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("llm.model_base_urls keys must be non-empty model names")
        if not isinstance(value, str):
            raise ValueError(f"llm.model_base_urls[{key!r}] must be a string")
        clean = value.strip()
        if clean:
            out[key.strip()] = clean
    return out
def resolved_model_base_urls() -> dict[str, str]:
    return parse_model_base_urls(config.llm.model_base_urls)
def configured_agent_models() -> dict[str, str]:
    return {
        "planner": config.agents.planner,
        "news_tools": config.agents.news_tools,
        "news_synthesis": config.agents.news_synthesis,
        "risk": config.agents.risk,
        "regime": config.agents.regime,
        "theme": config.agents.theme,
        "validation": config.agents.validation,
        "allocation": config.agents.allocation,
        "manager": config.agents.manager,
        "agent_summary": config.agents.agent_summary,
    }
def default_agent_models() -> dict[str, str]:
    return configured_agent_models()
@dataclass(frozen=True)
class LLMOverrides:
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    agent_models: tuple[tuple[str, str], ...] | None = None
llm_runtime_overrides: contextvars.ContextVar[LLMOverrides | None] = contextvars.ContextVar(
    "llm_runtime_overrides", default=None
)
def _agent_model_override(agent: str | None) -> str | None:
    if not agent:
        return None
    o = llm_runtime_overrides.get()
    if not o or not o.agent_models:
        return None
    for k, v in o.agent_models:
        if k == agent:
            return v
    return None
def _base_url_for_model(model: str) -> str | None:
    return resolved_model_base_urls().get(model.strip())
def _effective_llm_params(agent: str | None) -> tuple[str, str]:
    o = llm_runtime_overrides.get()
    if o is not None and o.llm_base_url is not None:
        has_runtime_base_url = True
        base_url: str = o.llm_base_url
    else:
        has_runtime_base_url = False
        base_url = config.llm.base_url

    override = _agent_model_override(agent)
    if override is not None:
        if not has_runtime_base_url:
            base_url = _base_url_for_model(override) or base_url
        return base_url, override

    if o is not None and o.llm_model is not None:
        if not has_runtime_base_url:
            base_url = _base_url_for_model(o.llm_model) or base_url
        return base_url, o.llm_model

    if agent is not None:
        models = configured_agent_models()
        if agent not in models:
            raise ValueError(f"unknown agent model key: {agent!r}")
        configured_model = models[agent].strip()
        if configured_model:
            if not has_runtime_base_url:
                base_url = _base_url_for_model(configured_model) or base_url
            return base_url, configured_model

    model = config.llm.model
    if not has_runtime_base_url:
        base_url = _base_url_for_model(model) or base_url
    return base_url, model
_RESERVED_EXTRA_ARG_KEYS = frozenset(
    {
        "api_key",
        "base_url",
        "http_async_client",
        "http_client",
        "max_retries",
        "max_tokens",
        "model",
        "timeout",
    }
)
def parse_model_extra_args(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("llm.model_extra_args must be a JSON object")
    for key, value in parsed.items():
        if not isinstance(key, str):
            raise ValueError("llm.model_extra_args keys must be model names")
        if not isinstance(value, dict):
            raise ValueError(f"llm.model_extra_args[{key!r}] must be a JSON object")
        reserved = sorted(set(value) & _RESERVED_EXTRA_ARG_KEYS)
        if reserved:
            raise ValueError(
                f"llm.model_extra_args[{key!r}] uses reserved ChatOpenAI argument(s): {reserved}"
            )
    return parsed
def _model_extra_args_config() -> dict:
    return parse_model_extra_args(config.llm.model_extra_args)
def _extra_args_for_model(model: str) -> dict:
    configured = _model_extra_args_config()
    merged: dict = {}
    default_args = configured.get("*")
    model_args = configured.get(model)
    if isinstance(default_args, dict):
        merged.update(default_args)
    if isinstance(model_args, dict):
        merged.update(model_args)
    return merged
def _llm_http_timeout() -> httpx.Timeout:
    r = config.llm.read_timeout
    return httpx.Timeout(
        connect=config.llm.connect_timeout,
        read=r,
        write=r,
        pool=r,
    )
def make_llm(
    *,
    temperature: float,
    max_tokens: int,
    agent: str | None = None,
) -> ChatOpenAI:
    o = llm_runtime_overrides.get()
    base_url, model = _effective_llm_params(agent)
    api_key = o.llm_api_key if o and o.llm_api_key is not None else config.llm.api_key
    if not api_key.strip():
        raise ValueError(
            "llm.api_key must be set in config.toml, config.local.toml, or LLM_API_KEY"
        )
    extra_kwargs = _extra_args_for_model(model)
    log.info(
        "LLM extra call args agent=%r model=%r sent=%s keys=%s",
        agent,
        model,
        bool(extra_kwargs),
        sorted(extra_kwargs),
    )
    return ChatOpenAI(
        base_url=base_url,
        model=model,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,  # type: ignore[call-arg]
        **extra_kwargs,
        timeout=_llm_http_timeout(),
        max_retries=config.llm.max_retries,
        http_client=httpx.Client(timeout=_llm_http_timeout(), trust_env=False),
        http_async_client=httpx.AsyncClient(timeout=_llm_http_timeout(), trust_env=False),
    )
def freeze_agent_models(raw: dict[str, str] | None) -> tuple[tuple[str, str], ...] | None:
    if raw is None:
        return None
    pairs: list[tuple[str, str]] = []
    for k, v in raw.items():
        if k not in AGENT_MODEL_KEYS:
            continue
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"agent model for {k!r} must be a non-empty string")
        pairs.append((k, v.strip()))
    pairs.sort(key=lambda x: x[0])
    return tuple(pairs)
