from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_IGNORE_EXTRA = ConfigDict(extra="ignore")


# ── Enum normalizers ──────────────────────────────────────────────────────────

def _norm_impact(v: str) -> str:
    return {
        "positive": "positive", "negative": "negative",
        "neutral": "neutral", "uncertain": "uncertain",
        "pos": "positive", "neg": "negative",
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
        "long": "long", "short": "short", "neutral": "neutral",
        "overweight": "long", "underweight": "short",
    }.get(str(v).lower(), "neutral")


def _norm_magnitude(v: str) -> str:
    return {
        "high": "high", "medium": "medium", "low": "low",
        "large": "high", "small": "low", "moderate": "medium",
    }.get(str(v).lower(), "medium")


def _norm_severity(v: str) -> str:
    return {
        "critical": "critical", "high": "high", "medium": "medium", "low": "low",
        "severe": "critical", "major": "high", "minor": "low",
    }.get(str(v).lower(), "medium")


def _norm_stance(v: str) -> str:
    return {
        "aligned": "aligned", "fighting": "fighting", "neutral": "neutral",
        "overweight": "overweight", "underweight": "underweight",
        "long": "aligned", "short": "fighting",
    }.get(str(v).lower(), "neutral")


def _norm_action_type(v: str) -> str:
    return {
        "reduce": "reduce", "exit": "exit", "hedge": "hedge",
        "rotate": "rotate", "add": "add", "monitor": "monitor", "no-action": "no-action",
        "sell": "exit", "trim": "reduce", "buy": "add",
        "no_action": "no-action", "hold": "monitor",
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


# ── Data Agent output ────────────────────────────────────────────────────────

class PositionSnapshot(BaseModel):
    model_config = _IGNORE_EXTRA

    ticker: str
    current_price: float = 0.0
    prev_close: float = 0.0
    change_1d_pct: float = 0.0
    change_1w_pct: float = 0.0
    change_1m_pct: float = 0.0
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


# ── Risk Agent output ─────────────────────────────────────────────────────────

class FactorExposure(BaseModel):
    model_config = _IGNORE_EXTRA

    factor: str
    direction: Literal["long", "short", "neutral"] = "neutral"
    magnitude: Literal["high", "medium", "low"] = "medium"
    positions_driving: list[str] = Field(default_factory=list)

    @field_validator("direction", mode="before")
    @classmethod
    def _dir(cls, v): return _norm_direction(v)

    @field_validator("magnitude", mode="before")
    @classmethod
    def _mag(cls, v): return _norm_magnitude(v)


class ScenarioLoss(BaseModel):
    model_config = _IGNORE_EXTRA

    scenario: str
    estimated_portfolio_loss_pct: float = 0.0
    most_affected_positions: list[str] = Field(default_factory=list)


class RiskReview(BaseModel):
    model_config = _IGNORE_EXTRA

    factor_exposures: list[FactorExposure] = Field(default_factory=list)
    concentration_issues: list[str] = Field(default_factory=list)
    scenario_losses: list[ScenarioLoss] = Field(default_factory=list)
    fragilities: list[str] = Field(default_factory=list)
    risk_score: int = Field(default=5, ge=1, le=10)
    summary: str = ""


# ── Regime Agent output ───────────────────────────────────────────────────────

class RegimeReview(BaseModel):
    model_config = _IGNORE_EXTRA

    current_regime: str
    regime_confidence: int = Field(default=5, ge=1, le=10)
    portfolio_fit_score: int = Field(default=5, ge=1, le=10)
    mismatches: list[str] = Field(default_factory=list)
    regime_appropriate_tilts: list[str] = Field(default_factory=list)
    summary: str = ""


# ── Theme Agent output ────────────────────────────────────────────────────────

class ThemeAlignment(BaseModel):
    model_config = _IGNORE_EXTRA

    theme: str
    portfolio_stance: Literal["aligned", "fighting", "neutral", "overweight", "underweight"] = "neutral"
    relevant_positions: list[str] = Field(default_factory=list)

    @field_validator("portfolio_stance", mode="before")
    @classmethod
    def _stance(cls, v): return _norm_stance(v)


class ThemeReview(BaseModel):
    model_config = _IGNORE_EXTRA

    dominant_market_themes: list[str] = Field(default_factory=list)
    theme_alignments: list[ThemeAlignment] = Field(default_factory=list)
    crowding_risks: list[str] = Field(default_factory=list)
    momentum_conflicts: list[str] = Field(default_factory=list)
    alignment_score: int = Field(default=5, ge=1, le=10)
    summary: str = ""


# ── Validation Agent output ───────────────────────────────────────────────────

class CriticalIssue(BaseModel):
    model_config = _IGNORE_EXTRA

    issue: str
    severity: Literal["critical", "high", "medium", "low"] = "medium"
    affected_positions: list[str] = Field(default_factory=list)
    source_agents: list[str] = Field(default_factory=list)

    @field_validator("severity", mode="before")
    @classmethod
    def _sev(cls, v): return _norm_severity(v)


class ValidationReview(BaseModel):
    model_config = _IGNORE_EXTRA

    critical_issues: list[CriticalIssue] = Field(default_factory=list)
    thesis_breaks: list[str] = Field(default_factory=list)
    internal_contradictions: list[str] = Field(default_factory=list)
    confidence_score: int = Field(default=5, ge=1, le=10)
    summary: str = ""


# ── Planner/PM Agent output ───────────────────────────────────────────────────

class Action(BaseModel):
    model_config = _IGNORE_EXTRA

    action_type: Literal["reduce", "exit", "hedge", "rotate", "add", "monitor", "no-action"] = "monitor"
    position: str
    rationale: str = ""
    priority: Literal["urgent", "this-week", "next-review", "watch"] = "watch"
    size_guidance: str = ""
    hedge_instrument: str = ""

    @field_validator("action_type", mode="before")
    @classmethod
    def _act(cls, v): return _norm_action_type(v)

    @field_validator("priority", mode="before")
    @classmethod
    def _pri(cls, v): return _norm_priority(v)


class PlannerReview(BaseModel):
    model_config = _IGNORE_EXTRA

    actions: list[Action] = Field(default_factory=list)
    do_nothing_case: str = ""
    overall_confidence: int = Field(default=5, ge=1, le=10)
    executive_summary: str = ""
