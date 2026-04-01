"""Risk agent — parallel, runs after news agent."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from port.agents._base import build_analysis_prompt
from port.config import make_llm
from port.models import RiskReview
from port.prompts import RISK_SYSTEM_PROMPT

if TYPE_CHECKING:
    from port.state import GraphState

log = logging.getLogger(__name__)


def risk_node(state: GraphState) -> dict:
    t0 = time.monotonic()
    log.info("started")
    structured_llm = make_llm(max_tokens=4096).with_structured_output(RiskReview)
    result: RiskReview = structured_llm.invoke(  # type: ignore[assignment]
        [
            SystemMessage(content=RISK_SYSTEM_PROMPT),
            HumanMessage(content=build_analysis_prompt(state)),
        ]
    )
    log.info("done in %.1fs", time.monotonic() - t0)
    return {"risk_results": [result]}
