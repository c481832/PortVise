"""Task registry and dispatch for the deterministic analysis tasks.

Tasks are plain functions registered by name; `run_analysis` is the only
entrypoint. Nothing here calls an LLM.
"""

from __future__ import annotations

from collections.abc import Callable

TaskFunc = Callable[[dict], dict]

TASK_REGISTRY: dict[str, TaskFunc] = {}


def register_task(name: str) -> Callable[[TaskFunc], TaskFunc]:
    def decorator(func: TaskFunc) -> TaskFunc:
        TASK_REGISTRY[name] = func
        return func

    return decorator


def run_analysis(task: str, payload: dict) -> dict:
    if task not in TASK_REGISTRY:
        raise ValueError(f"Unknown task: {task!r}; known: {sorted(TASK_REGISTRY)}")
    return TASK_REGISTRY[task](payload)
