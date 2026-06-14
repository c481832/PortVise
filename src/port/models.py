from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_IGNORE_EXTRA = ConfigDict(extra="ignore")




def _norm_impact(v) -> str:
    table = {
        "positive": "positive",
        "negative": "negative",
        "neutral": "neutral",
        "uncertain": "uncertain",
        "pos": "positive",
        "neg": "negative",
    }
    key = str(v).lower()
    if key not in table:
        raise ValueError(f"unrecognized impact value: {v!r}")
    return table[key]


def _norm_urgency(v) -> str:
    s = str(v).lower()
    if s in ("immediate", "critical", "high", "urgent"):
        return "immediate"
    if s in ("this-week", "this_week", "thisweek", "medium", "moderate"):
        return "this-week"
    if s in ("low", "watch", "low-priority"):
        return "low"
    if s == "monitor":
        return "monitor"
    raise ValueError(f"unrecognized urgency value: {v!r}")


def _norm_direction(v) -> str:
    table = {
        "long": "long",
        "short": "short",
        "neutral": "neutral",
        "overweight": "long",
        "underweight": "short",
    }
    key = str(v).lower()
    if key not in table:
        raise ValueError(f"unrecognized direction value: {v!r}")
    return table[key]


def _norm_magnitude(v) -> str:
    table = {
        "high": "high",
        "medium": "medium",
        "low": "low",
        "large": "high",
        "small": "low",
        "moderate": "medium",
    }
    key = str(v).lower()
    if key not in table:
        raise ValueError(f"unrecognized magnitude value: {v!r}")
    return table[key]


def _norm_severity(v) -> str:
    table = {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "low": "low",
        "severe": "critical",
        "major": "high",
        "minor": "low",
    }
    key = str(v).lower()
    if key not in table:
        raise ValueError(f"unrecognized severity value: {v!r}")
    return table[key]


def _norm_stance(v) -> str:
    table = {
        "aligned": "aligned",
        "fighting": "fighting",
        "neutral": "neutral",
        "overweight": "overweight",
        "underweight": "underweight",
        "long": "aligned",
        "short": "fighting",
    }
    key = str(v).lower()
    if key not in table:
        raise ValueError(f"unrecognized stance value: {v!r}")
    return table[key]


def _norm_action_type(v) -> str:
    table = {
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
    }
    key = str(v).lower()
    if key not in table:
        raise ValueError(f"unrecognized action_type value: {v!r}")
    return table[key]


def _norm_priority(v) -> str:
    s = str(v).lower()
    if s in ("urgent", "immediate", "critical", "high"):
        return "urgent"
    if s in ("this-week", "this_week", "thisweek", "medium", "short-term"):
        return "this-week"
    if s in ("next-review", "next_review", "low", "medium-term"):
        return "next-review"
    if s == "watch":
        return "watch"
    raise ValueError(f"unrecognized priority value: {v!r}")


def _norm_action_scope(v) -> str:
    s = str(v).lower()
    if s in ("portfolio", "portfolio-level", "portfolio_level", "book"):
        return "portfolio"
    if s in ("position", "ticker", "security", "holding"):
        return "position"
    raise ValueError(f"unrecognized action_scope value: {v!r}")


def _coerce_string_list(v) -> list[str]:
    if v is None:
        raise ValueError("expected a list of strings; got None")
    if isinstance(v, str):
        text = v.strip()
        if not text:
            raise ValueError("expected a list of strings; got an empty string")
        return [text]
    if isinstance(v, list):
        return [str(item).strip() for item in v if str(item).strip()]
    raise TypeError(f"expected a list of strings; got {type(v).__name__}")




class PositionSnapshot(BaseModel):
    model_config = _IGNORE_EXTRA

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
    model_config = _IGNORE_EXTRA

    ticker: str
    name: str = ""
    sector: str = ""
    industry: str = ""


class MarketIndicator(BaseModel):
    model_config = _IGNORE_EXTRA

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
    model_config = _IGNORE_EXTRA

    positions: list[PositionSnapshot] = Field(default_factory=list)
    indicators: list[MarketIndicator]
    fetched_at: str
    errors: list[str] = Field(default_factory=list)




class PositionGoalFocus(BaseModel):
    model_config = _IGNORE_EXTRA

    ticker: str
    goal: str
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


