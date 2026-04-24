from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_IGNORE_EXTRA = ConfigDict(extra="ignore")


# ── Enum normalizers ──────────────────────────────────────────────────────────


def _norm_impact(v: str) -> str:
    return {
        "positive": "positive",
        "negative": "negative",
        "neutral": "neutral",
        "uncertain": "uncertain",
        "pos": "positive",
        "neg": "negative",
    }.get(str(v).lower(), "uncertain")


def _norm_urgency(v: str) -> str:
    s = str(v).lower()
    if s in ("immediate", "critical", "high", "urgent"):
        return "immediate"
    if s in ("this-week", "this_week", "thisweek", "medium", "moderate"):
        return "this-week"
    if s in ("low", "watch", "low-priority"):
        return "low"
    return "monitor"


def _norm_direction(v: str) -> str:
    return {
        "long": "long",
        "short": "short",
        "neutral": "neutral",
        "overweight": "long",
        "underweight": "short",
    }.get(str(v).lower(), "neutral")


def _norm_magnitude(v: str) -> str:
    return {
        "high": "high",
        "medium": "medium",
        "low": "low",
        "large": "high",
        "small": "low",
        "moderate": "medium",
    }.get(str(v).lower(), "medium")


def _norm_severity(v: str) -> str:
    return {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "low": "low",
        "severe": "critical",
        "major": "high",
        "minor": "low",
    }.get(str(v).lower(), "medium")


def _norm_stance(v: str) -> str:
    return {
        "aligned": "aligned",
        "fighting": "fighting",
        "neutral": "neutral",
        "overweight": "overweight",
        "underweight": "underweight",
        "long": "aligned",
        "short": "fighting",
    }.get(str(v).lower(), "neutral")


def _norm_action_type(v: str) -> str:
    return {
        "reduce": "reduce",
        "exit": "exit",
        "hedge": "hedge",
        "rotate": "rotate",
        "add": "add",
        "monitor": "monitor",
        "no-action": "no-action",
        "sell": "exit",
        "trim": "reduce",
        "buy": "add",
        "no_action": "no-action",
        "hold": "monitor",
    }.get(str(v).lower(), "monitor")


def _norm_priority(v: str) -> str:
    s = str(v).lower()
    if s in ("urgent", "immediate", "critical", "high"):
        return "urgent"
    if s in ("this-week", "this_week", "thisweek", "medium", "short-term"):
        return "this-week"
    if s in ("next-review", "next_review", "low", "medium-term"):
        return "next-review"
    return "watch"


def _norm_portfolio_stance(v: str) -> str:
    s = str(v).lower()
    if s in ("defensive", "risk-off", "risk_off", "de-risk", "derisk"):
        return "defensive"
    if s in ("opportunistic", "risk-on", "risk_on", "offensive"):
        return "opportunistic"
    if s in ("wait", "hold", "stand-pat", "stand_pat", "no-action", "no_action"):
        return "wait"
    if s in ("balanced", "neutral"):
        return "balanced"
    return "balanced"


def _norm_action_scope(v: str) -> str:
    s = str(v).lower()
    if s in ("portfolio", "portfolio-level", "portfolio_level", "book"):
        return "portfolio"
    if s in ("position", "ticker", "security", "holding"):
        return "position"
    return "position"


def _coerce_string_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        text = v.strip()
        return [text] if text else []
    if isinstance(v, list):
        return [str(item).strip() for item in v if str(item).strip()]
    return [str(v).strip()] if str(v).strip() else []


def _empty_if_none(v):
    if v is None:
        return ""
    return v


# ── Data Agent output ────────────────────────────────────────────────────────


class PositionSnapshot(BaseModel):
    model_config = _IGNORE_EXTRA

    ticker: str
    current_price: float = 0.0
    prev_close: float = 0.0
    change_1d_pct: float = 0.0
    change_1w_pct: float = 0.0
    change_1m_pct: float = 0.0
    change_1y_pct: float = 0.0
    change_3m_pct: float = 0.0
    week_52_high: float = 0.0
    week_52_low: float = 0.0
    pct_from_52w_high: float = 0.0
    recent_headlines: list[str] = Field(default_factory=list)


