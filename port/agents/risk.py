"""Risk agent — Python factor/stress engine + LLM interpretation.

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
from port.models import RiskReview
from port.prompts import RISK_SYSTEM_PROMPT
from port.risk_engine import format_risk_python_block
from port.runner import run_analysis

if TYPE_CHECKING:
    from port.state import GraphState

log = logging.getLogger(__name__)


def _run_risk_engine(payload: dict, *, step_cb=None) -> RiskReview:
    """Run the deterministic risk engine with retry; raises on permanent failure."""
    max_attempts = config.runner.max_attempts
    base_seconds = config.runner.backoff_base_seconds
    cap_seconds = config.runner.backoff_max_seconds

    def attempt() -> RiskReview:
        out = run_analysis("risk_analysis", payload)
        return RiskReview.model_validate(out["risk_review"])

    def on_attempt(att: int, exc: Exception, delay: float) -> None:
        log.warning(
            "risk runner attempt %d/%d failed (%s) — retrying in %.1fs",
            att,
            max_attempts,
            exc,
            delay,
        )
        if step_cb:
            step_cb("risk", 1, f"Risk engine retry {att}/{max_attempts}…")

    return with_retry(
        attempt,
        attempts=max_attempts,
        base=base_seconds,
        cap=cap_seconds,
        on_attempt=on_attempt,
        stop_on=ReviewStoppedError,
    )


def _merge_risk(llm: RiskReview, base: RiskReview) -> RiskReview:
    merged_issues = list(dict.fromkeys([*base.concentration_issues, *llm.concentration_issues]))
    merged_liq = list(dict.fromkeys([*base.liquidity_notes, *llm.liquidity_notes]))
    merged_fragilities = list(dict.fromkeys([*base.fragilities, *llm.fragilities]))
    merged_top_risks = list(dict.fromkeys([*base.top_risks, *llm.top_risks]))
    return llm.model_copy(
        update={
            "factor_loadings": base.factor_loadings,
            "factor_risk_contribution": base.factor_risk_contribution,
            "marginal_risk_by_ticker": base.marginal_risk_by_ticker,
            "scenario_losses": base.scenario_losses,
            "worst_scenario": base.worst_scenario,
            "concentration_top5_pct": base.concentration_top5_pct,
            "hidden_concentration": base.hidden_concentration,
            "concentration_issues": merged_issues,
            "liquidity_notes": merged_liq,
            "fragilities": merged_fragilities,
            "top_risks": merged_top_risks,
        }
    )


def risk_node(state: GraphState) -> dict:
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
        _cb("risk", 0, "Preparing risk engine inputs…")
        _cb("risk", 1, "Running factor and stress engine…")
    base = _run_risk_engine(payload, step_cb=_cb)
    if _cb:
        _cb("risk", 2, "Building risk interpretation prompt…")
    content = build_analysis_prompt(state, portfolio_prefix="Portfolio to review")
    content = f"{format_risk_python_block(base)}\n\n{content}"

    if _cb:
        _cb("risk", 3, "Interpreting risk findings…")

    llm: RiskReview = invoke_structured(  # type: ignore[assignment]
        RiskReview,
        [SystemMessage(content=RISK_SYSTEM_PROMPT), HumanMessage(content=content)],
        agent="risk",
    )
    if _cb:
        _cb("risk", 4, "Merging computed attribution with narrative risks…")
    result = _merge_risk(llm, base)
    log.info("done in %.1fs", time.monotonic() - t0)
    return {"risk_results": [result]}
