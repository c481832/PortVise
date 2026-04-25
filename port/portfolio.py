from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from port.models import NewsFocus

if TYPE_CHECKING:
    from port.models import RegimeReview, RiskReview, ThemeReview, ValidationReview


class Position(BaseModel):
    ticker: str
    name: str
    weight: float  # decimal, e.g. 0.08 for 8%
    quantity: float = 0.0  # shares/units; used for value and open PnL in UI
    sector: str
    entry_date: date
    entry_price: float
    current_price: float
    dividend: float = Field(default=0.0, ge=0.0)  # cumulative cash dividends per entry share
    split: float = Field(default=1.0, gt=0.0)  # current shares per entry share
    entry_thesis: str
    asset_class: str = "equity"
    country: str = "US"
    tags: list[str] = Field(default_factory=list)

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


def portfolio_to_text(portfolio: Portfolio) -> str:
    pos_sum = sum(p.quantity * p.current_price for p in portfolio.positions)
    cw = portfolio.cash_weight
    if cw <= 0:
        cash_line = f"Cash: $0 {portfolio.base_currency}"
    elif cw < 1.0:
        cash_usd = cw * float(pos_sum) / (1.0 - cw)
        cash_line = f"Cash: ${cash_usd:,.0f} {portfolio.base_currency}"
    else:
        cash_line = f"Cash: entire portfolio in {portfolio.base_currency} (no position MV to size)"
    lines = [
        f"PORTFOLIO: {portfolio.name}  |  Benchmark: {portfolio.benchmark}"
        f"  |  Date: {portfolio.review_date}",
        cash_line,
        "",
        "POSITIONS:",
    ]
    for p in portfolio.positions:
        pnl = p.pnl_pct
        sign = "+" if pnl >= 0 else ""
        lines.append(
            f"  {p.ticker:<6} | {p.weight * 100:5.1f}% | {p.sector:<20} | "
            f"Entry: {p.entry_date} @ ${p.entry_price:.2f}"
            f" → ${p.current_price:.2f} ({sign}{pnl:.1f}%)"
        )
        if p.tags:
            lines.append(f"         | Tags: {', '.join(p.tags)}")
        lines.append(f"         | Asset class: {p.asset_class} | Country: {p.country}")
        lines.append(f'         | Thesis: "{p.entry_thesis}"')
        lines.append("")

    if portfolio.context_note:
        lines.append(f"CONTEXT: {portfolio.context_note}")

    return "\n".join(lines)


def news_focus_to_text(focus: NewsFocus) -> str:
    """What the news agent should prioritise: portfolio goal + each position thesis."""
    lines = [
        "=== SEARCH PRIORITIES (use these to filter what matters) ===",
        "",
        "1) PORTFOLIO GOAL — prioritise macro and market developments that affect this objective:",
        focus.portfolio_goal or "(none stated)",
        "",
        "2) POSITION GOALS (entry thesis per name) — prioritise ticker/sector news and flows "
        "that support or challenge each thesis:",
    ]
    for pg in focus.position_goals:
        g = pg.goal.strip() if pg.goal else ""
        lines.append(f"  • {pg.ticker}: {g or '(no thesis stated)'}")
        lq = (pg.latest_news_query or "").strip()
        if lq:
            lines.append(f"      → planned query (latest news): {lq}")
    pq = [q.strip() for q in focus.portfolio_search_queries if q and q.strip()]
    if pq:
        lines.append("")
        lines.append("3) PLANNED SEARCH QUERIES (portfolio-wide — run with search tools first):")
        for q in pq:
            lines.append(f"  • {q}")
    mi = [str(x).strip() for x in focus.macro_indicator_tickers if x and str(x).strip()]
    if mi:
        lines.append("")
        lines.append(
            "4) PLANNED MACRO PRICE FETCHES (data agent runs in parallel with news tools): "
            + ", ".join(mi)
        )
    lines.append("")
    lines.append(
        "Tailor key_events, market_themes, thesis_risks, and macro_context toward items above "
        "where recent facts exist; deprioritise generic filler unrelated to these goals."
    )
    return "\n".join(lines)


