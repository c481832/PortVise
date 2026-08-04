from __future__ import annotations

import pytest
from pydantic import ValidationError

from port.models import (
    Action,
    CriticalIssue,
    ExposureLayer,
    PortfolioVerdict,
    ThemeAssessment,
    _norm_action_type,
    _norm_priority,
    _norm_severity,
)


def test_enum_normalizers_accept_known_aliases() -> None:
    assert _norm_action_type("sell") == "exit"
    assert _norm_action_type("trim") == "reduce"
    assert _norm_priority("immediate") == "urgent"
    assert _norm_priority("medium") == "this-week"
    assert _norm_severity("severe") == "critical"


def test_enum_normalizers_reject_unknown_values() -> None:
    with pytest.raises(ValueError, match="unrecognized action_type"):
        _norm_action_type("unknown")


def test_exposure_layer_requires_unit_strength() -> None:
    assert (
        ExposureLayer.model_validate(
            {"layer": "factor", "label": "growth", "strength": "0.4", "maps_to": []}
        ).strength
        == 0.4
    )

    with pytest.raises(ValidationError, match="strength must be in"):
        ExposureLayer(layer="factor", label="growth", strength=10, maps_to=[])


def test_theme_assessment_validates_required_fields() -> None:
    assessment = ThemeAssessment.model_validate(
        {
            "theme": "AI capex",
            "supporting_assets": "AAPL",
            "key_evidence": "Capex spending is rising.",
            "assessment": "Evidence supports the AI capex narrative.",
            "implication": "Portfolio remains sensitive to AI spending headlines.",
            "narrative_kind": "structural",
        }
    )

    assert assessment.supporting_assets == ["AAPL"]
    assert assessment.key_evidence == ["Capex spending is rising."]


def test_manager_models_normalize_known_aliases() -> None:
    verdict = PortfolioVerdict.model_validate(
        {
            "action_timing": "immediate",
            "investment_horizon": "tactical",
            "horizon_detail": "1-4 weeks",
            "primary_risk": "Tech concentration",
            "recommended_posture": "Trim exposure",
            "revisit_trigger": "Concentration improves.",
            "rationale": "Risk is elevated.",
        }
    )
    action = Action.model_validate(
        {
            "action_type": "sell",
            "position": "AAPL",
            "rationale": "Reduce concentration.",
            "priority": "medium",
            "size_guidance": "Trim 2%.",
            "hedge_instrument": "",
            "scope": "ticker",
            "risk_addressed": "Single-name concentration",
            "supporting_evidence": "Risk agent flagged AAPL.",
            "revisit_trigger": "Marginal concentration improves.",
        }
    )

    assert verdict.action_timing == "urgent"
    assert verdict.investment_horizon == "tactical"
    assert action.action_type == "exit"
    assert action.priority == "this-week"
    assert action.scope == "position"
    assert action.supporting_evidence == ["Risk agent flagged AAPL."]


def test_action_requires_explicit_scope() -> None:
    with pytest.raises(ValidationError, match="Action.scope is required"):
        Action.model_validate(
            {
                "action_type": "monitor",
                "position": "AAPL",
                "rationale": "Watch.",
                "priority": "watch",
                "size_guidance": "",
                "hedge_instrument": "",
                "risk_addressed": "",
                "supporting_evidence": ["No action."],
                "revisit_trigger": "",
            }
        )


def test_critical_issue_normalizes_severity() -> None:
    issue = CriticalIssue.model_validate(
        {
            "issue": "Liquidity risk",
            "severity": "major",
            "affected_positions": ["AAPL"],
            "source_agents": ["risk"],
        }
    )

    assert issue.severity == "high"
