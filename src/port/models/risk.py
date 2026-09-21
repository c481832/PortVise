"""Risk engine outputs: scenario losses and the risk review."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from port.models.exposure import ExposureLayer
from port.models.normalizers import IGNORE_EXTRA


class ScenarioLoss(BaseModel):
    model_config = IGNORE_EXTRA

    scenario: str
    estimated_portfolio_loss_pct: float
    most_affected_positions: list[str]
    scenario_kind: Literal["historical", "engine"]


class WorstScenario(BaseModel):
    model_config = IGNORE_EXTRA

    name: str
    estimated_portfolio_loss_pct: float


class RiskReview(BaseModel):
    """Factor + stress engine output from real market history."""

    model_config = IGNORE_EXTRA

    factor_loadings: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Engine-filled. Approximate factor betas / tilts (e.g. market_beta, growth, value, "
            "momentum, rates_sensitivity, oil, usd). Do not emit; the engine value is "
            "authoritative."
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
            "Engine-filled. Cash-aware marginal risk by symbol, scaled by included portfolio "
            "weight "
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
        description=(
            "Engine-filled. Fraction of portfolio in top five names by weight. Do not emit."
        ),
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
        description=(
            "Engine-filled. Clusters that look diversified but move together (e.g. semis). "
            "Do not emit."
        ),
    )
    summary: str = ""
