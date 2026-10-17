from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from arena.schemas import ArenaPosition


class ParseCsvRequest(BaseModel):
    csv_text: str


class ParseCsvResponse(BaseModel):
    positions: list[ArenaPosition]


class ArenaDefaults(BaseModel):
    starting_cash: float
    transaction_cost_bps: float
    max_position_weight: float
    max_holdings: int
    cash_return_annual_pct: float
    min_trade_value: float
    min_cash_weight: float
    benchmark: str
    trade_time: str
    timezone: str
    corporate_actions: str
    advisor_timeout_seconds: int


class CompetitionSummary(BaseModel):
    run_id: str
    run_name: str
    status: str
    rounds: int
    last_round_date: str | None
    standings: dict[str, float]
    agent_status: dict[str, dict[str, Any]]
