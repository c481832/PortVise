from __future__ import annotations

import tomllib
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = PACKAGE_ROOT / "config.toml"
LOCAL_CONFIG_PATH = PACKAGE_ROOT / "config.local.toml"


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


def read_toml(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def read_config() -> Config:
    data = read_toml(DEFAULT_CONFIG_PATH)
    if LOCAL_CONFIG_PATH.exists():
        apply_local_overrides(data, read_toml(LOCAL_CONFIG_PATH))
    return Config(data)


config = read_config()


def reload() -> None:
    config._data = read_config()._data
