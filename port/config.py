"""LLM client factory — reads from .env / environment variables."""

from __future__ import annotations

import contextvars
import warnings
from dataclasses import dataclass

# OpenAI SDK can type `parsed` as None while LangChain puts a Pydantic model there; harmless.
warnings.filterwarnings(
    "ignore",
    message=r"Pydantic serializer warnings:[\s\S]*field_name='parsed'",
    category=UserWarning,
    module=r"pydantic\.main",
)

import httpx  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from pydantic_settings import BaseSettings, SettingsConfigDict  # noqa: E402

# Keys for per-agent model overrides (matches UI / API).
AGENT_MODEL_KEYS: frozenset[str] = frozenset(
    {
        "news_tools",
        "news_synthesis",
        "risk",
        "regime",
        "theme",
        "validation",
        "manager",
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    llm_base_url: str = "http://localhost:8003/v1"
    llm_model: str = "Qwen3.5-35B-A3B-UD-Q6_K_S.gguf"
    # Fast 7B router (ai-router); override with FAST_LLM_BASE_URL if needed.
    fast_llm_base_url: str = "http://localhost:8000/v1"
    fast_llm_model: str = "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
    llm_api_key: str = "dummy"
    tavily_api_key: str = ""
    # Comma-separated extra model ids for the UI dropdown (in addition to llm_model /
    # fast_llm_model).
    llm_model_options: str = ""
    # Local llama.cpp can take many minutes per completion; OpenAI defaults (e.g. 600s
    # read) are easy to hit.
    llm_connect_timeout: float = 30.0
    llm_read_timeout: float = 1200.0
    llm_max_retries: int = 2


settings = Settings()


def resolved_model_options() -> list[str]:
    """Distinct model names for UI/API: extras from LLM_MODEL_OPTIONS plus primary and fast."""
    raw = settings.llm_model_options.replace("\n", ",")
    extra = [p.strip() for p in raw.split(",") if p.strip()]
    core = [settings.llm_model, settings.fast_llm_model]
    seen: set[str] = set()
    out: list[str] = []
    for x in extra + core:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def default_agent_models() -> dict[str, str]:
    """Server default model id for each agent slot (for UI labels)."""
    return {
        "news_tools": settings.fast_llm_model,
        "news_synthesis": settings.llm_model,
        "risk": settings.llm_model,
        "regime": settings.llm_model,
        "theme": settings.llm_model,
        "validation": settings.llm_model,
        "manager": settings.llm_model,
    }


@dataclass(frozen=True)
class LLMOverrides:
    """Per-review overrides from the client. Any field left None uses `settings`."""

    llm_base_url: str | None = None
    llm_model: str | None = None
    fast_llm_base_url: str | None = None
    fast_llm_model: str | None = None
    agent_models: tuple[tuple[str, str], ...] | None = None


# Set by ReviewSession while a graph run is active; agent nodes call `make_llm()` inside it.
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


def _effective_llm_params(fast: bool, agent: str | None) -> tuple[str, str]:
    o = llm_runtime_overrides.get()
    use_fast = fast or (agent == "news_tools")

    if use_fast:
        base_url = (o.fast_llm_base_url if o else None) or settings.fast_llm_base_url
    else:
        base_url = (o.llm_base_url if o else None) or settings.llm_base_url

    override = _agent_model_override(agent)
    if override:
        return base_url, override

    if use_fast:
        model = (o.fast_llm_model if o else None) or settings.fast_llm_model
    else:
        model = (o.llm_model if o else None) or settings.llm_model
    return base_url, model


def _llm_http_timeout() -> httpx.Timeout:
    r = settings.llm_read_timeout
    return httpx.Timeout(
        connect=settings.llm_connect_timeout,
        read=r,
        write=r,
        pool=r,
    )


# Injected by ReviewSession._run before the graph runs.
# Agent nodes retrieve this and call it to emit agent_step SSE events.
step_callback: contextvars.ContextVar = contextvars.ContextVar("step_callback", default=None)


def make_llm(
    temperature: float = 0.1,
    max_tokens: int = 2048,
    fast: bool = False,
    *,
    agent: str | None = None,
) -> ChatOpenAI:
    base_url, model = _effective_llm_params(fast, agent)
    return ChatOpenAI(
        base_url=base_url,
        model=model,
        api_key=settings.llm_api_key,
        temperature=temperature,
        max_tokens=max_tokens,  # type: ignore[call-arg]
        timeout=_llm_http_timeout(),
        max_retries=settings.llm_max_retries,
    )


def freeze_agent_models(raw: dict[str, str] | None) -> tuple[tuple[str, str], ...] | None:
    """Keep only known agent keys and non-empty values; return immutable pairs for LLMOverrides."""
    if not raw:
        return None
    pairs: list[tuple[str, str]] = []
    for k, v in raw.items():
        if k in AGENT_MODEL_KEYS and isinstance(v, str) and v.strip():
            pairs.append((k, v.strip()))
    if not pairs:
        return None
    pairs.sort(key=lambda x: x[0])
    return tuple(pairs)
