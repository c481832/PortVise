from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

from port.agents.data import _safe_pct
from port.market_data import (
    _corporate_actions_from_history,
    fetch_corporate_actions,
    fetch_position_snapshot,
    fetch_ticker_profile,
)


def test_safe_pct_returns_rounded_percent_change() -> None:
    assert _safe_pct(110, 100) == 10.0
    assert _safe_pct(90, 100) == -10.0
    assert _safe_pct(100, 100) == 0.0
    assert _safe_pct(103, 100) == 3.0


@pytest.mark.parametrize(("new", "old"), [(100, 0), (100, float("nan")), (float("nan"), 100)])
def test_safe_pct_rejects_degenerate_inputs(new: float, old: float) -> None:
    with pytest.raises(ValueError, match="degenerate inputs"):
        _safe_pct(new, old)


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


def test_corporate_actions_empty_history_means_no_actions() -> None:
    dividend, split = _corporate_actions_from_history(pd.DataFrame())

    assert dividend == 0.0
    assert split == 1.0


def test_fetch_corporate_actions_forwards_history_timeout() -> None:
    class FakeTicker:
        def __init__(self, ticker: str) -> None:
            self.ticker = ticker

        def history(self, **kwargs):
            seen_kwargs.update(kwargs)
            return pd.DataFrame({"Dividends": [0.0], "Stock Splits": [0.0]})

    seen_kwargs = {}

    with patch("port.market_data.yf.Ticker", side_effect=FakeTicker):
        dividend, split = fetch_corporate_actions(
            "AAPL",
            date(2023, 1, 1),
            timeout=3.5,
        )

    assert dividend == 0.0
    assert split == 1.0
    assert seen_kwargs["timeout"] == 3.5


def test_fetch_ticker_profile_normalizes_basic_metadata() -> None:
    class FakeTicker:
        def __init__(self, ticker: str) -> None:
            self.ticker = ticker

        def get_info(self):
            return {
                "shortName": "Apple Inc.",
                "longName": "Apple Inc. Long",
                "sector": "Technology",
                "industry": "Consumer Electronics",
            }

    fake_config = SimpleNamespace(
        market=SimpleNamespace(
            fetch_max_attempts=1,
            fetch_backoff_base_seconds=0.0,
            fetch_backoff_max_seconds=0.0,
        )
    )

    with (
        patch("port.market_data.config", fake_config),
        patch("port.market_data.yf.Ticker", side_effect=FakeTicker),
    ):
        profile = fetch_ticker_profile("aapl")

    assert profile.ticker == "AAPL"
    assert profile.name == "Apple Inc."
    assert profile.sector == "Technology"
    assert profile.industry == "Consumer Electronics"


def test_fetch_ticker_profile_falls_back_to_long_name() -> None:
    class FakeTicker:
        def __init__(self, ticker: str) -> None:
            self.ticker = ticker

        def get_info(self):
            return {
                "shortName": None,
                "longName": "Vanguard Total Bond Market ETF",
                "sector": None,
            }

    fake_config = SimpleNamespace(
        market=SimpleNamespace(
            fetch_max_attempts=1,
            fetch_backoff_base_seconds=0.0,
            fetch_backoff_max_seconds=0.0,
        )
    )

    with (
        patch("port.market_data.config", fake_config),
        patch("port.market_data.yf.Ticker", side_effect=FakeTicker),
    ):
        profile = fetch_ticker_profile("bnd")

    assert profile.name == "Vanguard Total Bond Market ETF"
    assert profile.sector == ""


def test_fetch_position_snapshot_saves_full_history_and_omits_headlines(tmp_path) -> None:
    dates = pd.date_range("2025-01-01", periods=260, freq="B")
    price_hist = pd.DataFrame(
        {
            "Close": [100.0 + i for i in range(260)],
            "High": [101.0 + i for i in range(260)],
            "Low": [99.0 + i for i in range(260)],
        },
        index=dates,
    )
    action_hist = pd.DataFrame(
        {"Dividends": [1.0], "Stock Splits": [2.0]},
        index=pd.DatetimeIndex(["2025-06-01"]),
    )

    class FakeTicker:
        def __init__(self, ticker: str) -> None:
            self.ticker = ticker

        def history(self, **kwargs):
            if kwargs.get("actions") is True:
                return action_hist
            assert kwargs["period"] == "max"
            return price_hist

    fake_config = SimpleNamespace(
        market=SimpleNamespace(
            fetch_max_attempts=1,
            fetch_backoff_base_seconds=0.0,
            fetch_backoff_max_seconds=0.0,
            price_history_period="max",
            local_data_dir=str(tmp_path),
        )
    )

    with (
        patch("port.market_data.config", fake_config),
        patch("port.market_data.yf.Ticker", side_effect=FakeTicker),
    ):
        snap = fetch_position_snapshot("AAPL", date(2025, 1, 1))

    assert snap.current_price == 359.0
    assert snap.prev_close == 358.0
    assert snap.dividend == 1.0
    assert snap.split == 2.0
    assert not hasattr(snap, "recent_headlines")
    assert (tmp_path / "positions" / "AAPL.csv").exists()
    assert (tmp_path / "corporate_actions" / "AAPL.csv").exists()
