"""LLM client factory — reads from .env / environment variables."""

from __future__ import annotations

import contextvars
import json
import warnings
from dataclasses import dataclass
from pathlib import Path

# OpenAI SDK can type `parsed` as None while LangChain puts a Pydantic model there; harmless.
warnings.filterwarnings(
    "ignore",
    message=r"Pydantic serializer warnings:[\s\S]*field_name='parsed'",
    category=UserWarning,
    module=r"pydantic\.main",
)

import httpx  # noqa: E402
from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from pydantic_settings import BaseSettings, SettingsConfigDict  # noqa: E402

from port.i18n import (  # noqa: E402
    DEFAULT_LOCALE,
    LocaleRuntimeState,
    apply_translations_to_payload,
    chunk_strings,
    inject_locale_instruction,
    needs_translation_fallback,
    normalize_locale,
    prompt_language_name,
)

# Keys for per-agent model overrides (matches UI / API).
AGENT_MODEL_KEYS: frozenset[str] = frozenset(
    {
        "planner",
        "news_tools",
        "news_synthesis",
        "risk",
        "regime",
        "theme",
        "validation",
        "manager",
    }
)

# Repository root (parent of the ``port`` package). Log paths use this so they do not depend on cwd.
REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    llm_base_url: str = "http://localhost:8000/v1"
    llm_model: str = "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
    # Fast 7B router (ai-router); override with FAST_LLM_BASE_URL if needed.
    fast_llm_base_url: str = "http://localhost:8000/v1"
    fast_llm_model: str = "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
    llm_api_key: str = "dummy"
    tavily_api_key: str = ""
    # Local SearXNG base URL (no trailing path). Used when Tavily is unset and DuckDuckGo fails.
    # Set SEARXNG_URL= to disable (skip SearXNG when DDG fails).
    searxng_url: str = "http://127.0.0.1:8888"
    # Comma-separated extra model ids for the UI dropdown (in addition to llm_model /
    # fast_llm_model).
    llm_model_options: str = ""
    # Local llama.cpp can take many minutes per completion; OpenAI defaults (e.g. 600s
    # read) are easy to hit.
    llm_connect_timeout: float = 30.0
    llm_read_timeout: float = 1200.0
    llm_max_retries: int = 2
    # stderr + rotating file for ``port.*``. Empty ``PORT_LOG_FILE`` disables file logging.
    # Default is absolute under the repo so the file is stable when cwd varies (IDE, Docker).
    port_log_file: str = str(REPO_ROOT / "logs" / "port.log")
    port_log_max_bytes: int = 10 * 1024 * 1024
    port_log_backup_count: int = 5


settings = Settings()


def port_log_path_resolved() -> Path | None:
    """Return the absolute log file path, or None if file logging is disabled.

    Relative ``settings.port_log_file`` values are resolved against ``REPO_ROOT``, not cwd.
    """
    raw = (settings.port_log_file or "").strip()
    if not raw:
        return None
    p = Path(raw)
    if p.is_absolute():
        return p.resolve()
    return (REPO_ROOT / p).resolve()


def wipe_port_log_file(
    log_path: Path | None,
    *,
    backup_count: int | None = None,
) -> None:
    """Remove the log file and RotatingFileHandler backups (``name.1``, …). No-op if disabled."""
    if log_path is None:
        return
    bc = settings.port_log_backup_count if backup_count is None else backup_count
    log_path = log_path.resolve()
    log_path.unlink(missing_ok=True)
    for i in range(1, bc + 1):
        log_path.with_name(f"{log_path.name}.{i}").unlink(missing_ok=True)


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
        "planner": settings.fast_llm_model,
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

locale_runtime_state: contextvars.ContextVar[LocaleRuntimeState | None] = contextvars.ContextVar(
    "locale_runtime_state", default=None
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
    use_fast = fast or (agent in ("planner", "news_tools"))

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
        http_client=httpx.Client(timeout=_llm_http_timeout(), trust_env=False),
        http_async_client=httpx.AsyncClient(timeout=_llm_http_timeout(), trust_env=False),
    )


_MAX_TOKENS_CEILING = 32768
_LENGTH_MARKERS = ("length limit", "length_limit", "finish_reason: length", "max_tokens")

log = __import__("logging").getLogger(__name__)


class _TranslationBatch(BaseModel):
    translated: list[str] = Field(default_factory=list)


