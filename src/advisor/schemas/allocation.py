"""Capital deployment candidates and the allocation review."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DeploymentCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ticker: str
    rationale: str


class AllocationReview(BaseModel):
    """Capital allocation engine output plus LLM deployment narrative."""

    model_config = ConfigDict(extra="ignore")

    cash_weight: float = Field(
        default=0.0,
        description="Engine-filled. Current cash weight of the portfolio. Do not emit.",
    )
    allocated_capital: float = Field(
        default=0.0,
        description="Engine-filled. 1 - cash_weight. Do not emit.",
    )
    min_allocated_capital: float = Field(
        default=0.0,
        description="Engine-filled. Configured minimum allocated capital. Do not emit.",
    )
    max_cash_weight: float = Field(
        default=0.0,
        description="Engine-filled. 1 - min_allocated_capital. Do not emit.",
    )
    required_deployment_pct: float = Field(
        default=0.0,
        description=(
            "Engine-filled. Cash weight above the configured maximum, as a fraction of the "
            "portfolio that must be deployed to bring cash back to the maximum. Do not emit."
        ),
    )
    cash_yield_annual_pct: float = Field(
        default=0.0,
        description="Engine-filled. Assumed annual cash yield in percent. Do not emit.",
    )
    benchmark_return_1y_pct: float | None = Field(
        default=None,
        description="Engine-filled. One-year benchmark return in percent, if known. Do not emit.",
    )
    cash_opportunity_cost_pct: float | None = Field(
        default=None,
        description=(
            "Engine-filled. Historical one-year cost of the current cash weight vs the "
            "benchmark, in percent of portfolio. Do not emit."
        ),
    )
    drawdown_budget_pct: float = Field(
        default=0.0,
        description="Engine-filled. Configured maximum drawdown budget in percent. Do not emit.",
    )
    worst_scenario_loss_pct: float | None = Field(
        default=None,
        description=(
            "Engine-filled. Worst deterministic scenario loss in percent, if available. "
            "Do not emit."
        ),
    )
    drawdown_budget_breached: bool | None = Field(
        default=None,
        description=(
            "Engine-filled. Whether the worst scenario loss exceeds the drawdown budget; "
            "None when no deterministic scenario is available. Do not emit."
        ),
    )
    deployment_required: bool = Field(
        default=False,
        description=(
            "Engine-filled. True when cash is above the maximum and the drawdown budget "
            "is not breached. Do not emit."
        ),
    )
    deployment_candidates: list[DeploymentCandidate] = Field(
        default_factory=list,
        description=(
            "Current portfolio positions best suited to absorb redeployed cash, each with "
            "a one-sentence evidence-grounded rationale."
        ),
    )
    constraint_conflicts: list[str] = Field(
        default_factory=list,
        description="Cases where deploying cash conflicts with other portfolio findings.",
    )
    summary: str = ""
