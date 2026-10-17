"""Deterministic track record for a single past review's reduce/exit/add calls.

Each scoreable recommendation is judged by its average per-trading-day return minus the
portfolio benchmark, over the window from the review date to today. Per-day (not cumulative)
so the verdict is not biased by how long ago the review ran.

Computed fresh on demand: price history is fetched live so the verdict always reflects the
latest closes, and an older review whose tickers are no longer held is still scoreable.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal, cast

import pandas as pd

from advisor.config import config
from advisor.market_data import fetch_close_since
from advisor.schemas.performance import PastCallOutcome, PastPerformanceReview
from advisor.schemas.portfolio import Portfolio

ActionType = Literal["reduce", "exit", "add"]
Verdict = Literal["validated", "invalidated", "pending"]

SCOREABLE_ACTIONS = ("reduce", "exit", "add")
# Fetch a few extra calendar days before the review so the baseline close is present even if
# the review date itself was a weekend or market holiday.
FETCH_BUFFER_DAYS = 5


def parse_review_date(payload: dict) -> date:
    """The review's completion date (t0)."""
    return datetime.fromisoformat(payload["saved_at"]).date()


def daily_returns_after(close: pd.Series, t0: pd.Timestamp) -> pd.Series:
    """Simple daily returns on trading days strictly after the review date."""
    returns = close.pct_change().dropna()
    return pd.Series(returns[returns.index > t0])


def score_action(
    name_returns: pd.Series,
    bench_returns: pd.Series,
    action_type: str,
    min_days: int,
) -> tuple[int, float | None, Verdict]:
    aligned = pd.concat([name_returns, bench_returns], axis=1, join="inner").dropna()
    days = int(len(aligned))
    if days < min_days:
        return days, None, "pending"
    diff = aligned.iloc[:, 0] - aligned.iloc[:, 1]
    daily_outperf = round(float(diff.mean()) * 100.0, 4)
    verdict: Verdict
    if action_type == "add":
        verdict = "validated" if daily_outperf > 0 else "invalidated"
    else:  # reduce / exit — the bet is that the name lags the benchmark
        verdict = "validated" if daily_outperf < 0 else "invalidated"
    return days, daily_outperf, verdict


def compute_track_record(payload: dict) -> PastPerformanceReview:
    """Score the reduce/exit/add calls of one stored review against price action since then."""
    final_state = payload["final_state"]
    portfolio = Portfolio.model_validate(final_state["portfolio"])
    benchmark = portfolio.benchmark.strip().upper()
    review_id = payload["review_id"]
    min_days = config.track_record.min_comparison_days
    t0 = parse_review_date(payload)

    valid_tickers = {p.ticker for p in portfolio.positions}
    scored: list[tuple[ActionType, str]] = []
    # Reviews saved by the pre-split pipeline have no manager_review in final_state.
    manager_review = final_state["manager_review"]
    actions = manager_review["actions"] if manager_review is not None else []
    for action in actions:
        action_type = action["action_type"]
        position = action["position"].strip().upper()
        if action_type in SCOREABLE_ACTIONS and position in valid_tickers:
            scored.append((cast(ActionType, action_type), position))

    def review(outcomes: list[PastCallOutcome]) -> PastPerformanceReview:
        matured = [o for o in outcomes if o.verdict != "pending"]
        validated = [o for o in matured if o.verdict == "validated"]
        return PastPerformanceReview(
            review_id=review_id,
            review_date=t0.isoformat(),
            benchmark=benchmark,
            matured_count=len(matured),
            validated_count=len(validated),
            outcomes=outcomes,
        )

    if not scored:
        return review([])

    t0_ts = cast(pd.Timestamp, pd.Timestamp(t0))
    fetch_start = t0 - timedelta(days=FETCH_BUFFER_DAYS)

    # The benchmark is essential to every verdict — let a fetch failure raise.
    bench_returns = daily_returns_after(fetch_close_since(benchmark, fetch_start), t0_ts)

    name_returns: dict[str, pd.Series | None] = {}
    for ticker in sorted({ticker for _action_type, ticker in scored}):
        try:
            name_returns[ticker] = daily_returns_after(
                fetch_close_since(ticker, fetch_start), t0_ts
            )
        except RuntimeError:
            name_returns[ticker] = None

    outcomes: list[PastCallOutcome] = []
    for action_type, ticker in scored:
        returns = name_returns.get(ticker)
        if returns is None:
            outcomes.append(
                PastCallOutcome(
                    position=ticker,
                    action_type=action_type,
                    days_elapsed=0,
                    daily_outperf_pct=None,
                    verdict="pending",
                    note="no price history available",
                )
            )
            continue
        days, daily_outperf, verdict = score_action(returns, bench_returns, action_type, min_days)
        outcomes.append(
            PastCallOutcome(
                position=ticker,
                action_type=action_type,
                days_elapsed=days,
                daily_outperf_pct=daily_outperf,
                verdict=verdict,
            )
        )

    return review(outcomes)
