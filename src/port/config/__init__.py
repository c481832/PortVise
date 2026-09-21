"""Load the TOML configuration and expose it as the `config` proxy.

`load()` must run before any attribute read on `config`.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from port.config.schema import RootConfig

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.toml"
LOCAL_CONFIG_PATH = REPO_ROOT / "config.local.toml"


class ConfigNotLoadedError(RuntimeError):
    pass


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
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _drop_obsolete_config_keys(data: dict) -> None:
    llm = data.get("llm")
    if isinstance(llm, dict):
        llm.pop("reasoning_enabled", None)
    data.pop("agent_reasoning", None)


_loaded: RootConfig | None = None


def load(toml_path: Path | None = None) -> RootConfig:
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
        raise ConfigNotLoadedError("port.config.load() must be called before accessing config.")
    return _loaded


class _ConfigProxy:
    __slots__ = ()

    def __getattr__(self, name: str):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return getattr(_get(), name)

    def __repr__(self) -> str:
        return f"<_ConfigProxy loaded={_loaded is not None}>"


config = _ConfigProxy()
