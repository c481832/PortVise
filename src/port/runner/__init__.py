"""
Deterministic analysis runner: registry + `run_analysis(task, payload)`.

Import task modules so `@register_task` runs and populates `TASK_REGISTRY`.
"""

from __future__ import annotations

import port.runner.regime.runner  # noqa: F401
import port.runner.risk.runner  # noqa: F401
from port.runner.core.registry import register_task
from port.runner.core.runner import run_analysis

__all__ = ["register_task", "run_analysis"]