def _safe_text(value, *, max_chars: int = 12000) -> str:
    """Best-effort text rendering for log records."""
    try:
        if hasattr(value, "model_dump"):
            text = json.dumps(value.model_dump(), ensure_ascii=True, default=str)
        elif isinstance(value, (dict, list, tuple)):
            text = json.dumps(value, ensure_ascii=True, default=str)
        else:
            text = str(value)
    except Exception:
        text = repr(value)
    if len(text) > max_chars:
        return f"{text[:max_chars]}\n... (truncated)"
    return text


def _messages_for_log(messages) -> str:
    """Compact, readable message list for LLM input logs."""
    rendered: list[str] = []
    for i, m in enumerate(messages):
        msg_type = getattr(m, "type", m.__class__.__name__)
        content = getattr(m, "content", m)
        rendered.append(f"[{i}] {msg_type}: {_safe_text(content)}")
    return "\n".join(rendered)


def invoke_structured(
    schema, messages, *, agent: str, max_tokens: int = 4096, temperature: float = 0.1
):
    """Structured LLM call; doubles max_tokens on truncation up to _MAX_TOKENS_CEILING."""
    locale_state = locale_runtime_state.get()
    requested_locale = normalize_locale(
        locale_state.requested_locale if locale_state is not None else DEFAULT_LOCALE
    )
    localized_messages = inject_locale_instruction(messages, requested_locale)
    tokens = max_tokens
    while True:
        base = make_llm(max_tokens=tokens, agent=agent, temperature=temperature)
        llm = base.with_structured_output(schema)
        log.info(
            "LLM input agent=%r model=%r max_tokens=%d temperature=%.2f\n%s",
            agent,
            getattr(base, "model_name", "unknown"),
            tokens,
            temperature,
            _messages_for_log(localized_messages),
        )
        try:
            result = llm.invoke(localized_messages)
            if requested_locale != DEFAULT_LOCALE:
                result = _localize_structured_result(result, schema, agent, requested_locale)
            if locale_state is not None and requested_locale == DEFAULT_LOCALE:
                locale_state.content_locale = DEFAULT_LOCALE
            log.info("LLM output agent=%r\n%s", agent, _safe_text(result))
            return result
        except Exception as exc:
            msg = str(exc).lower()
            if any(m in msg for m in _LENGTH_MARKERS) and tokens < _MAX_TOKENS_CEILING:
                tokens = min(tokens * 2, _MAX_TOKENS_CEILING)
                log.info(
                    "structured output truncated for agent %r — retrying with max_tokens=%d",
                    agent,
                    tokens,
                )
                continue
            log.exception("LLM invoke failed agent=%r", agent)
            raise


def _localize_structured_result(result, schema, agent: str, locale: str):
    locale_state = locale_runtime_state.get()
    payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
    if not needs_translation_fallback(payload, locale):
        if locale_state is not None:
            locale_state.content_locale = normalize_locale(locale)
        return result
    try:
        translated_payload = apply_translations_to_payload(payload, locale, _translate_strings_fast)
        localized = schema.model_validate(translated_payload)
    except Exception:
        if locale_state is not None:
            locale_state.content_locale = DEFAULT_LOCALE
        return result
    if locale_state is not None:
        locale_state.translation_fallback_used = True
        locale_state.content_locale = normalize_locale(locale)
    log.info("localized structured output agent=%r via translation fallback", agent)
    return localized


def _translate_strings_fast(strings: list[str], locale: str) -> list[str]:
    if not strings:
        return []
    locale_name = prompt_language_name(locale)
    outputs: list[str] = []
    for batch in chunk_strings(strings):
        base = make_llm(max_tokens=3072, fast=True, temperature=0.0)
        llm = base.with_structured_output(_TranslationBatch)
        raw_result = llm.invoke(
            [
                SystemMessage(
                    content=(
                        f"Translate each input string into {locale_name}. Return JSON only. "
                        "Preserve stock tickers, acronyms, numbers, dates, punctuation, and terse "
                        "financial formatting. Do not add commentary."
                    )
                ),
                HumanMessage(content=json.dumps(batch, ensure_ascii=False)),
            ]
        )
        result = _TranslationBatch.model_validate(raw_result)
        translated = list(result.translated)
        if len(translated) != len(batch):
            raise ValueError("translation batch length mismatch")
        outputs.extend(translated)
    return outputs


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
