"""Root config + LLM client factory.

The single source of truth for every tunable is `config.toml` at the repo root
(plus an optional gitignored `config.local.toml` override, plus a narrow env-var
whitelist for secrets/endpoints). Nothing has Python-level defaults.

Call ``port.config.load()`` exactly once at process startup (via
``port.bootstrap.bootstrap()``). Before ``load()`` runs, accessing any field on
``config`` raises ``ConfigNotLoadedError``.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import threading
import time
import tomllib
import warnings
from dataclasses import dataclass
from pathlib import Path

warnings.filterwarnings(
    "ignore",
    message=r"Pydantic serializer warnings:[\s\S]*field_name='parsed'",
    category=UserWarning,
    module=r"pydantic\.main",
)

import httpx  # noqa: E402
import tomlkit  # noqa: E402
from langchain_core.exceptions import OutputParserException  # noqa: E402
from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from port._retry import backoff_seconds, with_retry  # noqa: E402
from port.config_models import RootConfig  # noqa: E402
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

# config.py lives at src/port/config.py, so the repo root is three levels up.
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.toml"
LOCAL_CONFIG_PATH = REPO_ROOT / "config.local.toml"


class ConfigNotLoadedError(RuntimeError):
    """Raised when ``config`` is accessed before ``load()`` has been called."""


_ENV_OVERRIDES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("LLM_BASE_URL", ("llm", "base_url"), "str"),
    ("LLM_MODEL", ("llm", "model"), "str"),
    ("LLM_API_KEY", ("llm", "api_key"), "str"),
    ("LLM_MODEL_OPTIONS", ("llm", "model_options"), "str"),
    ("LLM_MODEL_BASE_URLS", ("llm", "model_base_urls"), "str"),
    ("LLM_MODEL_EXTRA_ARGS", ("llm", "model_extra_args"), "str"),
    ("LLM_CONNECT_TIMEOUT", ("llm", "connect_timeout"), "float"),
    ("LLM_READ_TIMEOUT", ("llm", "read_timeout"), "float"),
    ("LLM_MAX_RETRIES", ("llm", "max_retries"), "int"),
    ("LLM_INVOKE_MAX_ATTEMPTS", ("llm", "invoke_max_attempts"), "int"),
    ("LLM_INVOKE_RETRY_BASE_SECONDS", ("llm", "retry_base_seconds"), "float"),
    ("LLM_INVOKE_RETRY_MAX_SECONDS", ("llm", "retry_max_seconds"), "float"),
    ("SEARXNG_URL", ("search", "searxng_url"), "str"),
    ("TAVILY_API_KEY", ("search", "tavily_api_key"), "str"),
    ("SEARCH_CONCURRENT_REQUESTS", ("search", "concurrent_requests"), "int"),
    ("PORT_LOG_FILE", ("log", "file"), "str"),
    ("PORT_LOG_MAX_BYTES", ("log", "max_bytes"), "int"),
    ("PORT_LOG_BACKUP_COUNT", ("log", "backup_count"), "int"),
)


def _set_nested(d: dict, path: tuple[str, ...], value) -> None:
    cur = d
    for key in path[:-1]:
        cur = cur.setdefault(key, {})
    cur[path[-1]] = value


def _coerce(raw: str, kind: str):
    if kind == "str":
        return raw
    if kind == "int":
        return int(raw)
    if kind == "float":
        return float(raw)
    raise ValueError(f"unknown env coercion kind: {kind!r}")


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursive dict merge: override wins; nested dicts merged in place."""
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _drop_obsolete_config_keys(data: dict) -> None:
    """Ignore settings removed from older local UI-managed config files."""
    llm = data.get("llm")
    if isinstance(llm, dict):
        llm.pop("reasoning_enabled", None)
    data.pop("agent_reasoning", None)


_loaded: RootConfig | None = None


