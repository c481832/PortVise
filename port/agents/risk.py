"""Risk agent — parallel, runs after news agent."""

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

if TYPE_CHECKING:
    from port.state import GraphState

log = logging.getLogger(__name__)


def risk_node(state: GraphState) -> dict:
    t0 = time.monotonic()
    log.info("started")
    content = build_analysis_prompt(state, curated_for="risk")

    _cb = _step_cb.get(None)
    if _cb:
        _cb("risk", 0, "Analysing portfolio risk…")

    result: RiskReview = invoke_structured(  # type: ignore[assignment]
        RiskReview,
        [SystemMessage(content=RISK_SYSTEM_PROMPT), HumanMessage(content=content)],
        agent="risk",
    )
    log.info("done in %.1fs", time.monotonic() - t0)
    return {"risk_results": [result]}
