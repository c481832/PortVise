"""Validation agent — fan-in, synthesises all four upstream reports."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from port.config import invoke_structured
from port.config import step_callback as _step_cb
from port.models import (
    NewsReview,
    RegimeReview,
    RiskReview,
    ThemeReview,
    ValidationReview,
)
from port.portfolio import news_to_text, portfolio_to_text, render_regime, render_risk, render_theme
from port.prompts import VALIDATION_SYSTEM_PROMPT

if TYPE_CHECKING:
    from port.state import GraphState

log = logging.getLogger(__name__)


def build_validation_human_message(
    portfolio,
    news: NewsReview,
    risk: RiskReview,
    regime: RegimeReview,
    theme: ThemeReview,
) -> str:
    return "\n\n".join(
        [
            f"ORIGINAL PORTFOLIO:\n{portfolio_to_text(portfolio)}",
            news_to_text(news),
            render_risk(risk),
            render_regime(regime),
            render_theme(theme),
            "Synthesise the above into a ValidationReview."
            " Elevate disagreements and thesis breaks.",
        ]
    )


def validation_node(state: GraphState) -> dict:
    t0 = time.monotonic()
    log.info("started")
    portfolio = state["portfolio"]
    news = state["news_review"]
    risk = state["risk_results"][0]
    regime = state["regime_results"][0]
    theme = state["theme_results"][0]

    human_msg = build_validation_human_message(portfolio, news, risk, regime, theme)  # type: ignore[arg-type]

    _cb = _step_cb.get(None)
    if _cb:
        _cb("validation", 0, "Cross-checking findings…")

    result: ValidationReview = invoke_structured(  # type: ignore[assignment]
        ValidationReview,
        [SystemMessage(content=VALIDATION_SYSTEM_PROMPT), HumanMessage(content=human_msg)],
        agent="validation",
    )
    log.info("done in %.1fs", time.monotonic() - t0)
    return {"validation_review": result}
