"""Regime agent — rule-based state vector + historical analog runner + LLM narrative."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from port.agents._base import build_analysis_prompt
from port.config import invoke_structured
from port.config import step_callback as _step_cb
from port.models import RegimeReview
from port.prompts import REGIME_SYSTEM_PROMPT
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
            "regime_confidence": base.regime_confidence,
            "portfolio_fit_score": base.portfolio_fit_score,
            "fit_notes": base.fit_notes,
            "historical_outcome": base.historical_outcome,
        }
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
    try:
        out = run_analysis("regime_analysis", payload)
    except RuntimeError as exc:
        if _cb:
            _cb("regime", 0, f"Historical analog matching stopped: {exc}")
        raise
    base = RegimeReview.model_validate(out["regime_review"])
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
    log.info("done in %.1fs", time.monotonic() - t0)
    return {"regime_results": [result]}
