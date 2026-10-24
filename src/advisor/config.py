from __future__ import annotations

import os
import tomllib
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.toml"
LOCAL_CONFIG_PATH = REPO_ROOT / "config.local.toml"

# Environment variables that override a config key (used by docker-compose).
# An empty value counts as unset, because compose passes `${VAR:-}` through as "".
ENV_OVERRIDES: dict[str, tuple[str, str]] = {
    "LLM_BASE_URL": ("llm", "base_url"),
    "LLM_MODEL": ("llm", "model"),
    "LLM_API_KEY": ("llm", "api_key"),
    "SEARXNG_URL": ("search", "searxng_url"),
    "TAVILY_API_KEY": ("search", "tavily_api_key"),
    "FRED_API_KEY": ("fred", "api_key"),
    "ADVISOR_LOG_FILE": ("log", "file"),
}

# Boolean environment overrides; the value must be exactly "true" or "false".
ENV_BOOL_OVERRIDES: dict[str, tuple[str, str]] = {
    "ADVISOR_LOCK_SETTINGS": ("server", "lock_settings"),
}


class ConfigKeyError(AttributeError, KeyError):
    def __str__(self) -> str:
        return str(self.args[0])


class Config(Mapping[str, Any]):
    __slots__ = ("_data", "_path")

    def __init__(self, data: dict[str, Any], path: str = "") -> None:
        self._path = path
        self._data = {key: wrap(value, self.key_path(key)) for key, value in data.items()}

    def key_path(self, key: str) -> str:
        return f"{self._path}.{key}" if self._path else key

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        return self[name]

    def __getitem__(self, key: str) -> Any:
        if key not in self._data:
            raise ConfigKeyError(f"config key {self.key_path(key)!r} is not set in config.toml")
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"Config({self._path or '<root>'}: {list(self._data)})"


def wrap(value: Any, path: str) -> Any:
    if isinstance(value, dict):
        return Config(value, path)
    if isinstance(value, list):
        return [wrap(item, f"{path}[{i}]") for i, item in enumerate(value)]
    return value


def apply_local_overrides(base: dict, local: dict, path: str = "") -> None:
    for key, value in local.items():
        key_path = f"{path}.{key}" if path else key
        if key not in base:
            raise ValueError(f"{LOCAL_CONFIG_PATH.name}: unknown key {key_path!r}")
        current = base[key]
        if isinstance(current, dict) != isinstance(value, dict):
            raise ValueError(
                f"{LOCAL_CONFIG_PATH.name}: {key_path!r} must be "
                f"{'a table' if isinstance(current, dict) else 'a value, not a table'}"
            )
        if isinstance(current, dict):
            apply_local_overrides(current, value, key_path)
        else:
            base[key] = value


def parse_env_bool(name: str, value: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(f"{name} must be 'true' or 'false', got {value!r}")


def read_toml(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def read_config() -> Config:
    data = read_toml(DEFAULT_CONFIG_PATH)
    if LOCAL_CONFIG_PATH.exists():
        apply_local_overrides(data, read_toml(LOCAL_CONFIG_PATH))
    for env_name, (section, key) in ENV_OVERRIDES.items():
        value = os.environ.get(env_name)
        if value:
            data[section][key] = value
    for env_name, (section, key) in ENV_BOOL_OVERRIDES.items():
        value = os.environ.get(env_name)
        if value:
            data[section][key] = parse_env_bool(env_name, value)
    return Config(data)


config = read_config()


def reload() -> None:
    config._data = read_config()._data