class MarketIndicator(BaseModel):
    model_config = _IGNORE_EXTRA

    ticker: str
    label: str
    current: float = 0.0
    change_1d_pct: float = 0.0
    change_1m_pct: float = 0.0


class MarketData(BaseModel):
    model_config = _IGNORE_EXTRA

    positions: list[PositionSnapshot] = Field(default_factory=list)
    indicators: list[MarketIndicator] = Field(default_factory=list)
    fetched_at: str = ""
    errors: list[str] = Field(default_factory=list)


# ── Planner → News: search priorities ───────────────────────────────────────────


class PositionGoalFocus(BaseModel):
    model_config = _IGNORE_EXTRA

    ticker: str
    goal: str = ""  # entry thesis / position-level goal
    latest_news_query: str = Field(
        default="",
        description=(
            "Single web search for this symbol — use the planner form: "
            "'latest news for {TICKER}' (filled by planner output)"
        ),
    )


class NewsFocus(BaseModel):
    """Portfolio goal + per-position goals for targeted news context."""

    model_config = _IGNORE_EXTRA

    portfolio_goal: str = ""
    portfolio_search_queries: list[str] = Field(
        default_factory=list,
        description="Three macro / portfolio-wide web search strings (from planner LLM)",
    )
    position_goals: list[PositionGoalFocus] = Field(default_factory=list)
    macro_indicator_tickers: list[str] = Field(
        default_factory=list,
        description=(
            "Yahoo symbols for macro dashboard fetches (subset of GLD, USO, ^TNX, EEM, EFA, SPY, "
            "QQQ, XLF, ^VIX). Empty means fetch all configured indicators."
        ),
    )


class PositionSearchPlan(BaseModel):
    """Per-ticker search plan produced by the planner LLM."""

    model_config = _IGNORE_EXTRA

    ticker: str = Field(description="Same symbol as in the portfolio")
    latest_news_query: str = Field(
        default="",
        description=(
            "REQUIRED: one web search string for fresh headlines on this holding. "
            "Use exactly: 'latest news for {TICKER}' with the portfolio symbol (e.g. "
            "'latest news for NVDA')."
        ),
    )


class NewsPlannerResult(BaseModel):
    """Structured planner output; merged into NewsFocus before data + news run in parallel."""

    model_config = _IGNORE_EXTRA

    portfolio_search_queries: list[str] = Field(
        default_factory=list,
        description=(
            "Exactly three web search strings: top macro / cross-cutting topics inferred from the "
            "portfolio CONTEXT note and overall thesis mix "
            "(Fed, rates, USD, credit, growth, risk). "
            "No single-name stock angles — those are only in per-ticker latest_news_query."
        ),
    )
    position_plans: list[PositionSearchPlan] = Field(
        default_factory=list,
        description=(
            "One entry per portfolio line: latest_news_query only (see PositionSearchPlan)."
        ),
    )
    macro_indicator_tickers: list[str] = Field(
        default_factory=list,
        description=(
            "Which macro benchmarks to pull live prices for (must be from: GLD, USO, ^TNX, EEM, "
            "EFA, SPY, QQQ, XLF, ^VIX). Pick 3-9 most relevant to the portfolio CONTEXT; [] means "
            "all."
        ),
    )
    brief_rationale: str = Field(
        default="",
        description="One sentence: why these searches matter for this review",
    )


# ── News Agent output ─────────────────────────────────────────────────────────


