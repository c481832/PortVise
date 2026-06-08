"""Request/response models for the arena GUI backend."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from arena.models import ArenaConfig, ArenaPosition


class ParseCsvRequest(BaseModel):
    csv_text: str


class ParseCsvResponse(BaseModel):
    positions: list[ArenaPosition]


class ArenaDefaults(BaseModel):
    """Default config values surfaced to pre-fill the setup form."""

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


class CreateCompetitionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_name: str
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
    corporate_actions: Literal["best_effort", "strict", "off"]
    advisor_timeout_seconds: int
    watchlist: list[str]
    positions: list[ArenaPosition]
    notes: str = ""

    def to_arena_config(self) -> ArenaConfig:
        return ArenaConfig(
            run_name=self.run_name,
            starting_cash=self.starting_cash,
            positions=self.positions,
            watchlist=self.watchlist,
            benchmark=self.benchmark,
            transaction_cost_bps=self.transaction_cost_bps,
            max_position_weight=self.max_position_weight,
            max_holdings=self.max_holdings,
            cash_return_annual_pct=self.cash_return_annual_pct,
            min_trade_value=self.min_trade_value,
            min_cash_weight=self.min_cash_weight,
            corporate_actions=self.corporate_actions,
            advisor_timeout_seconds=self.advisor_timeout_seconds,
            trade_time=self.trade_time,
            timezone=self.timezone,
            notes=self.notes,
        )


class CompetitionSummary(BaseModel):
    run_id: str
    run_name: str
    status: str
    rounds: int
    last_round_date: str | None
    standings: dict[str, float]  # agent_id -> cumulative_return
