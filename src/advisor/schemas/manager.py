"""Final portfolio verdict and the action list."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class PortfolioVerdict(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action_timing: Literal["urgent", "this-week", "next-review", "watch"]
    investment_horizon: Literal["tactical", "medium-term", "strategic"]
    horizon_detail: str
    primary_risk: str
    recommended_posture: str
    revisit_trigger: str
    rationale: str


class Action(BaseModel):
    model_config = ConfigDict(extra="ignore")

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


class InvestorLens(BaseModel):
    model_config = ConfigDict(extra="ignore")

    base_case: str
    alternative_scenarios: list[str]
    profile_challenge: str


class ManagerReview(BaseModel):
    model_config = ConfigDict(extra="ignore")

    portfolio_verdict: PortfolioVerdict
    actions: list[Action]
    do_nothing_case: str
    investor_lens: InvestorLens
    executive_summary: str