class PositionSearchPlan(BaseModel):
    """Per-ticker search plan produced by the planner LLM."""

    model_config = _IGNORE_EXTRA

    ticker: str = Field(description="Same symbol as in the portfolio")
    latest_news_query: str = Field(
        description=(
            "REQUIRED: one web search string for fresh headlines on this holding. "
            "Use exactly: 'latest news for {TICKER}' with the portfolio symbol (e.g. "
            "'latest news for NVDA')."
        ),
    )


class NewsPlannerResult(BaseModel):
    """Structured planner output; merged into NewsFocus before news research runs."""

    model_config = _IGNORE_EXTRA

    portfolio_search_queries: list[str] = Field(
        description=(
            "Exactly three web search strings: top macro / cross-cutting topics inferred from the "
            "portfolio CONTEXT note and overall thesis mix "
            "(Fed, rates, USD, credit, growth, risk). "
            "No single-name stock angles — those are only in per-ticker latest_news_query."
        ),
    )
    position_plans: list[PositionSearchPlan] = Field(
        description=(
            "One entry per portfolio line: latest_news_query only (see PositionSearchPlan)."
        ),
    )




class NewsReview(BaseModel):
    """Lightweight market context passed to all downstream agents."""

    model_config = _IGNORE_EXTRA

    macro_context: str = Field(
        description="2-3 sentences: rates, USD, credit spreads, equity vol, central bank posture"
    )
    market_themes: list[str] = Field(
        description="3-5 dominant themes driving flows, short labels",
    )
    key_events: list[str] = Field(
        description="Up to 6 notable recent events relevant to the portfolio tickers/sectors",
    )
    thesis_risks: list[str] = Field(
        description="Tickers where recent events challenge the original entry thesis",
    )
    summary: str




class ExposureLayer(BaseModel):
    """Cross-agent hook: same portfolio can be described in narrative vs macro vs factor space."""

    model_config = _IGNORE_EXTRA

    layer: Literal["theme", "regime", "factor"]
    label: str
    strength: float = Field(
        ge=-1.0,
        le=1.0,
        description="Signed strength in this layer (e.g. theme tilt, macro beta proxy).",
    )
    maps_to: list[str] = Field(
        description="Other layers or tags this exposure links to (e.g. 'growth factor', 'semis').",
    )

    @field_validator("strength", mode="before")
    @classmethod
    def _normalize_strength(cls, value):
        if value is None or isinstance(value, bool):
            raise ValueError(f"strength must be a real number in [-1, 1]; got {value!r}")
        try:
            x = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"strength must be a real number; got {value!r}") from exc
        if x != x:
            raise ValueError("strength is NaN")
        if not (-1.0 <= x <= 1.0):
            raise ValueError(f"strength must be in [-1, 1]; got {x}")
        return x




class ScenarioLoss(BaseModel):
    model_config = _IGNORE_EXTRA

    scenario: str
    estimated_portfolio_loss_pct: float
    most_affected_positions: list[str]
    scenario_kind: Literal["historical", "engine"]


class WorstScenario(BaseModel):
    model_config = _IGNORE_EXTRA

    name: str
    estimated_portfolio_loss_pct: float


class RiskReview(BaseModel):
    """Factor + stress engine output from real market history."""

    model_config = _IGNORE_EXTRA

    factor_loadings: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Engine-filled. Approximate factor betas / tilts (e.g. market_beta, growth, value, "
            "momentum, rates_sensitivity, oil, usd). Do not emit; the engine value is authoritative."
        ),
    )
    factor_risk_contribution: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Engine-filled. Cash-aware rough share of portfolio variance explained by each factor "
            "proxy, scaled by included portfolio weight. Do not emit."
        ),
    )
    marginal_risk_by_ticker: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Engine-filled. Cash-aware marginal risk by symbol, scaled by included portfolio weight "
            "rather than renormalized to a fully invested book. Do not emit."
        ),
    )
    exposure_links: list[ExposureLayer] = Field(
        default_factory=list,
        description="Optional links between theme-like labels and factor proxies.",
    )
    concentration_issues: list[str] = Field(
        default_factory=list,
        description=(
            "LLM additions to the engine's concentration findings; merged with the "
            "engine base in code, so an empty list is valid."
        ),
    )
    concentration_top5_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Engine-filled. Fraction of portfolio in top five names by weight. Do not emit.",
    )
    liquidity_notes: list[str] = Field(
        default_factory=list,
        description="ADV / size vs float proxies; crowding hints.",
    )
    scenario_losses: list[ScenarioLoss] = Field(
        default_factory=list,
        description="Engine-filled stress P&L by scenario. Do not emit.",
    )
    top_risks: list[str] = Field(
        default_factory=list,
        description="Ranked human-readable risk bullets (LLM + engine).",
    )
    worst_scenario: WorstScenario | None = Field(
        default=None,
        description="Engine-filled worst historical scenario. Do not emit.",
    )
    hidden_concentration: list[str] = Field(
        default_factory=list,
        description="Engine-filled. Clusters that look diversified but move together (e.g. semis). Do not emit.",
    )
    summary: str = ""




