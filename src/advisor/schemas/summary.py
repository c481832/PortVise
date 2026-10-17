"""Per-agent task summary shown in the UI."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AgentTaskSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    summary: str
    bullets: list[str]