class NewsReview(BaseModel):
    """Lightweight market context passed to all downstream agents."""

    model_config = _IGNORE_EXTRA

    macro_context: str = Field(
        description="2-3 sentences: rates, USD, credit spreads, equity vol, central bank posture"
    )
    market_themes: list[str] = Field(
        default_factory=list,
        description="3-5 dominant themes driving flows, short labels",
    )
    key_events: list[str] = Field(
        default_factory=list,
        description="Up to 6 notable recent events relevant to the portfolio tickers/sectors",
    )
    thesis_risks: list[str] = Field(
        default_factory=list,
        description="Tickers where recent events challenge the original entry thesis",
    )
    summary: str = ""


class DownstreamContextPlan(BaseModel):
    """Planner phase 2: curated narrative slices for parallel analysis agents."""

    model_config = _IGNORE_EXTRA

    brief_rationale: str = Field(
        default="",
        description="One sentence: what was emphasised for risk / regime / theme agents",
    )
    risk_focus: str = Field(
        default="",
        description="Text for Risk agent: factors, concentration, scenarios, fragilities to weight",
    )
    regime_focus: str = Field(
        default="",
        description="Text for Regime agent: macro/policy/FX/growth cues and regime hooks",
    )
    theme_focus: str = Field(
        default="",
        description="Text for Theme agent: narratives, sector/theme links, crowding/momentum hooks",
    )


# ── Shared exposure vocabulary (Theme / Regime / Risk) ─────────────────────────


class ExposureLayer(BaseModel):
    """Cross-agent hook: same portfolio can be described in narrative vs macro vs factor space."""

    model_config = _IGNORE_EXTRA

    layer: Literal["theme", "regime", "factor"] = "factor"
    label: str = ""
    strength: float = Field(
        default=0.0,
        ge=-1.0,
        le=1.0,
        description="Signed strength in this layer (e.g. theme tilt, macro beta proxy).",
    )
    maps_to: list[str] = Field(
        default_factory=list,
        description="Other layers or tags this exposure links to (e.g. 'growth factor', 'semis').",
    )


# ── Risk Agent output ─────────────────────────────────────────────────────────


class ScenarioLoss(BaseModel):
    model_config = _IGNORE_EXTRA

    scenario: str
    estimated_portfolio_loss_pct: float = 0.0
    most_affected_positions: list[str] = Field(default_factory=list)
    scenario_kind: Literal["historical", "engine"] = "engine"


class WorstScenario(BaseModel):
    model_config = _IGNORE_EXTRA

    name: str = ""
    estimated_portfolio_loss_pct: float = 0.0


class RiskReview(BaseModel):
    """Factor + stress engine output from real market history."""

    model_config = _IGNORE_EXTRA

    factor_loadings: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Approximate factor betas / tilts (e.g. market_beta, growth, value, momentum, "
            "rates_sensitivity, oil, usd)."
        ),
    )
    factor_risk_contribution: dict[str, float] = Field(
        default_factory=dict,
        description="Rough share of portfolio variance explained by each factor proxy (sums ~1).",
    )
    marginal_risk_by_ticker: dict[str, float] = Field(
        default_factory=dict,
        description="Marginal risk weights by symbol (sum ~1).",
    )
    exposure_links: list[ExposureLayer] = Field(
        default_factory=list,
        description="Optional links between theme-like labels and factor proxies.",
    )
    concentration_issues: list[str] = Field(default_factory=list)
    concentration_top5_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Fraction of portfolio in top five names by weight.",
    )
    liquidity_notes: list[str] = Field(
        default_factory=list,
        description="ADV / size vs float proxies; crowding hints.",
    )
    scenario_losses: list[ScenarioLoss] = Field(default_factory=list)
    top_risks: list[str] = Field(
        default_factory=list,
        description="Ranked human-readable risk bullets (LLM + engine).",
    )
    worst_scenario: WorstScenario | None = None
    hidden_concentration: list[str] = Field(
        default_factory=list,
        description="Clusters that look diversified but move together (e.g. semis).",
    )
    fragilities: list[str] = Field(default_factory=list)
    risk_score: int = Field(default=5, ge=1, le=10)
    summary: str = ""