class RegimeStateVector(BaseModel):
    """Rule-based macro state from live indicators."""

    model_config = _IGNORE_EXTRA

    inflation_trend: Literal["up", "down", "stable"]
    rates_trend: Literal["up", "down", "stable"]
    growth_trend: Literal["accelerating", "slowing", "stable"]
    liquidity: Literal["tight", "neutral", "loose"]
    volatility: Literal["high", "low"]


class HistoricalRegimePeriod(BaseModel):
    """Portfolio result from one historical regime analog."""

    model_config = _IGNORE_EXTRA

    period: str
    forward_window: str
    forward_horizon_days: int
    distance: float
    match_score: float
    portfolio_return: float
    max_drawdown: float


class HistoricalRegimeOutcome(BaseModel):
    """Historical analog summary from the regime runner."""

    model_config = _IGNORE_EXTRA

    runner_available: bool
    message: str
    analog_periods_identified: int
    avg_return: float | None
    max_drawdown: float | None
    win_rate: float | None
    top_similar_periods: list[HistoricalRegimePeriod]


class RegimeReview(BaseModel):
    model_config = _IGNORE_EXTRA

    current_regime: str = Field(
        description="Human-readable composite regime label aligned with state_vector."
    )
    state_vector: RegimeStateVector
    historical_outcome: HistoricalRegimeOutcome
    mismatch_drivers: list[str] = Field(
        description="Why the book is misaligned with the regime (duration, growth tilt, etc.).",
    )
    regime_appropriate_tilts: list[str]
    exposure_links: list[ExposureLayer] = Field(
        description="Map regime stress (e.g. long duration) to factor/theme hooks.",
    )
    summary: str




class ThemePositionProfile(BaseModel):
    """Step 1: portfolio → metadata + candidate themes (per position)."""

    model_config = _IGNORE_EXTRA

    ticker: str
    sector: str
    business_model: str
    revenue_drivers: str
    candidate_themes: list[str]


class ThemeAssessment(BaseModel):
    """Step 3: qualitative theme ↔ book ↔ news assessment."""

    model_config = _IGNORE_EXTRA

    theme: str
    supporting_assets: list[str]
    key_evidence: list[str]
    assessment: str
    implication: str
    narrative_kind: Literal["structural", "cyclical", "unknown"]

    @field_validator("supporting_assets", "key_evidence", mode="before")
    @classmethod
    def _coerce_string_list(cls, value):
        """Handle common LLM singleton-string emissions for list[str] fields."""
        if value is None:
            raise ValueError("supporting_assets / key_evidence cannot be None")
        if isinstance(value, str):
            s = value.strip()
            if not s:
                raise ValueError("supporting_assets / key_evidence cannot be an empty string")
            return [s]
        if isinstance(value, list):
            out: list[str] = []
            for item in value:
                if item is None:
                    raise ValueError("list field contains None")
                if not isinstance(item, str):
                    raise TypeError("ThemeAssessment list fields must contain strings only")
                s = item.strip()
                if s:
                    out.append(s)
            return out
        raise TypeError("ThemeAssessment list fields must be a string or list of strings")


