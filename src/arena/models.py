from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_TRADE_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ArenaPosition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ticker: str
    name: str
    quantity: float = Field(ge=0.0)
    sector: str
    entry_date: date
    entry_price: float = Field(gt=0.0)
    entry_thesis: str

    @field_validator("ticker", mode="before")
    @classmethod
    def _ticker(cls, value: object) -> str:
        return str(value).strip().upper()


class ArenaConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_name: str
    starting_cash: float = Field(ge=0.0)
    positions: list[ArenaPosition]
    watchlist: list[str]
    benchmark: str
    rebalance_cadence: Literal["daily-close"] = "daily-close"
    transaction_cost_bps: float = Field(ge=0.0)
    max_position_weight: float = Field(gt=0.0, le=1.0)
    max_holdings: int = Field(gt=0)
    cash_return_annual_pct: float = Field(default=0.0, ge=0.0)
    min_trade_value: float = Field(ge=0.0)
    min_cash_weight: float = Field(ge=0.0, le=1.0)
    corporate_actions: Literal["best_effort", "strict", "off"]
    advisor_timeout_seconds: int = Field(default=1800, ge=0)
    trade_time: str = "16:10"
    timezone: str = "America/New_York"
    notes: str = ""

    @field_validator("trade_time", mode="before")
    @classmethod
    def _trade_time(cls, value: object) -> str:
        s = str(value).strip()
        if not _TRADE_TIME_RE.match(s):
            raise ValueError(f"trade_time must be 24-hour HH:MM, got {value!r}")
        return s

    @field_validator("timezone", mode="before")
    @classmethod
    def _timezone(cls, value: object) -> str:
        s = str(value).strip()
        try:
            ZoneInfo(s)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"timezone must be a valid IANA zone, got {value!r}") from exc
        return s

    @field_validator("watchlist", mode="before")
    @classmethod
    def _watchlist(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("watchlist must be a list")
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            ticker = str(item).strip().upper()
            if ticker and ticker not in seen:
                out.append(ticker)
                seen.add(ticker)
        return out

    @field_validator("benchmark", mode="before")
    @classmethod
    def _benchmark(cls, value: object) -> str:
        s = str(value).strip().upper()
        if not s:
            raise ValueError("benchmark cannot be empty")
        return s

    @model_validator(mode="after")
    def _positions_in_watchlist(self) -> ArenaConfig:
        known = set(self.watchlist)
        missing = [p.ticker for p in self.positions if p.ticker not in known]
        if missing:
            raise ValueError("starting positions must be in watchlist: " + ", ".join(missing))
        return self


class Holding(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ticker: str
    quantity: float = Field(ge=0.0)
    average_cost: float = Field(ge=0.0)


class PortfolioState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    agent_id: str
    as_of: str
    cash: float = Field(ge=0.0)
    holdings: dict[str, Holding]
    last_prices: dict[str, float]
    equity: float = Field(ge=0.0)


class MarketSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    as_of: str
    prices: dict[str, float]
    benchmark: str
    benchmark_price: float | None
    price_movement: dict[str, dict[str, float]]
    headlines: dict[str, list[str]]
    errors: list[str] = Field(default_factory=list)


class AgentDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    target_weights: dict[str, float] = Field(default_factory=dict)
    cash_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    rationale: str = ""
    risk_notes: list[str] = Field(default_factory=list)

    @field_validator("target_weights", mode="before")
    @classmethod
    def _target_weights(cls, value: object) -> dict[str, float]:
        if not isinstance(value, dict):
            raise ValueError("target_weights must be an object")
        out: dict[str, float] = {}
        for key, raw in value.items():
            ticker = str(key).strip().upper()
            if ticker:
                out[ticker] = float(raw)
        return out


class Trade(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ticker: str
    side: Literal["buy", "sell"]
    quantity: float
    price: float
    gross_value: float
    transaction_cost: float
    realized_pnl: float = 0.0
    cash_after: float = 0.0


class HoldingView(BaseModel):
    """Holding enriched with derived market values for the GUI. Never persisted."""

    model_config = ConfigDict(extra="ignore")

    ticker: str
    quantity: float
    average_cost: float
    price: float
    mkt_value: float
    unrealized_pnl: float
    weight: float


class LedgerEntry(BaseModel):
    """One persisted transaction line: a Trade plus the date it executed."""

    model_config = ConfigDict(extra="ignore")

    date: str
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float
    price: float
    gross_value: float
    transaction_cost: float
    realized_pnl: float = 0.0
    cash_after: float = 0.0


class AgentRoundResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    agent_id: str
    decision: AgentDecision
    trades: list[Trade] = Field(default_factory=list)
    corrections: list[str] = Field(default_factory=list)
    state: PortfolioState
    advisor_result_path: str | None = None


class RoundRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    round_id: str
    started_at: datetime
    snapshot: MarketSnapshot
    results: dict[str, AgentRoundResult]


class LeaderboardRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    agent_id: str
    rounds: int
    cumulative_return: float
    excess_return_vs_benchmark: float
    max_drawdown: float
    realized_volatility: float
    turnover: float
    transaction_costs: float
    cash_drag: float
    score: float
