from __future__ import annotations

import operator
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from port.portfolio import Portfolio


# ── News Agent output ─────────────────────────────────────────────────────────

class PositionEvent(BaseModel):
    ticker: str
    event: str
    impact_direction: Literal["positive", "negative", "neutral", "uncertain"]
    urgency: Literal["immediate", "this-week", "monitor", "low"]
    detail: str


class NewsReview(BaseModel):
    macro_context: str = Field(
        description="Broad macro environment: rates, curves, USD, credit spreads, equity vol, central bank posture"
    )
    market_themes: list[str] = Field(
        description="Dominant market narratives currently driving flows (3-6 themes)"
    )
    material_events: list[PositionEvent] = Field(
        description="Per-holding events scoped to positions in the portfolio"
    )
    thesis_breaking_events: list[str] = Field(
        description="Events that directly contradict an entry thesis for a held position"
    )
    catalysts_ahead: list[str] = Field(
        description="Upcoming events in the next 60 days relevant to the portfolio"
    )
    summary: str


# ── Risk Agent output ─────────────────────────────────────────────────────────

class FactorExposure(BaseModel):
    factor: str
    direction: Literal["long", "short", "neutral"]
    magnitude: Literal["high", "medium", "low"]
    positions_driving: list[str]


class ScenarioLoss(BaseModel):
    scenario: str
    estimated_portfolio_loss_pct: float
    most_affected_positions: list[str]


class RiskReview(BaseModel):
    factor_exposures: list[FactorExposure]
    concentration_issues: list[str]
    scenario_losses: list[ScenarioLoss]
    fragilities: list[str]
    risk_score: int = Field(ge=1, le=10, description="1=low risk, 10=extreme risk")
    summary: str


# ── Regime Agent output ───────────────────────────────────────────────────────

class RegimeReview(BaseModel):
    current_regime: str
    regime_confidence: int = Field(ge=1, le=10)
    portfolio_fit_score: int = Field(ge=1, le=10, description="10=perfect fit")
    mismatches: list[str]
    regime_appropriate_tilts: list[str]
    summary: str


# ── Theme Agent output ────────────────────────────────────────────────────────

class ThemeAlignment(BaseModel):
    theme: str
    portfolio_stance: Literal["aligned", "fighting", "neutral", "overweight", "underweight"]
    relevant_positions: list[str]


class ThemeReview(BaseModel):
    dominant_market_themes: list[str]
    theme_alignments: list[ThemeAlignment]
    crowding_risks: list[str]
    momentum_conflicts: list[str]
    alignment_score: int = Field(ge=1, le=10, description="10=fully aligned")
    summary: str


# ── Validation Agent output ───────────────────────────────────────────────────

class CriticalIssue(BaseModel):
    issue: str
    severity: Literal["critical", "high", "medium", "low"]
    affected_positions: list[str]
    source_agents: list[str]


class ValidationReview(BaseModel):
    critical_issues: list[CriticalIssue]
    thesis_breaks: list[str]
    internal_contradictions: list[str]
    confidence_score: int = Field(ge=1, le=10, description="10=highly consistent portfolio")
    summary: str


# ── Planner/PM Agent output ───────────────────────────────────────────────────

class Action(BaseModel):
    action_type: Literal["reduce", "exit", "hedge", "rotate", "add", "monitor", "no-action"]
    position: str
    rationale: str
    priority: Literal["urgent", "this-week", "next-review", "watch"]
    size_guidance: str
    hedge_instrument: str = ""


class PlannerReview(BaseModel):
    actions: list[Action]
    do_nothing_case: str
    overall_confidence: int = Field(ge=1, le=10)
    executive_summary: str


# ── Graph State ───────────────────────────────────────────────────────────────

class GraphState(TypedDict):
    portfolio: Portfolio

    # Sequential: plan_node writes confirmed portfolio, news_node writes this
    news_review: Optional[NewsReview]

    # Parallel fan-out — operator.add lets each branch append without clobbering
    risk_results: Annotated[list[RiskReview], operator.add]
    regime_results: Annotated[list[RegimeReview], operator.add]
    theme_results: Annotated[list[ThemeReview], operator.add]

    # Sequential: validation → planner
    validation_review: Optional[ValidationReview]
    planner_review: Optional[PlannerReview]
