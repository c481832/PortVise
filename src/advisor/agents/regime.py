from __future__ import annotations

import logging
import time

from langchain_core.messages import HumanMessage, SystemMessage

from advisor.agents.base import build_analysis_prompt
from advisor.config import config
from advisor.llm.context import report_step
from advisor.llm.structured import invoke_structured
from advisor.prompts import regime_system_prompt
from advisor.prompts.regime import regime_engine_to_text
from advisor.quant import compute_regime_review_base
from advisor.schemas.regime import RegimeReview
from advisor.schemas.state import GraphState

log = logging.getLogger(__name__)


def merge_regime_review(llm: RegimeReview, base: RegimeReview) -> RegimeReview:
    return llm.model_copy(
        update={
            "current_regime": base.current_regime,
            "state_vector": base.state_vector,
            "historical_outcome": base.historical_outcome,
        }
    )


def regime_node(state: GraphState) -> dict:
    t0 = time.monotonic()
    log.info("started")
    portfolio = state["portfolio"]
    md = state.get("market_data")
    report_step("regime", 0, "Preparing regime engine inputs…")
    report_step("regime", 1, "Running regime and analog engine…")
    base = compute_regime_review_base(portfolio, md)
    report_step("regime", 2, "Building regime interpretation prompt…")
    content = build_analysis_prompt(state)
    content = f"{regime_engine_to_text(base)}\n\n{content}"

    report_step("regime", 3, "Interpreting macro regime fit…")

    llm: RegimeReview = invoke_structured(  # type: ignore[assignment]
        RegimeReview,
        [SystemMessage(content=regime_system_prompt()), HumanMessage(content=content)],
        agent="regime",
        max_tokens=config.llm.structured_max_tokens,
        temperature=config.llm.structured_temperature,
        use_agent_model=True,
    )
    report_step("regime", 4, "Merging computed analogs with regime narrative…")
    result = merge_regime_review(llm, base)
    log.info("done in %.1fs", time.monotonic() - t0)
    return {"regime_review": result}
