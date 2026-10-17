"""Market data snapshots and macro indicators."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PositionSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ticker: str
    current_price: float
    change_1d_pct: float
    change_1w_pct: float
    change_1m_pct: float
    change_1y_pct: float
    change_3m_pct: float
    week_52_high: float
    pct_from_52w_high: float
    dividend: float
    split: float


class TickerProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ticker: str
    name: str = ""
    sector: str = ""


class MarketIndicator(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ticker: str
    label: str
    current: float
    change_1d_pct: float
    change_1w_pct: float
    change_1m_pct: float
    change_3m_pct: float
    change_1y_pct: float
    week_52_high: float
    pct_from_52w_high: float


class MarketData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    positions: list[PositionSnapshot] = Field(default_factory=list)
    indicators: list[MarketIndicator]
    fetched_at: str
