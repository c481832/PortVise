"""Map features / snapshots to a stable regime identifier string."""

from __future__ import annotations

from typing import TYPE_CHECKING

from port.regime_signals import infer_state_vector, regime_id_from_state_vector

if TYPE_CHECKING:
    from port.models import MarketData


def classify_regime_id(md: MarketData | None) -> str:
    sv = infer_state_vector(md)
    return regime_id_from_state_vector(sv)
