"""Risk engine outputs: scenario losses and the risk review."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ScenarioLoss(BaseModel):
    model_config = ConfigDict(extra="ignore")

    scenario: str
    estimated_portfolio_loss_pct: float


class WorstScenario(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    estimated_portfolio_loss_pct: float


class RiskReview(BaseModel):
    """Factor + stress engine output from real market history."""

    model_config = ConfigDict(extra="ignore")

    factor_loadings: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Engine-filled. Betas from one joint regression of daily portfolio returns on the "
            "market, tilts measured against the market (e.g. growth_vs_market), and macro "
            "factors (long_bonds, gold, oil, usd). Cash-aware: computed on actual weights. "
            "Do not emit; the engine value is authoritative."
        ),
    )
    factor_risk_contribution: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Engine-filled. Signed share of portfolio return variance from each factor (Euler "
            "split of the joint regression) plus 'idiosyncratic'; values sum to 1. Negative "
            "means the factor offsets other risk. Do not emit."
        ),
    )
    risk_contribution_by_ticker: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Engine-filled. Signed share of portfolio variance by holding (Euler split); sums "
            "to 1. Negative means the holding hedges the rest of the book. Do not emit."
        ),
    )
    volatility_contribution_by_ticker: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Engine-filled. Each holding's contribution to annualized portfolio volatility, as a "
            "fraction; sums to portfolio_volatility. Do not emit."
        ),
    )
    portfolio_volatility: float | None = Field(
        default=None,
        description=(
            "Engine-filled. Annualized volatility of the covered holdings at actual weights, "
            "so cash lowers it. Do not emit."
        ),
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
