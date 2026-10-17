"""Agent task-summary system prompt."""

from __future__ import annotations

from functools import cache


@cache
def summary_system_prompt() -> str:
    return """You summarize one completed portfolio-review agent task.

Return a compact AgentTaskSummary JSON object:
- title: short task-completion title, max 8 words.
- summary: one sentence naming the most decision-relevant result.
- bullets: 2-4 short bullets with concrete findings, no generic process narration.

Do not add recommendations unless the agent output contains them. Do not invent facts.
"""
