"""Final portfolio verdict and the action list."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

from port.models.normalizers import (
    IGNORE_EXTRA,
    coerce_string_list,
    norm_action_scope,
    norm_action_type,
    norm_priority,
)


class PortfolioVerdict(BaseModel):
    model_config = IGNORE_EXTRA

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
        return norm_priority(v)


class Action(BaseModel):
    model_config = IGNORE_EXTRA

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
        return norm_action_type(v)

    @field_validator("priority", mode="before")
    @classmethod
    def _pri(cls, v):
        return norm_priority(v)

    @field_validator("scope", mode="before")
    @classmethod
    def _scope(cls, v):
        return norm_action_scope(v)

    @field_validator("supporting_evidence", mode="before")
    @classmethod
    def _supporting_evidence(cls, v):
        return coerce_string_list(v)


class ManagerReview(BaseModel):
    model_config = IGNORE_EXTRA

    portfolio_verdict: PortfolioVerdict
    actions: list[Action]
    do_nothing_case: str
    executive_summary: str
