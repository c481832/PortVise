"""Per-agent task summary shown in the UI."""

from __future__ import annotations

from pydantic import BaseModel, field_validator

from port.models.normalizers import IGNORE_EXTRA, coerce_string_list


class AgentTaskSummary(BaseModel):
    model_config = IGNORE_EXTRA

    title: str
    summary: str
    bullets: list[str]

    @field_validator("bullets", mode="before")
    @classmethod
    def _bullets(cls, v):
        return coerce_string_list(v)
