"""Regime agent — rule-based state vector + historical analog runner + LLM narrative."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from port.agents._base import build_analysis_prompt
from port.config import ReviewStoppedError, invoke_structured, raise_if_review_stopped
from port.config import step_callback as _step_cb
from port.models import HistoricalRegimeOutcome, RegimeReview, RegimeStateVector
from port.prompts import REGIME_SYSTEM_PROMPT
from port.regime_signals import format_regime_python_block
from port.runner import run_analysis

if TYPE_CHECKING:
    from port.state import GraphState

log = logging.getLogger(__name__)

_RUNNER_MAX_ATTEMPTS = 3
_RUNNER_BACKOFF_BASE = 1.0
_RUNNER_BACKOFF_MAX = 6.0


def _runner_backoff(attempt: int) -> float:
    return min(_RUNNER_BACKOFF_BASE * (2 ** max(0, attempt - 1)), _RUNNER_BACKOFF_MAX)


def _merge_regime(llm: RegimeReview, base: RegimeReview) -> RegimeReview:
    """Keep Python regime math; LLM supplies narrative fields."""
    return llm.model_copy(
        update={
            "current_regime": base.current_regime,
            "state_vector": base.state_vector,
            "regime_confidence": base.regime_confidence,
            "portfolio_fit_score": base.portfolio_fit_score,
            "fit_notes": base.fit_notes,
            "historical_outcome": base.historical_outcome,
        }
    )


def _degraded_regime_review(reason: str) -> RegimeReview:
    """Neutral regime baseline when the engine cannot run; lets the LLM still produce narrative."""
    sv = RegimeStateVector()
    return RegimeReview(
        current_regime=(
            f"infl_{sv.inflation_trend}_rates_{sv.rates_trend}_growth_{sv.growth_trend}_"
            f"liq_{sv.liquidity}_vol_{sv.volatility}"
        ),
        state_vector=sv,
        regime_confidence=1,
        portfolio_fit_score=5,
        fit_notes=[
            f"Regime engine unavailable; produced neutral baseline. Underlying error: {reason}"
        ],
        historical_outcome=HistoricalRegimeOutcome(
            runner_available=False,
            message=(
                "Historical analog matching could not run for this review "
                f"(after retries): {reason}"
            ),
        ),
    )


def _run_regime_engine_with_retry(
    payload: dict, *, step_cb=None
) -> tuple[RegimeReview, str | None]:
    last_exc: Exception | None = None
    for attempt in range(1, _RUNNER_MAX_ATTEMPTS + 1):
        raise_if_review_stopped()
        try:
            out = run_analysis("regime_analysis", payload)
            return RegimeReview.model_validate(out["regime_review"]), None
        except ReviewStoppedError:
            raise
        except Exception as exc:
            last_exc = exc
            if attempt >= _RUNNER_MAX_ATTEMPTS:
                break
            delay = _runner_backoff(attempt)
            log.warning(
                "regime runner attempt %d/%d failed (%s) — retrying in %.1fs",
                attempt,
                _RUNNER_MAX_ATTEMPTS,
                exc,
                delay,
            )
            if step_cb:
                step_cb(
                    "regime",
                    0,
                    f"Regime engine retry {attempt}/{_RUNNER_MAX_ATTEMPTS}…",
                )
            time.sleep(delay)
    log.exception("regime runner exhausted retries; falling back to neutral regime baseline")
    return _degraded_regime_review(str(last_exc)), str(last_exc)


def regime_node(state: GraphState) -> dict:
    t0 = time.monotonic()
    log.info("started")
    portfolio = state["portfolio"]
    md = state.get("market_data")
    payload = {
        "portfolio": portfolio.model_dump(mode="json"),
        "market_data": md.model_dump(mode="json") if md else None,
    }
    _cb = _step_cb.get(None)
    base, fallback_reason = _run_regime_engine_with_retry(payload, step_cb=_cb)
    if fallback_reason and _cb:
        _cb(
            "regime",
            0,
            "Regime engine unavailable; using neutral baseline",
        )
    content = build_analysis_prompt(
        state, portfolio_prefix="Portfolio to assess", curated_for="regime"
    )
    content = f"{format_regime_python_block(base)}\n\n{content}"

    if _cb:
        _cb("regime", 0, "Assessing macro regime…")

    llm: RegimeReview = invoke_structured(  # type: ignore[assignment]
        RegimeReview,
        [SystemMessage(content=REGIME_SYSTEM_PROMPT), HumanMessage(content=content)],
        agent="regime",
    )
    result = _merge_regime(llm, base)
    log.info(
        "done in %.1fs%s",
        time.monotonic() - t0,
        " (fallback baseline)" if fallback_reason else "",
    )
    return {"regime_results": [result]}
