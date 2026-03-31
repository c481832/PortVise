from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from port.models import RegimeReview, RiskReview, ThemeReview, ValidationReview


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


def market_data_to_text(md) -> str:
    """Render a MarketData snapshot as compact text for injection into agent prompts."""
    lines = ["=== LIVE MARKET DATA ===", ""]

    if md.indicators:
        lines.append("MARKET INDICATORS:")
        for ind in md.indicators:
            lines.append(
                f"  {ind.label:<22} {ind.current:>9.2f}  "
                f"1d: {ind.change_1d_pct:+5.1f}%  1m: {ind.change_1m_pct:+5.1f}%"
            )
        lines.append("")

    if md.positions:
        lines.append("POSITION SNAPSHOTS:")
        for snap in md.positions:
            lines.append(
                f"  {snap.ticker:<6}  ${snap.current_price:>9.2f}  "
                f"1d: {snap.change_1d_pct:+5.1f}%  1w: {snap.change_1w_pct:+5.1f}%  "
                f"1m: {snap.change_1m_pct:+5.1f}%  3m: {snap.change_3m_pct:+5.1f}%  "
                f"52w hi: ${snap.week_52_high:.2f} ({snap.pct_from_52w_high:+.1f}%)"
            )
            for h in snap.recent_headlines[:3]:
                lines.append(f"    • {h}")
            lines.append("")

    if md.errors:
        lines.append(f"Fetch errors: {', '.join(md.errors)}")

    lines.append(f"Data as of: {md.fetched_at}")
    return "\n".join(lines)


def news_to_text(news) -> str:
    """Render a NewsReview as compact text for injection into downstream agent prompts."""
    lines = ["=== MARKET CONTEXT (News Agent) ===", ""]
    lines.append(news.macro_context)
    lines.append("")

    if news.market_themes:
        lines.append("Themes: " + " | ".join(news.market_themes))

    if news.key_events:
        lines.append("Key events: " + "; ".join(news.key_events))

    if news.thesis_risks:
        lines.append("Thesis risks: " + "; ".join(news.thesis_risks))

    if news.summary:
        lines.append(news.summary)

    return "\n".join(lines)


def render_risk(r: RiskReview) -> str:
    lines = [f"=== RISK REPORT (risk score: {r.risk_score}/10) ==="]
    lines.append(f"Summary: {r.summary}")
    if r.factor_exposures:
        lines.append("Factor exposures:")
        for fe in r.factor_exposures:
            lines.append(
                f"  - {fe.factor} ({fe.direction}, {fe.magnitude}): "
                f"{', '.join(fe.positions_driving)}"
            )
    if r.concentration_issues:
        lines.append("Concentration issues: " + "; ".join(r.concentration_issues))
    if r.scenario_losses:
        lines.append("Scenario losses:")
        for s in r.scenario_losses:
            lines.append(f"  - {s.scenario}: {s.estimated_portfolio_loss_pct:+.1f}%")
    if r.fragilities:
        lines.append("Fragilities: " + "; ".join(r.fragilities))
    return "\n".join(lines)


def render_regime(r: RegimeReview) -> str:
    lines = [
        f"=== REGIME REPORT (fit score: {r.portfolio_fit_score}/10, "
        f"regime confidence: {r.regime_confidence}/10) ===",
        f"Regime: {r.current_regime}",
        f"Summary: {r.summary}",
    ]
    if r.mismatches:
        lines.append("Mismatches: " + "; ".join(r.mismatches))
    if r.regime_appropriate_tilts:
        lines.append("Appropriate tilts: " + "; ".join(r.regime_appropriate_tilts))
    return "\n".join(lines)


def render_theme(t: ThemeReview) -> str:
    lines = [f"=== THEME REPORT (alignment score: {t.alignment_score}/10) ==="]
    lines.append(f"Summary: {t.summary}")
    if t.theme_alignments:
        lines.append("Theme alignments:")
        for ta in t.theme_alignments:
            lines.append(
                f"  - {ta.theme}: {ta.portfolio_stance} ({', '.join(ta.relevant_positions)})"
            )
    if t.crowding_risks:
        lines.append("Crowding risks: " + "; ".join(t.crowding_risks))
    if t.momentum_conflicts:
        lines.append("Momentum conflicts: " + "; ".join(t.momentum_conflicts))
    return "\n".join(lines)


def render_validation(v: ValidationReview) -> str:
    lines = [f"=== VALIDATION SYNTHESIS (confidence score: {v.confidence_score}/10) ==="]
    lines.append(f"Summary: {v.summary}")
    if v.critical_issues:
        lines.append("Critical issues:")
        for ci in v.critical_issues:
            lines.append(
                f"  [{ci.severity.upper()}] {ci.issue} "
                f"(positions: {', '.join(ci.affected_positions)}; "
                f"flagged by: {', '.join(ci.source_agents)})"
            )
    if v.thesis_breaks:
        lines.append("Thesis breaks: " + "; ".join(v.thesis_breaks))
    if v.internal_contradictions:
        lines.append("Internal contradictions: " + "; ".join(v.internal_contradictions))
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
