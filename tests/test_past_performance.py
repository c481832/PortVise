"""Scoring logic for the past-review track record (no network: fetch is monkeypatched)."""

from __future__ import annotations

import pandas as pd
import pytest

from port import past_performance
from port.past_performance import compute_track_record


def _series(daily_ret: float, periods: int) -> pd.Series:
    idx = pd.bdate_range(start="2024-01-08", periods=periods)
    prices = [100.0]
    for _ in range(periods - 1):
        prices.append(prices[-1] * (1.0 + daily_ret))
    return pd.Series(prices, index=idx)


# Constant daily return per ticker -> constant daily outperformance vs the flat benchmark.
_FAKE_SERIES = {
    "SPY": _series(0.0, 20),  # flat benchmark
    "AAA": _series(-0.002, 20),  # lagged -> reduce validated
    "BBB": _series(0.002, 20),  # led -> add validated
    "CCC": _series(0.002, 20),  # led -> reduce invalidated
    "DDD": _series(0.002, 8),  # only ~2 trading days after t0 -> pending
}


def _fake_fetch(ticker: str, start) -> pd.Series:
    if ticker == "EEE":
        raise past_performance._NoHistory("delisted")
    return _FAKE_SERIES[ticker]


def _position(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "name": ticker,
        "weight": 0.2,
        "quantity": 1.0,
        "sector": "Tech",
        "entry_date": "2023-01-01",
        "entry_price": 100.0,
        "current_price": 100.0,
        "entry_thesis": "thesis",
    }


def _payload() -> dict:
    tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
    actions = [
        {"action_type": "reduce", "position": "AAA"},
        {"action_type": "add", "position": "BBB"},
        {"action_type": "reduce", "position": "CCC"},
        {"action_type": "add", "position": "DDD"},
        {"action_type": "add", "position": "EEE"},
        {"action_type": "monitor", "position": "FFF"},  # not scoreable
        {"action_type": "add", "position": "portfolio"},  # not a held ticker
    ]
    return {
        "review_id": "rid-1",
        "saved_at": "2024-01-15T00:00:00+00:00",
        "status": "done",
        "final_state": {
            "portfolio": {
                "name": "P",
                "benchmark": "SPY",
                "positions": [_position(t) for t in tickers],
            },
            "manager_review": {"actions": actions},
        },
    }


@pytest.fixture
def review(monkeypatch):
    monkeypatch.setattr(past_performance, "_fetch_close_since", _fake_fetch)
    return compute_track_record(_payload())


def _by_position(review) -> dict:
    return {o.position: o for o in review.outcomes}


def test_only_scoreable_actions_on_held_tickers(review):
    # monitor and the portfolio-level action are excluded.
    assert {o.position for o in review.outcomes} == {"AAA", "BBB", "CCC", "DDD", "EEE"}


def test_verdicts(review):
    outcomes = _by_position(review)
    assert outcomes["AAA"].verdict == "validated"  # reduce, lagged
    assert outcomes["BBB"].verdict == "validated"  # add, led
    assert outcomes["CCC"].verdict == "invalidated"  # reduce, but led


def test_daily_outperformance_sign_and_magnitude(review):
    outcomes = _by_position(review)
    assert outcomes["AAA"].daily_outperf_pct == pytest.approx(-0.2, abs=1e-6)
    assert outcomes["BBB"].daily_outperf_pct == pytest.approx(0.2, abs=1e-6)


def test_pending_when_too_recent(review):
    outcome = _by_position(review)["DDD"]
    assert outcome.verdict == "pending"
    assert outcome.daily_outperf_pct is None
    assert outcome.days_elapsed < review.min_comparison_days


def test_pending_when_no_history(review):
    outcome = _by_position(review)["EEE"]
    assert outcome.verdict == "pending"
    assert outcome.note == "no price history available"


def test_aggregate_counts(review):
    assert review.matured_count == 3
    assert review.validated_count == 2
    assert review.benchmark == "SPY"
    assert review.review_date == "2024-01-15"


def test_no_scoreable_actions_returns_empty(monkeypatch):
    monkeypatch.setattr(past_performance, "_fetch_close_since", _fake_fetch)
    payload = _payload()
    payload["final_state"]["manager_review"]["actions"] = [
        {"action_type": "monitor", "position": "AAA"},
    ]
    review = compute_track_record(payload)
    assert review.outcomes == []
    assert review.matured_count == 0
