"""Manager agent — final action list from validation + specialist reports."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from port.config import invoke_structured
from port.config import step_callback as _step_cb
from port.models import ManagerReview
from port.portfolio import (
    news_to_text,
    portfolio_to_text,
    render_regime,
    render_risk,
    render_theme,
    render_validation,
)
from port.prompts import MANAGER_SYSTEM_PROMPT

if TYPE_CHECKING:
    from port.state import GraphState

log = logging.getLogger(__name__)


def build_manager_human_message(state: GraphState) -> str:
    portfolio = state["portfolio"]
    news = state["news_review"]
    risk = state["risk_results"][-1]
    regime = state["regime_results"][-1]
    theme = state["theme_results"][-1]
    validation = state["validation_review"]

    return "\n\n".join(
        [
            f"ORIGINAL PORTFOLIO:\n{portfolio_to_text(portfolio)}",
            news_to_text(news),
            render_risk(risk),
            render_regime(regime),
            render_theme(theme),
            render_validation(validation) if validation is not None else "",
            "Based on all of the above, generate a ManagerReview with concrete actions.",
        ]
    )


def manager_node(state: GraphState) -> dict:
    t0 = time.monotonic()
    log.info("started")
    human_msg = build_manager_human_message(state)

    _cb = _step_cb.get(None)
    if _cb:
        _cb("manager", 0, "Generating action plan…")

    result: ManagerReview = invoke_structured(  # type: ignore[assignment]
        ManagerReview,
        [SystemMessage(content=MANAGER_SYSTEM_PROMPT), HumanMessage(content=human_msg)],
        agent="manager",
    )
    log.info("done in %.1fs", time.monotonic() - t0)
    return {"manager_review": result}
