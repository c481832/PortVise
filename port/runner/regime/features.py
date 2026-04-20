"""Regime feature vector from live market snapshots."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from port.regime_signals import infer_state_vector

if TYPE_CHECKING:
    from port.models import MarketData


def build_regime_features(md: MarketData | None) -> dict[str, Any]:
    """Authoritative coarse features (aligned with `RegimeStateVector`)."""
    sv = infer_state_vector(md)
    return sv.model_dump()
