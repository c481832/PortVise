"""Parse structured payloads into domain models (single place for I/O shape)."""

from __future__ import annotations

from typing import Any

from port.models import MarketData
from port.portfolio import Portfolio


class DataLoader:
    """Build domain objects from JSON-compatible dicts passed into `run_analysis`."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def portfolio(self) -> Portfolio:
        raw = self._payload.get("portfolio")
        if not isinstance(raw, dict):
            raise ValueError("payload['portfolio'] must be a dict")
        return Portfolio.model_validate(raw)

    def market_data(self) -> MarketData | None:
        raw = self._payload.get("market_data")
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ValueError("payload['market_data'] must be a dict or null")
        return MarketData.model_validate(raw)

    def optional_params(self) -> dict[str, Any]:
        p = self._payload.get("params")
        return p if isinstance(p, dict) else {}
