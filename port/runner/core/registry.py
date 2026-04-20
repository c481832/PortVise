"""Task registry for deterministic analysis functions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

TASK_REGISTRY: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def register_task(name: str):
    def decorator(func: Callable[[dict[str, Any]], dict[str, Any]]):
        TASK_REGISTRY[name] = func
        return func

    return decorator


def list_tasks() -> tuple[str, ...]:
    return tuple(sorted(TASK_REGISTRY.keys()))