def load(toml_path: Path | None = None) -> RootConfig:
    """Load + validate config from TOML files + env overrides. Idempotent within a process."""
    global _loaded
    if _loaded is not None:
        return _loaded

    primary = toml_path if toml_path is not None else DEFAULT_CONFIG_PATH
    if not primary.exists():
        raise FileNotFoundError(f"config TOML not found: {primary}")
    with primary.open("rb") as f:
        data = tomllib.load(f)

    if LOCAL_CONFIG_PATH.exists() and toml_path is None:
        with LOCAL_CONFIG_PATH.open("rb") as f:
            data = _deep_merge(data, tomllib.load(f))

    for env_name, path, kind in _ENV_OVERRIDES:
        raw = os.environ.get(env_name)
        if raw is None or raw == "":
            raw = os.environ.get(env_name.lower())
        if raw is None or raw == "":
            continue
        _set_nested(data, path, _coerce(raw, kind))

    _drop_obsolete_config_keys(data)
    _loaded = RootConfig.model_validate(data)
    return _loaded


def reload(toml_path: Path | None = None) -> RootConfig:
    """Discard any cached config and reload. Use sparingly — e.g. test fixtures.

    If the reload fails, the previously-loaded config is preserved (restore-on-error).
    """
    global _loaded
    saved = _loaded
    _loaded = None
    try:
        return load(toml_path)
    except BaseException:
        _loaded = saved
        raise


def _get() -> RootConfig:
    if _loaded is None:
        raise ConfigNotLoadedError(
            "port.config.load() must be called before accessing config "
            "(typically via port.bootstrap.bootstrap())."
        )
    return _loaded


class _ConfigProxy:
    """Module-level proxy that delegates to the loaded RootConfig.

    Allows ``from port.config import config; config.llm.base_url`` to raise a clear
    ConfigNotLoadedError if accessed before ``load()``.
    """

    __slots__ = ()

    def __getattr__(self, name: str):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return getattr(_get(), name)

    def __repr__(self) -> str:
        return f"<_ConfigProxy loaded={_loaded is not None}>"


config = _ConfigProxy()


def port_log_path_resolved() -> Path | None:
    """Return the absolute log file path, or None if file logging is disabled.

    Relative ``config.log.file`` values are resolved against ``REPO_ROOT``, not cwd.
    """
    raw = (config.log.file or "").strip()
    if not raw:
        return None
    p = Path(raw)
    if p.is_absolute():
        return p.resolve()
    return (REPO_ROOT / p).resolve()


def wipe_port_log_file(log_path: Path | None, *, backup_count: int) -> None:
    """Remove the log file and RotatingFileHandler backups (``name.1``, …). No-op if disabled."""
    if log_path is None:
        return
    log_path = log_path.resolve()
    log_path.unlink(missing_ok=True)
    for i in range(1, backup_count + 1):
        log_path.with_name(f"{log_path.name}.{i}").unlink(missing_ok=True)


def resolved_model_options() -> list[str]:
    """Distinct model names for UI/API: extras from llm.model_options plus the default model."""
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
    """Validate and parse per-model endpoint overrides."""
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
    """Per-model OpenAI-compatible API base URLs for UI/API and runtime routing."""
    return parse_model_base_urls(config.llm.model_base_urls)


def configured_agent_models() -> dict[str, str]:
    """Explicit model id for each agent slot, read directly from config."""
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
    """Default per-agent model routing exposed to the web UI."""
    return configured_agent_models()


_UI_LLM_KEYS: tuple[str, ...] = (
    "base_url",
    "model",
    "api_key",
    "model_options",
    "model_base_urls",
    "model_extra_args",
    "reasoning_enabled",
)
_UI_SEARCH_KEYS: tuple[str, ...] = ("provider", "searxng_url", "tavily_api_key")
_UI_CAPITAL_ALLOCATION_KEYS: tuple[str, ...] = (
    "min_allocated_capital",
    "max_drawdown",
    "cash_yield_annual_pct",
)