# ── Regime Agent output ───────────────────────────────────────────────────────


class RegimeStateVector(BaseModel):
    """Rule-based macro state from live indicators."""

    model_config = _IGNORE_EXTRA

    inflation_trend: Literal["up", "down", "stable"] = "stable"
    rates_trend: Literal["up", "down", "stable"] = "stable"
    growth_trend: Literal["accelerating", "slowing", "stable"] = "stable"
    liquidity: Literal["tight", "neutral", "loose"] = "neutral"
    volatility: Literal["high", "low"] = "low"


class HistoricalRegimeOutcome(BaseModel):
    """Historical analog summary from the regime runner."""

    model_config = _IGNORE_EXTRA

    runner_available: bool = False
    message: str = (
        "Historical analog periods and portfolio simulation are not executed in this build "
        "(runner disabled)."
    )
    analog_periods_identified: int = 0
    avg_return: float | None = None
    max_drawdown: float | None = None
    win_rate: float | None = None


class RegimeReview(BaseModel):
    model_config = _IGNORE_EXTRA

    current_regime: str = Field(
        description="Composite regime id, e.g. inflation_up_rates_up (aligned with state_vector)."
    )
    state_vector: RegimeStateVector = Field(default_factory=RegimeStateVector)
    regime_confidence: int = Field(default=5, ge=1, le=10)
    portfolio_fit_score: int = Field(default=5, ge=1, le=10)
    fit_notes: list[str] = Field(
        default_factory=list,
        description="Methodology / data-quality notes behind portfolio_fit_score.",
    )
    historical_outcome: HistoricalRegimeOutcome = Field(default_factory=HistoricalRegimeOutcome)
    mismatch_drivers: list[str] = Field(
        default_factory=list,
        description="Why the book is misaligned with the regime (duration, growth tilt, etc.).",
    )
    mismatches: list[str] = Field(
        default_factory=list,
        description="Legacy plain-language mismatch lines (kept for prompts/UI).",
    )
    regime_appropriate_tilts: list[str] = Field(default_factory=list)
    exposure_links: list[ExposureLayer] = Field(
        default_factory=list,
        description="Map regime stress (e.g. long duration) to factor/theme hooks.",
    )
    summary: str = ""


# ── Theme Agent output ────────────────────────────────────────────────────────


class ThemePositionProfile(BaseModel):
    """Step 1: portfolio → metadata + candidate themes (per position)."""

    model_config = _IGNORE_EXTRA

    ticker: str
    sector: str = ""
    business_model: str = ""
    revenue_drivers: str = ""
    candidate_themes: list[str] = Field(default_factory=list)


class ThemeMatchScore(BaseModel):
    """Step 3: scored theme ↔ book ↔ news."""

    model_config = _IGNORE_EXTRA

    theme: str
    portfolio_exposure: float = Field(default=0.0, ge=0.0, le=1.0)
    news_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    supporting_assets: list[str] = Field(default_factory=list)
    key_evidence: list[str] = Field(default_factory=list)
    narrative_kind: Literal["structural", "cyclical", "unknown"] = "unknown"

    @field_validator("supporting_assets", "key_evidence", mode="before")
    @classmethod
    def _coerce_string_list(cls, value):
        """Handle common LLM singleton-string emissions for list[str] fields."""
        if value is None:
            return []
        if isinstance(value, str):
            s = value.strip()
            return [s] if s else []
        if isinstance(value, list):
            out: list[str] = []
            for item in value:
                if item is None:
                    continue
                if isinstance(item, str):
                    s = item.strip()
                    if s:
                        out.append(s)
                    continue
                raise TypeError("ThemeMatchScore list fields must contain strings only")
            return out
        raise TypeError("ThemeMatchScore list fields must be a string or list of strings")


