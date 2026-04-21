"""Risk agent — Python factor/stress engine + LLM interpretation."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from port.agents._base import build_analysis_prompt
from port.config import invoke_structured
from port.config import step_callback as _step_cb
from port.models import RiskReview
from port.prompts import RISK_SYSTEM_PROMPT
from port.risk_engine import format_risk_python_block
from port.runner import run_analysis

if TYPE_CHECKING:
    from port.state import GraphState

log = logging.getLogger(__name__)


def _merge_risk(llm: RiskReview, base: RiskReview) -> RiskReview:
    merged_issues = list(dict.fromkeys([*base.concentration_issues, *llm.concentration_issues]))
    merged_liq = list(dict.fromkeys([*base.liquidity_notes, *llm.liquidity_notes]))
    merged_fragilities = list(dict.fromkeys([*base.fragilities, *llm.fragilities]))
    return llm.model_copy(
        update={
            "factor_loadings": base.factor_loadings,
            "factor_risk_contribution": base.factor_risk_contribution,
            "marginal_risk_by_ticker": base.marginal_risk_by_ticker,
            "scenario_losses": base.scenario_losses,
            "worst_scenario": base.worst_scenario,
            "concentration_top5_pct": base.concentration_top5_pct,
            "hidden_concentration": base.hidden_concentration,
            "risk_score": base.risk_score,
            "concentration_issues": merged_issues,
            "liquidity_notes": merged_liq,
            "fragilities": merged_fragilities,
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
    out = run_analysis("risk_analysis", payload)
    base = RiskReview.model_validate(out["risk_review"])
    content = build_analysis_prompt(state, curated_for="risk")
    content = f"{format_risk_python_block(base)}\n\n{content}"

    _cb = _step_cb.get(None)
    if _cb:
        _cb("risk", 0, "Analysing portfolio risk…")

    llm: RiskReview = invoke_structured(  # type: ignore[assignment]
        RiskReview,
        [SystemMessage(content=RISK_SYSTEM_PROMPT), HumanMessage(content=content)],
        agent="risk",
    )
    result = _merge_risk(llm, base)
    log.info("done in %.1fs", time.monotonic() - t0)
    return {"risk_results": [result]}
