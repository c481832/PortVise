from __future__ import annotations

import logging
import time

from langchain_core.messages import HumanMessage, SystemMessage

from advisor.agents.base import build_analysis_prompt
from advisor.config import config
from advisor.llm.context import report_step
from advisor.llm.structured import invoke_structured
from advisor.prompts import risk_system_prompt
from advisor.prompts.risk import risk_engine_to_text
from advisor.quant import compute_risk_review_base
from advisor.schemas.risk import RiskReview
from advisor.schemas.state import GraphState

log = logging.getLogger(__name__)


def merge_risk_review(llm: RiskReview, base: RiskReview) -> RiskReview:
    merged_issues = list(dict.fromkeys([*base.concentration_issues, *llm.concentration_issues]))
    merged_top_risks = list(dict.fromkeys([*base.top_risks, *llm.top_risks]))
    return llm.model_copy(
        update={
            "factor_loadings": base.factor_loadings,
            "factor_risk_contribution": base.factor_risk_contribution,
            "risk_contribution_by_ticker": base.risk_contribution_by_ticker,
            "volatility_contribution_by_ticker": base.volatility_contribution_by_ticker,
            "portfolio_volatility": base.portfolio_volatility,
            "scenario_losses": base.scenario_losses,
            "worst_scenario": base.worst_scenario,
            "concentration_top5_pct": base.concentration_top5_pct,
            "hidden_concentration": base.hidden_concentration,
            "concentration_issues": merged_issues,
            "top_risks": merged_top_risks,
        }
    )


def risk_node(state: GraphState) -> dict:
    t0 = time.monotonic()
    log.info("started")
    portfolio = state["portfolio"]
    report_step("risk", 0, "Preparing risk engine inputs…")
    report_step("risk", 1, "Running factor and stress engine…")
    base = compute_risk_review_base(portfolio)
    report_step("risk", 2, "Building risk interpretation prompt…")
    content = build_analysis_prompt(state)
    content = f"{risk_engine_to_text(base, portfolio)}\n\n{content}"

    report_step("risk", 3, "Interpreting risk findings…")

    llm: RiskReview = invoke_structured(  # type: ignore[assignment]
        RiskReview,
        [SystemMessage(content=risk_system_prompt()), HumanMessage(content=content)],
        agent="risk",
        max_tokens=config.llm.structured_max_tokens,
        temperature=config.llm.structured_temperature,
        use_agent_model=True,
    )
    report_step("risk", 4, "Merging computed attribution with narrative risks…")
    result = merge_risk_review(llm, base)
    log.info("done in %.1fs", time.monotonic() - t0)
    return {"risk_review": result}
