"""Single entrypoint: dispatch by task name (no LLM, deterministic)."""

from __future__ import annotations

from typing import Any

from port.runner.core.registry import TASK_REGISTRY


def run_analysis(task: str, payload: dict[str, Any]) -> dict[str, Any]:
    if task not in TASK_REGISTRY:
        raise ValueError(f"Unknown task: {task!r}; known: {sorted(TASK_REGISTRY)}")
    return TASK_REGISTRY[task](payload)
