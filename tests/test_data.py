from __future__ import annotations

import pandas as pd

from port.agents.data import _safe_pct
from port.market_data import _corporate_actions_from_history


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


def test_safe_pct_nan_numerator() -> None:
    assert _safe_pct(float("nan"), 100) == 0.0


def test_safe_pct_rounding() -> None:
    result = _safe_pct(103, 100)
    assert result == 3.0


def test_corporate_actions_adjusts_dividends_for_splits() -> None:
    hist = pd.DataFrame(
        {
            "Dividends": [1.0, 0.0, 0.5],
            "Stock Splits": [0.0, 2.0, 0.0],
        }
    )

    dividend, split = _corporate_actions_from_history(hist)

    assert dividend == 2.0
    assert split == 2.0
