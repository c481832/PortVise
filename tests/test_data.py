from __future__ import annotations

from port.agents.data import _safe_pct


def test_safe_pct_positive() -> None:
    assert _safe_pct(110, 100) == 10.0


def test_safe_pct_negative() -> None:
    assert _safe_pct(90, 100) == -10.0


def test_safe_pct_zero_denom() -> None:
    assert _safe_pct(100, 0) == 0.0


def test_safe_pct_nan_denom() -> None:
    assert _safe_pct(100, float("nan")) == 0.0


def test_safe_pct_equal() -> None:
    assert _safe_pct(100, 100) == 0.0


def test_safe_pct_rounding() -> None:
    result = _safe_pct(103, 100)
    assert result == 3.0
