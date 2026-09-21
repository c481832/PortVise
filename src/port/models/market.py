"""Market data snapshots and macro indicators."""

from __future__ import annotations

from pydantic import BaseModel, Field

from port.models.normalizers import IGNORE_EXTRA


class PositionSnapshot(BaseModel):
    model_config = IGNORE_EXTRA

    ticker: str
    current_price: float
    prev_close: float
    change_1d_pct: float
    change_1w_pct: float
    change_1m_pct: float
    change_1y_pct: float
    change_3m_pct: float
    week_52_high: float
    week_52_low: float
    pct_from_52w_high: float
    dividend: float
    split: float


class TickerProfile(BaseModel):
    model_config = IGNORE_EXTRA

    ticker: str
    name: str = ""
    sector: str = ""
    industry: str = ""


class MarketIndicator(BaseModel):
    model_config = IGNORE_EXTRA

    ticker: str
    label: str
    current: float
    prev_close: float
    change_1d_pct: float
    change_1w_pct: float
    change_1m_pct: float
    change_3m_pct: float
    change_1y_pct: float
    week_52_high: float
    week_52_low: float
    pct_from_52w_high: float


class MarketData(BaseModel):
    model_config = IGNORE_EXTRA

    positions: list[PositionSnapshot] = Field(default_factory=list)
    indicators: list[MarketIndicator]
    fetched_at: str
