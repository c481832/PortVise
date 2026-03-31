from __future__ import annotations

import pytest

from port.models import (
    Action,
    CriticalIssue,
    FactorExposure,
    ThemeAlignment,
    _norm_action_type,
    _norm_direction,
    _norm_impact,
    _norm_magnitude,
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


def test_factor_exposure_normalizes_direction() -> None:
    fe = FactorExposure(factor="momentum", direction="overweight", magnitude="large")  # type: ignore[arg-type]
    assert fe.direction == "long"
    assert fe.magnitude == "high"


def test_critical_issue_normalizes_severity() -> None:
    ci = CriticalIssue(issue="test", severity="severe")  # type: ignore[arg-type]
    assert ci.severity == "critical"


def test_theme_alignment_normalizes_stance() -> None:
    ta = ThemeAlignment(theme="AI", portfolio_stance="long")  # type: ignore[arg-type]
    assert ta.portfolio_stance == "aligned"


def test_action_normalizes_type_and_priority() -> None:
    a = Action(action_type="sell", position="AAPL", priority="immediate")  # type: ignore[arg-type]
    assert a.action_type == "exit"
    assert a.priority == "urgent"