def _dedupe_queries_preserve_order(queries: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        if q in seen:
            continue
        seen.add(q)
        out.append(q)
    return out


def planned_news_tool_queries(focus: NewsFocus) -> list[str]:
    """Web search strings in planner order (three macro topics, then one per ticker).

    Duplicate strings are kept once (first occurrence) to avoid redundant network calls.
    """
    out: list[str] = []
    pq = [q.strip() for q in focus.portfolio_search_queries if q and q.strip()]
    out.extend(pq)

    for pg in focus.position_goals:
        lq = (pg.latest_news_query or "").strip()
        if lq:
            out.append(lq)

    if out:
        return _dedupe_queries_preserve_order(out)

    if focus.position_goals:
        seeds: list[str] = []
        for pg in focus.position_goals:
            t = (pg.ticker or "").strip().upper()
            if t:
                seeds.append(f"latest news for {t}")
        if seeds:
            return _dedupe_queries_preserve_order(seeds)

    return ["US stock market macro news week"]


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
                f"1m: {snap.change_1m_pct:+5.1f}%  1y: {snap.change_1y_pct:+5.1f}%  "
                f"3m: {snap.change_3m_pct:+5.1f}%  "
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
    if r.factor_loadings:
        lines.append(
            "Factor loadings (engine): "
            + ", ".join(f"{k}={v:+.2f}" for k, v in r.factor_loadings.items())
        )
    if r.top_risks:
        lines.append("Top risks: " + "; ".join(r.top_risks))
    if r.worst_scenario:
        lines.append(
            f"Worst scenario (engine): {r.worst_scenario.name} "
            f"({r.worst_scenario.estimated_portfolio_loss_pct:+.2f}%)"
        )
    if r.hidden_concentration:
        lines.append("Hidden concentration: " + "; ".join(r.hidden_concentration))
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
    sv = r.state_vector
    lines = [
        f"=== REGIME REPORT (fit score: {r.portfolio_fit_score}/10, "
        f"regime confidence: {r.regime_confidence}/10) ===",
        f"Regime id: {r.current_regime}",
        (
            f"State vector: inflation {sv.inflation_trend}, rates {sv.rates_trend}, "
            f"growth {sv.growth_trend}, liquidity {sv.liquidity}, vol {sv.volatility}"
        ),
        f"Summary: {r.summary}",
    ]
    if r.fit_notes:
        lines.append("Fit notes: " + "; ".join(r.fit_notes))
    ho = r.historical_outcome
    lines.append(f"Historical analogs: {ho.message}")
    if r.mismatch_drivers:
        lines.append("Mismatch drivers: " + "; ".join(r.mismatch_drivers))
    if r.mismatches:
        lines.append("Mismatches: " + "; ".join(r.mismatches))
    if r.regime_appropriate_tilts:
        lines.append("Appropriate tilts: " + "; ".join(r.regime_appropriate_tilts))
    return "\n".join(lines)


def render_theme(t: ThemeReview) -> str:
    lines = [f"=== THEME REPORT (alignment score: {t.alignment_score}/10) ==="]
    if t.implicit_portfolio_bet:
        lines.append(f"Implicit bet: {t.implicit_portfolio_bet}")
    lines.append(f"Summary: {t.summary}")
    if t.scored_themes:
        lines.append("Scored themes:")
        for st in t.scored_themes:
            lines.append(
                f"  - {st.theme}: exposure={st.portfolio_exposure:.2f}, "
                f"news={st.news_strength:.2f}, conf={st.confidence:.2f} "
                f"({', '.join(st.supporting_assets)})"
            )
    syn = t.synthesis
    if syn.dominant_themes:
        lines.append("Dominant themes: " + "; ".join(syn.dominant_themes))
    if syn.redundant_expressions:
        lines.append("Redundant expressions: " + "; ".join(syn.redundant_expressions))
    if syn.missing_exposures:
        lines.append("Missing exposures: " + "; ".join(syn.missing_exposures))
    if syn.theme_drift_note:
        lines.append(f"Theme drift: {syn.theme_drift_note}")
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