def write_ui_overrides(
    *,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    model_options: list[str] | None = None,
    model_base_urls: dict[str, str] | None = None,
    model_extra_args: str | None = None,
    agent_models: dict[str, str] | None = None,
    search_provider: str | None = None,
    searxng_url: str | None = None,
    tavily_api_key: str | None = None,
    min_allocated_capital: float | None = None,
    max_drawdown: float | None = None,
    cash_yield_annual_pct: float | None = None,
) -> None:
    """Persist the UI-managed settings to config.local.toml, then reload in-memory config.

    Edits are surgical: only the keys passed (non-None) are written, and comments plus any
    non-UI overrides already in the file are preserved. ``model_options`` is stored as a
    comma-joined string; ``model_extra_args`` is a JSON object keyed by model name or "*";
    ``agent_models`` rewrites the whole ``[agents]`` table (slots not present are cleared
    to "", i.e. "use default").
    """
    if LOCAL_CONFIG_PATH.exists():
        doc = tomlkit.parse(LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))
    else:
        doc = tomlkit.document()

    if any(
        v is not None
        for v in (base_url, model, api_key, model_options, model_base_urls, model_extra_args)
    ):
        if "llm" not in doc:
            doc["llm"] = tomlkit.table()
        llm = doc["llm"]
        if base_url is not None:
            llm["base_url"] = base_url.strip()
        if model is not None:
            llm["model"] = model.strip()
        if api_key is not None:
            llm["api_key"] = api_key
        if model_options is not None:
            llm["model_options"] = ", ".join(m.strip() for m in model_options if m.strip())
        if model_base_urls is not None:
            clean_urls = {
                str(k).strip(): str(v).strip()
                for k, v in model_base_urls.items()
                if str(k).strip() and str(v).strip()
            }
            llm["model_base_urls"] = json.dumps(clean_urls, sort_keys=True, separators=(",", ":"))
        if model_extra_args is not None:
            llm["model_extra_args"] = model_extra_args.strip()

    if any(v is not None for v in (search_provider, searxng_url, tavily_api_key)):
        if "search" not in doc:
            doc["search"] = tomlkit.table()
        search = doc["search"]
        if search_provider is not None:
            search["provider"] = search_provider.strip()
        if searxng_url is not None:
            search["searxng_url"] = searxng_url.strip()
        if tavily_api_key is not None:
            search["tavily_api_key"] = tavily_api_key

    if agent_models is not None:
        if "agents" not in doc:
            doc["agents"] = tomlkit.table()
        agents = doc["agents"]
        for key in sorted(AGENT_MODEL_KEYS):
            agents[key] = (agent_models.get(key) or "").strip()

    if any(v is not None for v in (min_allocated_capital, max_drawdown, cash_yield_annual_pct)):
        if "capital_allocation" not in doc:
            doc["capital_allocation"] = tomlkit.table()
        capital = doc["capital_allocation"]
        if min_allocated_capital is not None:
            capital["min_allocated_capital"] = min_allocated_capital
        if max_drawdown is not None:
            capital["max_drawdown"] = max_drawdown
        if cash_yield_annual_pct is not None:
            capital["cash_yield_annual_pct"] = cash_yield_annual_pct

    LOCAL_CONFIG_PATH.write_text(tomlkit.dumps(doc), encoding="utf-8")
    reload()


def _drop_table_keys(doc, table_name: str, keys: tuple[str, ...]) -> None:
    """Delete ``keys`` from ``doc[table_name]``; remove the table entirely once empty."""
    table = doc.get(table_name)
    if table is None:
        return
    for key in keys:
        if key in table:
            del table[key]
    if not len(table):
        del doc[table_name]


