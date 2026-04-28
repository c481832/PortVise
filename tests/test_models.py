from __future__ import annotations

import pytest

from port.models import (
    Action,
    CriticalIssue,
    ExposureLayer,
    ManagerReview,
    PortfolioStance,
    ThemeMatchScore,
    _norm_action_scope,
    _norm_action_type,
    _norm_direction,
    _norm_impact,
    _norm_magnitude,
    _norm_portfolio_stance,
    _norm_priority,
    _norm_severity,
    _norm_stance,
    _norm_urgency,
)


@pytest.mark.parametrize(
    "input_val,expected",
    [
        ("positive", "positive"),
        ("pos", "positive"),
        ("negative", "negative"),
        ("neg", "negative"),
        ("neutral", "neutral"),
        ("uncertain", "uncertain"),
        ("POSITIVE", "positive"),
        ("unknown", "uncertain"),
    ],
)
def test_norm_impact(input_val: str, expected: str) -> None:
    assert _norm_impact(input_val) == expected


@pytest.mark.parametrize(
    "input_val,expected",
    [
        ("immediate", "immediate"),
        ("critical", "immediate"),
        ("high", "immediate"),
        ("this-week", "this-week"),
        ("this_week", "this-week"),
        ("medium", "this-week"),
        ("low", "low"),
        ("watch", "low"),
        ("something-else", "monitor"),
    ],
)
def test_norm_urgency(input_val: str, expected: str) -> None:
    assert _norm_urgency(input_val) == expected


@pytest.mark.parametrize(
    "input_val,expected",
    [
        ("long", "long"),
        ("short", "short"),
        ("neutral", "neutral"),
        ("overweight", "long"),
        ("underweight", "short"),
        ("unknown", "neutral"),
    ],
)
def test_norm_direction(input_val: str, expected: str) -> None:
    assert _norm_direction(input_val) == expected


@pytest.mark.parametrize(
    "input_val,expected",
    [
        ("high", "high"),
        ("medium", "medium"),
        ("low", "low"),
        ("large", "high"),
        ("small", "low"),
        ("moderate", "medium"),
        ("unknown", "medium"),
    ],
)
def test_norm_magnitude(input_val: str, expected: str) -> None:
    assert _norm_magnitude(input_val) == expected


@pytest.mark.parametrize(
    "input_val,expected",
    [
        ("critical", "critical"),
        ("high", "high"),
        ("medium", "medium"),
        ("low", "low"),
        ("severe", "critical"),
        ("major", "high"),
        ("minor", "low"),
        ("unknown", "medium"),
    ],
)
def test_norm_severity(input_val: str, expected: str) -> None:
    assert _norm_severity(input_val) == expected


@pytest.mark.parametrize(
    "input_val,expected",
    [
        ("aligned", "aligned"),
        ("fighting", "fighting"),
        ("neutral", "neutral"),
        ("overweight", "overweight"),
        ("underweight", "underweight"),
        ("long", "aligned"),
        ("short", "fighting"),
        ("unknown", "neutral"),
    ],
)
def test_norm_stance(input_val: str, expected: str) -> None:
    assert _norm_stance(input_val) == expected


@pytest.mark.parametrize(
    "input_val,expected",
    [
        ("reduce", "reduce"),
        ("exit", "exit"),
        ("hedge", "hedge"),
        ("rotate", "rotate"),
        ("add", "add"),
        ("monitor", "monitor"),
        ("no-action", "no-action"),
        ("sell", "exit"),
        ("trim", "reduce"),
        ("buy", "add"),
        ("no_action", "no-action"),
        ("hold", "monitor"),
        ("unknown", "monitor"),
    ],
)
def test_norm_action_type(input_val: str, expected: str) -> None:
    assert _norm_action_type(input_val) == expected


@pytest.mark.parametrize(
    "input_val,expected",
    [
        ("urgent", "urgent"),
        ("immediate", "urgent"),
        ("critical", "urgent"),
        ("this-week", "this-week"),
        ("this_week", "this-week"),
        ("medium", "this-week"),
        ("next-review", "next-review"),
        ("next_review", "next-review"),
        ("low", "next-review"),
        ("unknown", "watch"),
    ],
)
def test_norm_priority(input_val: str, expected: str) -> None:
    assert _norm_priority(input_val) == expected


@pytest.mark.parametrize(
    "input_val,expected",
    [
        ("defensive", "defensive"),
        ("risk-off", "defensive"),
        ("risk_off", "defensive"),
        ("balanced", "balanced"),
        ("neutral", "balanced"),
        ("opportunistic", "opportunistic"),
        ("risk-on", "opportunistic"),
        ("risk_on", "opportunistic"),
        ("wait", "wait"),
        ("hold", "wait"),
        ("unknown", "balanced"),
    ],
)
def test_norm_portfolio_stance(input_val: str, expected: str) -> None:
    assert _norm_portfolio_stance(input_val) == expected


