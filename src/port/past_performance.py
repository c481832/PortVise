"""Deterministic track record for a single past review's reduce/exit/add calls.

Each scoreable recommendation is judged by its average per-trading-day return minus the
portfolio benchmark, over the window from the review date to today. Per-day (not cumulative)
so the verdict is not biased by how long ago the review ran.

Computed fresh on demand: price history is fetched live so the verdict always reflects the
latest closes, and an older review whose tickers are no longer held is still scoreable.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Literal, cast

import pandas as pd
import yfinance as yf

from port._retry import with_retry
from port.config import config
from port.models import PastCallOutcome, PastPerformanceReview
from port.portfolio import Portfolio
from port.yfinance_compat import suppress_yfinance_pandas4_warnings

log = logging.getLogger(__name__)

_ActionType = Literal["reduce", "exit", "add"]
_Verdict = Literal["validated", "invalidated", "pending"]

_SCOREABLE_ACTIONS = ("reduce", "exit", "add")
# Fetch a few extra calendar days before the review so the baseline close is present even if
# the review date itself was a weekend or market holiday.
_FETCH_BUFFER_DAYS = 5


class _NoHistory(RuntimeError):
    pass


def _review_date(payload: dict) -> date:
    """The review's completion date (t0). Falls back to the stored portfolio review_date."""
    raw = payload.get("saved_at")
    if isinstance(raw, str) and raw.strip():
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    final_state = payload.get("final_state") or {}
    portfolio = final_state.get("portfolio") or {}
    review_date = portfolio.get("review_date")
    if isinstance(review_date, str) and review_date.strip():
        return date.fromisoformat(review_date[:10])
    raise ValueError("review payload has no usable date (saved_at / review_date)")


def _fetch_close_since(ticker: str, start: date) -> pd.Series:
    """Fresh daily close series for ``ticker`` from ``start`` to today. Raises ``_NoHistory``."""
    max_attempts = config.market.fetch_max_attempts
    base_seconds = config.market.fetch_backoff_base_seconds
    cap_seconds = config.market.fetch_backoff_max_seconds

    def attempt() -> pd.Series:
        with suppress_yfinance_pandas4_warnings():
            hist = pd.DataFrame(
                yf.Ticker(ticker).history(
                    start=start.isoformat(), interval="1d", auto_adjust=True
                )
            )
        if hist.empty or "Close" not in hist.columns:
            raise _NoHistory(f"{ticker} returned no close history since {start}")
        close = pd.to_numeric(hist["Close"], errors="coerce").dropna()
        if close.empty:
            raise _NoHistory(f"{ticker} returned no usable closes since {start}")
        close.index = pd.to_datetime(close.index, utc=True).tz_convert(None).normalize()
        close = close.groupby(level=0).last().sort_index()
        close.name = ticker.upper()
        return pd.Series(close)

    def on_attempt(att: int, exc: Exception, delay: float) -> None:
        level = log.info if isinstance(exc, _NoHistory) else log.warning
        level(
            "track-record fetch failed for %s attempt=%d/%d err=%s — retrying in %.1fs",
            ticker,
            att,
            max_attempts,
            exc,
            delay,
        )

    return with_retry(
        attempt,
        attempts=max_attempts,
        base=base_seconds,
        cap=cap_seconds,
        on_attempt=on_attempt,
    )


def _daily_returns_after(close: pd.Series, t0: pd.Timestamp) -> pd.Series:
    """Simple daily returns on trading days strictly after the review date."""
    returns = close.pct_change().dropna()
    return pd.Series(returns[returns.index > t0])


def _score_action(
    name_returns: pd.Series,
    bench_returns: pd.Series,
    action_type: str,
    min_days: int,
) -> tuple[int, float | None, _Verdict]:
    aligned = pd.concat([name_returns, bench_returns], axis=1, join="inner").dropna()
    days = int(len(aligned))
    if days < min_days:
        return days, None, "pending"
    diff = aligned.iloc[:, 0] - aligned.iloc[:, 1]
    daily_outperf = round(float(diff.mean()) * 100.0, 4)
    verdict: _Verdict
    if action_type == "add":
        verdict = "validated" if daily_outperf > 0 else "invalidated"
    else:  # reduce / exit — the bet is that the name lags the benchmark
        verdict = "validated" if daily_outperf < 0 else "invalidated"
    return days, daily_outperf, verdict


def compute_track_record(payload: dict) -> PastPerformanceReview:
    """Score the reduce/exit/add calls of one stored review against price action since then."""
    final_state = payload.get("final_state") or {}
    portfolio = Portfolio.model_validate(final_state.get("portfolio"))
    benchmark = (portfolio.benchmark or "SPY").strip().upper()
    review_id = str(payload.get("review_id") or "")
    min_days = config.track_record.min_comparison_days
    t0 = _review_date(payload)

    manager_review = final_state.get("manager_review")
    raw_actions = manager_review.get("actions") if isinstance(manager_review, dict) else None
    actions = raw_actions if isinstance(raw_actions, list) else []

    valid_tickers = {p.ticker.strip().upper() for p in portfolio.positions}
    scored: list[tuple[_ActionType, str]] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_type = str(action.get("action_type") or "").strip().lower()
        position = str(action.get("position") or "").strip().upper()
        if action_type in _SCOREABLE_ACTIONS and position in valid_tickers:
            scored.append((cast(_ActionType, action_type), position))

    def _review(outcomes: list[PastCallOutcome]) -> PastPerformanceReview:
        matured = [o for o in outcomes if o.verdict != "pending"]
        validated = [o for o in matured if o.verdict == "validated"]
        return PastPerformanceReview(
            review_id=review_id,
            review_date=t0.isoformat(),
            benchmark=benchmark,
            min_comparison_days=min_days,
            matured_count=len(matured),
            validated_count=len(validated),
            outcomes=outcomes,
        )

    if not scored:
        return _review([])

    t0_ts = cast(pd.Timestamp, pd.Timestamp(t0))
    fetch_start = t0 - timedelta(days=_FETCH_BUFFER_DAYS)

    # The benchmark is essential to every verdict — let a fetch failure raise.
    bench_returns = _daily_returns_after(_fetch_close_since(benchmark, fetch_start), t0_ts)

    name_returns: dict[str, pd.Series | None] = {}
    for ticker in sorted({ticker for _action_type, ticker in scored}):
        try:
            name_returns[ticker] = _daily_returns_after(
                _fetch_close_since(ticker, fetch_start), t0_ts
            )
        except _NoHistory:
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
        days, daily_outperf, verdict = _score_action(
            returns, bench_returns, action_type, min_days
        )
        outcomes.append(
            PastCallOutcome(
                position=ticker,
                action_type=action_type,
                days_elapsed=days,
                daily_outperf_pct=daily_outperf,
                verdict=verdict,
            )
        )

    return _review(outcomes)
