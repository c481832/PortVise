"""Regime agent — rule-based state vector + historical analog runner + LLM narrative.

No degraded-review fallback: engine failure propagates and fails the review loudly.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from port._retry import with_retry
from port.agents._base import build_analysis_prompt
from port.config import ReviewStoppedError, config, invoke_structured
from port.config import step_callback as _step_cb
from port.models import RegimeReview
from port.prompts import regime_system_prompt
from port.regime_signals import format_regime_python_block
from port.runner import run_analysis

if TYPE_CHECKING:
    from port.state import GraphState

log = logging.getLogger(__name__)


def _merge_regime(llm: RegimeReview, base: RegimeReview) -> RegimeReview:
    """Keep Python regime math; LLM supplies narrative fields."""
    return llm.model_copy(
        update={
            "current_regime": base.current_regime,
            "state_vector": base.state_vector,
            "historical_outcome": base.historical_outcome,
        }
    )


def _run_regime_engine(payload: dict, *, step_cb=None) -> RegimeReview:
    """Run the deterministic regime engine with retry; raises on permanent failure."""
    max_attempts = config.runner.max_attempts
    base_seconds = config.runner.backoff_base_seconds
    cap_seconds = config.runner.backoff_max_seconds

    def attempt() -> RegimeReview:
        out = run_analysis("regime_analysis", payload)
        return RegimeReview.model_validate(out["regime_review"])

    def on_attempt(att: int, exc: Exception, delay: float) -> None:
        log.warning(
            "regime runner attempt %d/%d failed (%s) — retrying in %.1fs",
            att,
            max_attempts,
            exc,
            delay,
        )
        if step_cb:
            step_cb("regime", 1, f"Regime engine retry {att}/{max_attempts}…")

    return with_retry(
        attempt,
        attempts=max_attempts,
        base=base_seconds,
        cap=cap_seconds,
        on_attempt=on_attempt,
        stop_on=ReviewStoppedError,
    )


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
    if _cb:
        _cb("regime", 0, "Preparing regime engine inputs…")
        _cb("regime", 1, "Running regime and analog engine…")
    base = _run_regime_engine(payload, step_cb=_cb)
    if _cb:
        _cb("regime", 2, "Building regime interpretation prompt…")
    content = build_analysis_prompt(state, portfolio_prefix="Portfolio to assess")
    content = f"{format_regime_python_block(base)}\n\n{content}"

    if _cb:
        _cb("regime", 3, "Interpreting macro regime fit…")

    llm: RegimeReview = invoke_structured(  # type: ignore[assignment]
        RegimeReview,
        [SystemMessage(content=regime_system_prompt()), HumanMessage(content=content)],
        agent="regime",
    )
    if _cb:
        _cb("regime", 4, "Merging computed analogs with regime narrative…")
    result = _merge_regime(llm, base)
    log.info("done in %.1fs", time.monotonic() - t0)
    return {"regime_results": [result]}
