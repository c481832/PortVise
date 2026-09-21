"""Shared exposure layer, referenced by risk, regime and theme reviews."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from port.models.normalizers import IGNORE_EXTRA


class ExposureLayer(BaseModel):
    """Cross-agent hook: same portfolio can be described in narrative vs macro vs factor space."""

    model_config = IGNORE_EXTRA

    layer: Literal["theme", "regime", "factor"]
    label: str
    strength: float = Field(
        ge=-1.0,
        le=1.0,
        description="Signed strength in this layer (e.g. theme tilt, macro beta proxy).",
    )
    maps_to: list[str] = Field(
        description="Other layers or tags this exposure links to (e.g. 'growth factor', 'semis').",
    )

    @field_validator("strength", mode="before")
    @classmethod
    def _normalize_strength(cls, value):
        if value is None or isinstance(value, bool):
            raise ValueError(f"strength must be a real number in [-1, 1]; got {value!r}")
        try:
            x = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"strength must be a real number; got {value!r}") from exc
        if x != x:
            raise ValueError("strength is NaN")
        if not (-1.0 <= x <= 1.0):
            raise ValueError(f"strength must be in [-1, 1]; got {x}")
        return x