class ThemePortfolioSynthesis(BaseModel):
    """Step 4: book-level narrative."""

    model_config = _IGNORE_EXTRA

    dominant_themes: list[str]
    redundant_expressions: list[str] = Field(
        description="Multiple line items expressing the same macro or factor bet.",
    )
    missing_exposures: list[str] = Field(
        description="Hedges or themes implied by the thesis but absent from the book.",
    )
    theme_drift_note: str = Field(
        description="Drift vs last review if unknown, say so.",
    )


class ThemeReview(BaseModel):
    """Theme = f(portfolio structure, news flow); LLM interprets seeds + research."""

    model_config = _IGNORE_EXTRA

    implicit_portfolio_bet: str = Field(
        description="What the portfolio is implicitly betting on before checking the tape.",
    )
    position_profiles: list[ThemePositionProfile]
    theme_assessments: list[ThemeAssessment]
    synthesis: ThemePortfolioSynthesis
    crowding_risks: list[str]
    momentum_conflicts: list[str]
    exposure_links: list[ExposureLayer] = Field(
        description="Map dominant themes to factor / regime hooks.",
    )
    summary: str




class CriticalIssue(BaseModel):
    model_config = _IGNORE_EXTRA

    issue: str
    severity: Literal["critical", "high", "medium", "low"]
    affected_positions: list[str]
    source_agents: list[str]

    @field_validator("severity", mode="before")
    @classmethod
    def _sev(cls, v):
        return _norm_severity(v)


class ValidationReview(BaseModel):
    model_config = _IGNORE_EXTRA

    critical_issues: list[CriticalIssue]
    thesis_breaks: list[str]
    internal_contradictions: list[str]
    summary: str




class PortfolioVerdict(BaseModel):
    model_config = _IGNORE_EXTRA

    action_timing: Literal["urgent", "this-week", "next-review", "watch"]
    investment_horizon: Literal["tactical", "medium-term", "strategic"]
    horizon_detail: str
    primary_risk: str
    recommended_posture: str
    revisit_trigger: str
    rationale: str

    @field_validator("action_timing", mode="before")
    @classmethod
    def _action_timing(cls, v):
        return _norm_priority(v)


class Action(BaseModel):
    model_config = _IGNORE_EXTRA

    action_type: Literal["reduce", "exit", "hedge", "rotate", "add", "monitor", "no-action"]
    position: str
    rationale: str
    priority: Literal["urgent", "this-week", "next-review", "watch"]
    size_guidance: str
    hedge_instrument: str
    scope: Literal["portfolio", "position"]
    risk_addressed: str
    supporting_evidence: list[str]
    revisit_trigger: str

    @model_validator(mode="before")
    @classmethod
    def _require_scope(cls, data):
        if not isinstance(data, dict):
            return data
        if not data.get("scope"):
            raise ValueError("Action.scope is required and must be 'portfolio' or 'position'")
        return data

    @field_validator("action_type", mode="before")
    @classmethod
    def _act(cls, v):
        return _norm_action_type(v)

    @field_validator("priority", mode="before")
    @classmethod
    def _pri(cls, v):
        return _norm_priority(v)

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

    portfolio_verdict: PortfolioVerdict
    actions: list[Action]
    do_nothing_case: str
    executive_summary: str


class AgentTaskSummary(BaseModel):
    model_config = _IGNORE_EXTRA

    title: str
    summary: str
    bullets: list[str]

    @field_validator("bullets", mode="before")
    @classmethod
    def _bullets(cls, v):
        return _coerce_string_list(v)


class PastCallOutcome(BaseModel):
    """How one prior reduce/exit/add recommendation has performed since the review.

    ``daily_outperf_pct`` is the average per-trading-day return of the named position minus
    the benchmark over the window since the review (length-unbiased). It is ``None`` while the
    call is ``pending`` (too few trading days elapsed) or when price history is unavailable.
    """

    model_config = _IGNORE_EXTRA

    position: str
    action_type: Literal["reduce", "exit", "add"]
    days_elapsed: int
    daily_outperf_pct: float | None
    verdict: Literal["validated", "invalidated", "pending"]
    note: str = ""


class PastPerformanceReview(BaseModel):
    """Deterministic scorecard for a single past review's reduce/exit/add calls."""

    model_config = _IGNORE_EXTRA

    review_id: str
    review_date: str
    benchmark: str
    min_comparison_days: int
    matured_count: int
    validated_count: int
    outcomes: list[PastCallOutcome]
