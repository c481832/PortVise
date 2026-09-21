"""Upstream input completeness gate."""

from __future__ import annotations

from pydantic import BaseModel

from port.models.normalizers import IGNORE_EXTRA


class ValidationReview(BaseModel):
    model_config = IGNORE_EXTRA

    summary: str