def clear_ui_overrides() -> None:
    """Remove every UI-managed key (LLM, search, capital policy, agents), then reload.

    This is the "Restore defaults" action: it drops everything the settings UI owns so config
    falls back to config.toml, while leaving hand-edited overrides of other keys/sections (and
    other ``[llm]``/``[search]`` keys like timeouts) intact. The file is deleted if nothing
    remains.
    """
    if LOCAL_CONFIG_PATH.exists():
        doc = tomlkit.parse(LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))
        _drop_table_keys(doc, "llm", _UI_LLM_KEYS)
        _drop_table_keys(doc, "search", _UI_SEARCH_KEYS)
        _drop_table_keys(doc, "capital_allocation", _UI_CAPITAL_ALLOCATION_KEYS)
        if "agents" in doc:
            del doc["agents"]
        if "agent_reasoning" in doc:
            del doc["agent_reasoning"]
        remaining = tomlkit.dumps(doc)
        if remaining.strip():
            LOCAL_CONFIG_PATH.write_text(remaining, encoding="utf-8")
        else:
            LOCAL_CONFIG_PATH.unlink()
    reload()


@dataclass(frozen=True)
class LLMOverrides:
    """Complete per-review LLM configuration from the client."""

    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    agent_models: tuple[tuple[str, str], ...] | None = None


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


def _base_url_for_model(model: str) -> str | None:
    return resolved_model_base_urls().get(model.strip())


def _effective_llm_params(agent: str | None) -> tuple[str, str]:
    o = llm_runtime_overrides.get()
    has_runtime_base_url = o is not None and o.llm_base_url is not None
    base_url = o.llm_base_url if has_runtime_base_url else config.llm.base_url

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
    """Validate and parse model-specific extra ChatOpenAI constructor arguments."""
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


step_callback: contextvars.ContextVar = contextvars.ContextVar("step_callback", default=None)
review_stop_event: contextvars.ContextVar[threading.Event | None] = contextvars.ContextVar(
    "review_stop_event", default=None
)


class ReviewStoppedError(RuntimeError):
    """Raised when an in-flight review has been stopped by the user."""


class StructuredLLMOutputError(RuntimeError):
    """Raised when an agent exhausts retries because the model returned malformed JSON."""

    def __init__(self, *, agent: str, schema_name: str):
        self.agent = agent
        self.schema_name = schema_name
        super().__init__(
            f"{agent.title()} agent returned malformed structured output after retries. "
            "The model produced invalid JSON, so the review could not continue. "
            "Retry the review, or choose a stronger model for this agent."
        )


def raise_if_review_stopped() -> None:
    event = review_stop_event.get()
    if event is not None and event.is_set():
        raise ReviewStoppedError("Review stopped by user.")


def make_llm(
    temperature: float = 0.1,
    max_tokens: int = 2048,
    *,
    agent: str | None = None,
) -> ChatOpenAI:
    """Construct a ChatOpenAI client. (Phase 2 will strip these defaults.)"""
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


log = logging.getLogger(__name__)


def _interruptible_sleep(seconds: float) -> None:
    """Sleep for ``seconds`` but raise ``ReviewStoppedError`` if a stop is requested."""
    if seconds <= 0:
        raise_if_review_stopped()
        return
    event = review_stop_event.get()
    if event is None:
        time.sleep(seconds)
        return
    if event.wait(seconds):
        raise ReviewStoppedError("Review stopped by user.")


def _retry_backoff_seconds(attempt: int) -> float:
    """Exponential backoff (capped) for the given 1-based attempt number."""
    base = max(0.0, config.llm.retry_base_seconds)
    cap = max(base, config.llm.retry_max_seconds)
    return backoff_seconds(attempt, base=base, cap=cap)


def _agent_flow_logger(agent: str) -> logging.Logger:
    return logging.getLogger(f"port.agentflow.{agent}")


class _TranslationBatch(BaseModel):
    translated: list[str] = Field(default_factory=list)


def _safe_text(value, *, max_chars: int = 12000) -> str:
    """Best-effort text rendering for log records. (Phase 2 will strip default.)"""
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
    cap = config.truncation.log_safe_text_max_chars
    for i, m in enumerate(messages):
        msg_type = getattr(m, "type", m.__class__.__name__)
        content = getattr(m, "content", m)
        rendered.append(f"[{i}] {msg_type}: {_safe_text(content, max_chars=cap)}")
    return "\n".join(rendered)


