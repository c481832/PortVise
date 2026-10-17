"""The portfolio under review: positions and book-level settings."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator


class Position(BaseModel):
    ticker: str
    name: str
    weight: float
    quantity: float
    sector: str
    entry_date: date
    entry_price: float
    current_price: float
    dividend: float = Field(default=0.0, ge=0.0)
    split: float = Field(default=1.0, gt=0.0)
    entry_thesis: str
    asset_class: str = "equity"

    @field_validator("ticker", mode="before")
    @classmethod
    def validate_ticker(cls, value: object) -> str:
        return str(value).strip().upper()

    @property
    def pnl_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        current_value = self.current_price * self.split + self.dividend
        return (current_value - self.entry_price) / self.entry_price * 100


class Portfolio(BaseModel):
    name: str
    positions: list[Position]
    cash_weight: float = 0.0
    base_currency: str = "USD"
    benchmark: str = "SPY"
    review_date: date = Field(default_factory=date.today)
    context_note: str = ""