@pytest.mark.parametrize(
    "input_val,expected",
    [
        ("portfolio", "portfolio"),
        ("portfolio-level", "portfolio"),
        ("book", "portfolio"),
        ("position", "position"),
        ("ticker", "position"),
        ("security", "position"),
        ("unknown", "position"),
    ],
)
def test_norm_action_scope(input_val: str, expected: str) -> None:
    assert _norm_action_scope(input_val) == expected


def test_exposure_layer_defaults() -> None:
    el = ExposureLayer(layer="factor", label="growth", strength=0.4, maps_to=["AI capex"])
    assert el.layer == "factor"
    assert el.strength == 0.4


@pytest.mark.parametrize(
    "given, expected",
    [
        (10, 1.0),  # 1–10 scale → 1.0
        (-10, -1.0),
        (7, 0.7),
        (-3, -0.3),
        (50, 0.5),  # 0–100 scale
        (-25, -0.25),
        (200, 1.0),  # absurd input → clamped
        (-9999, -1.0),
        ("0.4", 0.4),
        (None, 0.0),
        ("not-a-number", 0.0),
        (float("nan"), 0.0),
    ],
)
def test_exposure_layer_strength_normalizes_scale(given, expected) -> None:
    el = ExposureLayer(layer="factor", label="x", strength=given)
    assert el.strength == pytest.approx(expected)


def test_theme_match_score_bounds() -> None:
    tm = ThemeMatchScore(
        theme="Test",
        portfolio_exposure=0.5,
        news_strength=0.6,
        confidence=0.7,
        supporting_assets=["X"],
        key_evidence=["e"],
    )
    assert tm.portfolio_exposure == 0.5


def test_critical_issue_normalizes_severity() -> None:
    ci = CriticalIssue(issue="test", severity="severe")  # type: ignore[arg-type]
    assert ci.severity == "critical"


def test_action_normalizes_type_and_priority() -> None:
    a = Action(action_type="sell", position="AAPL", priority="immediate")  # type: ignore[arg-type]
    assert a.action_type == "exit"
    assert a.priority == "urgent"


def test_portfolio_stance_defaults_and_normalization() -> None:
    stance = PortfolioStance(stance="risk-off", urgency="immediate")  # type: ignore[arg-type]

    assert stance.stance == "defensive"
    assert stance.urgency == "urgent"
    assert stance.primary_risk == ""
    assert stance.recommended_posture == ""
    assert stance.rationale == ""


def test_portfolio_stance_metadata_fields_tolerate_null() -> None:
    stance = PortfolioStance.model_validate(
        {
            "primary_risk": None,
            "recommended_posture": None,
            "rationale": None,
        }
    )

    assert stance.primary_risk == ""
    assert stance.recommended_posture == ""
    assert stance.rationale == ""


def test_action_infers_portfolio_scope_for_legacy_portfolio_level_position() -> None:
    action = Action(action_type="trim", position="portfolio-level", priority="medium")  # type: ignore[arg-type]

    assert action.action_type == "reduce"
    assert action.priority == "this-week"
    assert action.scope == "portfolio"
    assert action.risk_addressed == ""
    assert action.supporting_evidence == []
    assert action.revisit_trigger == ""


def test_action_defaults_to_position_scope_for_legacy_ticker_action() -> None:
    action = Action(position="AAPL")

    assert action.scope == "position"
    assert action.supporting_evidence == []


def test_action_coerces_string_supporting_evidence_to_list() -> None:
    action = Action.model_validate(
        {
            "position": "AAPL",
            "supporting_evidence": "Risk flagged AAPL as a top marginal risk contributor.",
        }
    )

    assert action.supporting_evidence == ["Risk flagged AAPL as a top marginal risk contributor."]


def test_action_new_metadata_fields_tolerate_null() -> None:
    action = Action.model_validate(
        {
            "position": "AAPL",
            "risk_addressed": None,
            "revisit_trigger": None,
        }
    )

    assert action.risk_addressed == ""
    assert action.revisit_trigger == ""


def test_manager_review_defaults_portfolio_stance() -> None:
    review = ManagerReview()

    assert review.portfolio_stance == PortfolioStance()


def test_manager_review_coerces_null_portfolio_stance_to_default() -> None:
    review = ManagerReview.model_validate({"portfolio_stance": None})

    assert review.portfolio_stance == PortfolioStance()
