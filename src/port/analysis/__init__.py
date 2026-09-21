"""Deterministic analysis tasks: registry plus `run_analysis(task, payload)`.

Importing this package pulls in the task modules so their `@register_task`
decorators populate `TASK_REGISTRY`.
"""

from __future__ import annotations

import port.analysis.regime  # noqa: F401  (registers regime_analysis)
import port.analysis.risk  # noqa: F401  (registers risk_analysis)
from port.analysis.registry import register_task, run_analysis

__all__ = ["register_task", "run_analysis"]