def _schema_json_for_prompt(schema) -> str:
    payload = schema.model_json_schema() if hasattr(schema, "model_json_schema") else schema
    return json.dumps(payload, ensure_ascii=False)


def _structured_messages(messages, schema):
    schema_name = getattr(schema, "__name__", "StructuredOutput")
    instruction = (
        "Return only a valid JSON object. Do not wrap it in markdown. "
        f"The JSON object must validate against the {schema_name} schema below:\n"
        f"{_schema_json_for_prompt(schema)}"
    )
    copied = list(messages)
    if copied and isinstance(copied[0], SystemMessage):
        first = copied[0]
        copied[0] = SystemMessage(content=f"{first.content}\n\n{instruction}")
        return copied
    return [SystemMessage(content=instruction), *copied]


def _parser_llm_output(exc: Exception) -> str | None:
    if isinstance(exc, OutputParserException):
        output = getattr(exc, "llm_output", None)
        return output if isinstance(output, str) and output.strip() else None
    return None


def _json_repair_message(exc: Exception, llm_output: str, *, max_chars: int) -> HumanMessage:
    truncated = llm_output[:max_chars]
    return HumanMessage(
        content=(
            "Your previous response was rejected because it was not valid JSON. "
            f"Parser error: {exc}\n\n"
            "Return a complete corrected JSON object only. Preserve the intended analysis, "
            "but ensure every string is valid JSON: escape internal double quotes, backslashes, "
            "and control characters. Do not wrap the response in markdown.\n\n"
            f"Previous invalid response:\n{truncated}"
        )
    )