class ThemeGraphNode(BaseModel):
    model_config = _IGNORE_EXTRA

    node_id: str
    label: str = ""
    portfolio_exposure: float = 0.0
    news_strength: float = 0.0


def _theme_node_id(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return slug or "theme"


class ThemeGraphEdge(BaseModel):
    model_config = _IGNORE_EXTRA

    source: str
    target: str
    weight: float = 0.0
    relationship: str = ""


class ThemeGraph(BaseModel):
    """Optional collapse detection: themes that co-move or share one macro driver."""

    model_config = _IGNORE_EXTRA

    nodes: list[ThemeGraphNode] = Field(default_factory=list)
    edges: list[ThemeGraphEdge] = Field(default_factory=list)

    @field_validator("nodes", mode="before")
    @classmethod
    def _coerce_nodes(cls, value):
        # LLM sometimes emits ["theme a", "theme b"] instead of objects.
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError("theme_graph.nodes must be a list")

        used: set[str] = set()
        out: list[ThemeGraphNode | dict] = []

        def _unique(node_id: str) -> str:
            if node_id not in used:
                used.add(node_id)
                return node_id
            i = 2
            while f"{node_id}-{i}" in used:
                i += 1
            unique = f"{node_id}-{i}"
            used.add(unique)
            return unique

        for item in value:
            if isinstance(item, ThemeGraphNode):
                if not item.node_id.strip():
                    raise ValueError("theme graph node_id cannot be empty")
                item.node_id = _unique(item.node_id.strip())
                if not item.label:
                    item.label = item.node_id
                out.append(item)
                continue

            if isinstance(item, str):
                label = item.strip()
                if not label:
                    raise ValueError("theme graph string node cannot be empty")
                out.append({"node_id": _unique(_theme_node_id(label)), "label": label})
                continue

            if isinstance(item, dict):
                node = dict(item)
                raw_label = node.get("label") or node.get("theme") or ""
                label = str(raw_label).strip()
                raw_id = node.get("node_id") or ""
                node_id = str(raw_id).strip() or _theme_node_id(label)
                if not label and not node_id:
                    raise ValueError("theme graph node dict must include label or node_id")
                node["node_id"] = _unique(node_id)
                if label and not node.get("label"):
                    node["label"] = label
                out.append(node)
                continue

            raise TypeError(f"invalid theme graph node type: {type(item).__name__}")

        return out


class ThemePortfolioSynthesis(BaseModel):
    """Step 4: book-level narrative."""

    model_config = _IGNORE_EXTRA

    dominant_themes: list[str] = Field(default_factory=list)
    redundant_expressions: list[str] = Field(
        default_factory=list,
        description="Multiple line items expressing the same macro or factor bet.",
    )
    missing_exposures: list[str] = Field(
        default_factory=list,
        description="Hedges or themes implied by the thesis but absent from the book.",
    )
    theme_drift_note: str = Field(
        default="",
        description="Drift vs last review if unknown, say so.",
    )


class ThemeReview(BaseModel):
    """Theme = f(portfolio structure, news flow); LLM interprets seeds + research."""

    model_config = _IGNORE_EXTRA

    implicit_portfolio_bet: str = Field(
        default="",
        description="What the portfolio is implicitly betting on before checking the tape.",
    )
    position_profiles: list[ThemePositionProfile] = Field(default_factory=list)
    scored_themes: list[ThemeMatchScore] = Field(default_factory=list)
    theme_graph: ThemeGraph | None = None
    synthesis: ThemePortfolioSynthesis = Field(default_factory=ThemePortfolioSynthesis)
    crowding_risks: list[str] = Field(default_factory=list)
    momentum_conflicts: list[str] = Field(default_factory=list)
    exposure_links: list[ExposureLayer] = Field(
        default_factory=list,
        description="Map dominant themes to factor / regime hooks.",
    )
    alignment_score: int = Field(default=5, ge=1, le=10)
    summary: str = ""


# ── Validation Agent output ───────────────────────────────────────────────────


class CriticalIssue(BaseModel):
    model_config = _IGNORE_EXTRA

    issue: str = ""
    severity: Literal["critical", "high", "medium", "low"] = "medium"
    affected_positions: list[str] = Field(default_factory=list)
    source_agents: list[str] = Field(default_factory=list)

    @field_validator("severity", mode="before")
    @classmethod
    def _sev(cls, v):
        return _norm_severity(v)


class ValidationReview(BaseModel):
    model_config = _IGNORE_EXTRA

    critical_issues: list[CriticalIssue] = Field(default_factory=list)
    thesis_breaks: list[str] = Field(default_factory=list)
    internal_contradictions: list[str] = Field(default_factory=list)
    confidence_score: int = Field(default=5, ge=1, le=10)
    summary: str = ""


# ── Manager/PM Agent output ───────────────────────────────────────────────────


class PortfolioStance(BaseModel):
    model_config = _IGNORE_EXTRA

    stance: Literal["defensive", "balanced", "opportunistic", "wait"] = "balanced"
    urgency: Literal["urgent", "this-week", "next-review", "watch"] = "watch"
    primary_risk: str = ""
    recommended_posture: str = ""
    rationale: str = ""

    @field_validator("stance", mode="before")
    @classmethod
    def _stance(cls, v):
        return _norm_portfolio_stance(v)

    @field_validator("urgency", mode="before")
    @classmethod
    def _urgency(cls, v):
        return _norm_priority(v)

    @field_validator("primary_risk", "recommended_posture", "rationale", mode="before")
    @classmethod
    def _metadata_string(cls, v):
        return _empty_if_none(v)


class Action(BaseModel):
    model_config = _IGNORE_EXTRA

    action_type: Literal["reduce", "exit", "hedge", "rotate", "add", "monitor", "no-action"] = (
        "monitor"
    )
    position: str
    rationale: str = ""
    priority: Literal["urgent", "this-week", "next-review", "watch"] = "watch"
    size_guidance: str = ""
    hedge_instrument: str = ""
    scope: Literal["portfolio", "position"] = "position"
    risk_addressed: str = ""
    supporting_evidence: list[str] = Field(default_factory=list)
    revisit_trigger: str = ""

    @model_validator(mode="before")
    @classmethod
    def _infer_scope(cls, data):
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if not out.get("scope"):
            position = str(out.get("position") or "").strip().lower()
            out["scope"] = "portfolio" if position == "portfolio-level" else "position"
        return out

    @field_validator("action_type", mode="before")
    @classmethod
    def _act(cls, v):
        return _norm_action_type(v)

    @field_validator("priority", mode="before")
    @classmethod
    def _pri(cls, v):
        return _norm_priority(v)

    @field_validator("hedge_instrument", mode="before")
    @classmethod
    def _hedge_instrument(cls, v):
        # LLMs often emit null for "N/A"; explicit null does not use the field default.
        if v is None:
            return ""
        return v

    @field_validator("risk_addressed", "revisit_trigger", mode="before")
    @classmethod
    def _new_metadata_string(cls, v):
        return _empty_if_none(v)

    @field_validator("scope", mode="before")
    @classmethod
    def _scope(cls, v):
        return _norm_action_scope(v)

    @field_validator("supporting_evidence", mode="before")
    @classmethod
    def _supporting_evidence(cls, v):
        return _coerce_string_list(v)


class ManagerReview(BaseModel):
    model_config = _IGNORE_EXTRA

    portfolio_stance: PortfolioStance = Field(default_factory=PortfolioStance)
    actions: list[Action] = Field(default_factory=list)
    do_nothing_case: str = ""
    overall_confidence: int = Field(default=5, ge=1, le=10)
    executive_summary: str = ""

    @field_validator("portfolio_stance", mode="before")
    @classmethod
    def _portfolio_stance(cls, v):
        if v is None:
            return {}
        return v
