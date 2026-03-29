from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class Position(BaseModel):
    ticker: str
    name: str
    weight: float  # decimal, e.g. 0.08 for 8%
    sector: str
    entry_date: date
    entry_price: float
    current_price: float
    entry_thesis: str
    asset_class: str = "equity"
    country: str = "US"
    tags: list[str] = Field(default_factory=list)

    @property
    def pnl_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price * 100


class Portfolio(BaseModel):
    name: str
    positions: list[Position]
    cash_weight: float = 0.0
    base_currency: str = "USD"
    benchmark: str = "SPY"
    review_date: date = Field(default_factory=date.today)
    context_note: str = ""


def portfolio_to_text(portfolio: Portfolio) -> str:
    lines = [
        f"PORTFOLIO: {portfolio.name}  |  Benchmark: {portfolio.benchmark}  |  Date: {portfolio.review_date}",
        f"Cash: {portfolio.cash_weight * 100:.1f}%",
        "",
        "POSITIONS:",
    ]
    for p in portfolio.positions:
        pnl = p.pnl_pct
        sign = "+" if pnl >= 0 else ""
        lines.append(
            f"  {p.ticker:<6} | {p.weight * 100:5.1f}% | {p.sector:<20} | "
            f"Entry: {p.entry_date} @ ${p.entry_price:.2f} → ${p.current_price:.2f} ({sign}{pnl:.1f}%)"
        )
        if p.tags:
            lines.append(f"         | Tags: {', '.join(p.tags)}")
        lines.append(f"         | Asset class: {p.asset_class} | Country: {p.country}")
        lines.append(f"         | Thesis: \"{p.entry_thesis}\"")
        lines.append("")

    if portfolio.context_note:
        lines.append(f"CONTEXT: {portfolio.context_note}")

    return "\n".join(lines)


def news_to_text(news) -> str:
    """Render a NewsReview as compact text for injection into downstream agent prompts."""
    lines = ["=== CURRENT MARKET CONTEXT (News Agent) ===", ""]

    lines.append("MACRO ENVIRONMENT:")
    lines.append(news.macro_context)
    lines.append("")

    lines.append("DOMINANT MARKET THEMES:")
    for theme in news.market_themes:
        lines.append(f"  - {theme}")
    lines.append("")

    if news.material_events:
        lines.append("POSITION-LEVEL EVENTS:")
        for event in news.material_events:
            lines.append(
                f"  [{event.ticker}] {event.event}  "
                f"(impact: {event.impact_direction}, urgency: {event.urgency})"
            )
        lines.append("")

    if news.thesis_breaking_events:
        lines.append("THESIS-BREAKING EVENTS:")
        for e in news.thesis_breaking_events:
            lines.append(f"  !! {e}")
        lines.append("")

    if news.catalysts_ahead:
        lines.append("UPCOMING CATALYSTS:")
        for c in news.catalysts_ahead:
            lines.append(f"  - {c}")

    return "\n".join(lines)


# ── Example portfolio for quick testing ──────────────────────────────────────

def make_example_portfolio() -> Portfolio:
    return Portfolio(
        name="Growth Tilted Core",
        positions=[
            Position(
                ticker="NVDA",
                name="Nvidia",
                weight=0.12,
                sector="Technology",
                entry_date=date(2023, 6, 1),
                entry_price=380.0,
                current_price=875.0,
                entry_thesis="AI compute monopoly, data center capex supercycle driven by LLM training demand",
                tags=["AI", "semiconductors", "momentum", "data-center"],
            ),
            Position(
                ticker="MSFT",
                name="Microsoft",
                weight=0.10,
                sector="Technology",
                entry_date=date(2022, 10, 1),
                entry_price=240.0,
                current_price=415.0,
                entry_thesis="Azure cloud + Copilot AI monetisation; recurring revenue model with pricing power",
                tags=["cloud", "AI", "software", "quality"],
            ),
            Position(
                ticker="TLT",
                name="iShares 20Y Treasury",
                weight=0.10,
                sector="Fixed Income",
                entry_date=date(2023, 10, 1),
                entry_price=88.0,
                current_price=91.0,
                entry_thesis="Duration add at rate peak; Fed pivot trade for H1 2024",
                asset_class="bond",
                tags=["duration", "rates", "macro"],
            ),
            Position(
                ticker="XOM",
                name="ExxonMobil",
                weight=0.08,
                sector="Energy",
                entry_date=date(2022, 6, 1),
                entry_price=95.0,
                current_price=112.0,
                entry_thesis="Energy transition underinvestment; strong FCF, buybacks, dividend growth",
                tags=["energy", "value", "FCF", "inflation-hedge"],
            ),
            Position(
                ticker="JPM",
                name="JPMorgan Chase",
                weight=0.08,
                sector="Financials",
                entry_date=date(2023, 3, 1),
                entry_price=138.0,
                current_price=195.0,
                entry_thesis="Best-in-class bank; benefits from higher-for-longer rates via NIM expansion",
                tags=["financials", "rates", "quality"],
            ),
            Position(
                ticker="ASML",
                name="ASML Holding",
                weight=0.07,
                sector="Technology",
                entry_date=date(2023, 1, 1),
                entry_price=640.0,
                current_price=710.0,
                entry_thesis="EUV monopoly; only supplier of lithography tools enabling sub-5nm chips",
                country="NL",
                tags=["semiconductors", "capex", "monopoly", "international"],
            ),
        ],
        cash_weight=0.45,
        benchmark="SPY",
        review_date=date(2026, 3, 28),
        context_note=(
            "Reviewing after Q1 2026. Concerned about AI capex sustainability "
            "and rising rate volatility. Duration position has not worked as expected."
        ),
    )