def invoke_structured(
    schema,
    messages,
    *,
    agent: str,
    max_tokens: int = 4096,
    temperature: float = 0.1,
    use_agent_model: bool = True,
):
    """Structured LLM call. (Phase 2 will strip these defaults.)

    Doubles ``max_tokens`` on truncation up to ``config.llm.max_tokens_ceiling`` without consuming
    a retry. All other errors retry with exponential backoff up to
    ``config.llm.invoke_max_attempts``; only ``ReviewStoppedError`` short-circuits.
    """
    raise_if_review_stopped()
    locale_state = locale_runtime_state.get()
    requested_locale = normalize_locale(
        locale_state.requested_locale if locale_state is not None else DEFAULT_LOCALE
    )
    localized_messages = inject_locale_instruction(messages, requested_locale)
    structured_messages = _structured_messages(localized_messages, schema)
    schema_name = getattr(schema, "__name__", "StructuredOutput")
    ceiling = config.llm.max_tokens_ceiling
    length_markers = config.llm.length_markers
    log_cap = config.truncation.log_safe_text_max_chars
    tokens = max_tokens
    flow_log = _agent_flow_logger(agent)
    max_attempts = max(1, int(config.llm.invoke_max_attempts))
    attempt = 0
    base = None
    cached_tokens: int | None = None
    while True:
        raise_if_review_stopped()
        attempt += 1
        if base is None or cached_tokens != tokens:
            base = make_llm(
                max_tokens=tokens,
                agent=agent if use_agent_model else None,
                temperature=temperature,
            )
            cached_tokens = tokens
        llm = base.with_structured_output(schema, method="json_mode")
        log.info(
            "LLM input agent=%r model=%r max_tokens=%d temperature=%.2f attempt=%d/%d messages=%d",
            agent,
            getattr(base, "model_name", "unknown"),
            tokens,
            temperature,
            attempt,
            max_attempts,
            len(structured_messages),
        )
        flow_log.info(
            "LLM input model=%r max_tokens=%d temperature=%.2f attempt=%d/%d\n%s",
            getattr(base, "model_name", "unknown"),
            tokens,
            temperature,
            attempt,
            max_attempts,
            _messages_for_log(structured_messages),
        )
        try:
            result = llm.invoke(structured_messages)
            raise_if_review_stopped()
            if requested_locale != DEFAULT_LOCALE:
                result = _localize_structured_result(result, schema, agent, requested_locale)
            if locale_state is not None and requested_locale == DEFAULT_LOCALE:
                locale_state.content_locale = DEFAULT_LOCALE
            log.info("LLM output agent=%r schema=%s", agent, schema_name)
            flow_log.info("LLM output\n%s", _safe_text(result, max_chars=log_cap))
            return result
        except ReviewStoppedError:
            raise
        except Exception as exc:
            msg = str(exc).lower()
            parser_output = _parser_llm_output(exc)
            if any(m in msg for m in length_markers) and tokens < ceiling:
                tokens = min(tokens * 2, ceiling)
                log.info(
                    "structured output truncated for agent %r — retrying with max_tokens=%d",
                    agent,
                    tokens,
                )
                flow_log.info("structured output truncated — retrying with max_tokens=%d", tokens)
                attempt -= 1
                continue
            if attempt >= max_attempts:
                log.exception(
                    "LLM invoke failed agent=%r attempt=%d/%d — giving up",
                    agent,
                    attempt,
                    max_attempts,
                )
                flow_log.exception(
                    "LLM invoke failed attempt=%d/%d — giving up", attempt, max_attempts
                )
                if parser_output is not None:
                    raise StructuredLLMOutputError(
                        agent=agent,
                        schema_name=schema_name,
                    ) from exc
                raise
            if parser_output is not None:
                structured_messages = _structured_messages(
                    [
                        *localized_messages,
                        _json_repair_message(exc, parser_output, max_chars=log_cap),
                    ],
                    schema,
                )
            backoff = _retry_backoff_seconds(attempt)
            log.warning(
                "LLM invoke failed agent=%r attempt=%d/%d err=%s — retrying in %.1fs",
                agent,
                attempt,
                max_attempts,
                exc,
                backoff,
            )
            flow_log.warning(
                "LLM invoke failed attempt=%d/%d err=%s — retrying in %.1fs",
                attempt,
                max_attempts,
                exc,
                backoff,
            )
            _interruptible_sleep(backoff)


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
    max_attempts = max(1, int(config.llm.invoke_max_attempts))
    base_seconds = max(0.0, config.llm.retry_base_seconds)
    cap_seconds = max(base_seconds, config.llm.retry_max_seconds)
    base = make_llm(
        max_tokens=config.llm.translation_max_tokens,
        temperature=config.llm.translation_temperature,
    )
    llm = base.with_structured_output(_TranslationBatch, method="json_mode")
    for batch in chunk_strings(strings):
        messages = _structured_messages(
            [
                SystemMessage(
                    content=(
                        f"Translate each input string into {locale_name}. Return JSON only. "
                        "Preserve stock tickers, acronyms, numbers, dates, punctuation, and "
                        "terse financial formatting. Do not add commentary."
                    )
                ),
                HumanMessage(content=json.dumps(batch, ensure_ascii=False)),
            ],
            _TranslationBatch,
        )

        def attempt(messages=messages, batch=batch) -> list[str]:
            raise_if_review_stopped()
            raw_result = llm.invoke(messages)
            result = _TranslationBatch.model_validate(raw_result)
            translated = list(result.translated)
            if len(translated) != len(batch):
                raise ValueError("translation batch length mismatch")
            return translated

        def on_attempt(att: int, exc: Exception, delay: float) -> None:
            log.warning(
                "translation batch failed attempt=%d/%d err=%s — retrying in %.1fs",
                att,
                max_attempts,
                exc,
                delay,
            )

        try:
            outputs.extend(
                with_retry(
                    attempt,
                    attempts=max_attempts,
                    base=base_seconds,
                    cap=cap_seconds,
                    on_attempt=on_attempt,
                    sleep=_interruptible_sleep,
                    stop_on=ReviewStoppedError,
                )
            )
        except ReviewStoppedError:
            raise
        except Exception as exc:
            log.warning("translation batch failed after %d attempts: %s", max_attempts, exc)
            raise
    return outputs


def freeze_agent_models(raw: dict[str, str] | None) -> tuple[tuple[str, str], ...] | None:
    """Validate supplied per-agent model routing and return immutable known-key pairs."""
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
