"""Validation agent — fan-in, synthesises all four upstream reports."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from port.config import config, invoke_structured
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
    risk_reviews: list[RiskReview],
    regime_reviews: list[RegimeReview],
    theme_reviews: list[ThemeReview],
) -> str:
    risk_blocks = [
        f"--- RISK REPORT #{i + 1} ---\n{render_risk(r)}" for i, r in enumerate(risk_reviews)
    ]
    regime_blocks = [
        f"--- REGIME REPORT #{i + 1} ---\n{render_regime(r)}" for i, r in enumerate(regime_reviews)
    ]
    theme_blocks = [
        f"--- THEME REPORT #{i + 1} ---\n{render_theme(t)}" for i, t in enumerate(theme_reviews)
    ]
    return "\n\n".join(
        [
            f"ORIGINAL PORTFOLIO:\n{portfolio_to_text(portfolio)}",
            news_to_text(news),
            f"RISK REVIEWS PROVIDED: {len(risk_reviews)}",
            *risk_blocks,
            f"REGIME REVIEWS PROVIDED: {len(regime_reviews)}",
            *regime_blocks,
            f"THEME REVIEWS PROVIDED: {len(theme_reviews)}",
            *theme_blocks,
            "Synthesise the above into a ValidationReview."
            " Elevate disagreements and thesis breaks.",
        ]
    )


def _missing_validation_inputs(state: GraphState) -> list[str]:
    missing: list[str] = []
    if state.get("news_review") is None:
        missing.append("news_synthesis")
    if not state.get("risk_results"):
        missing.append("risk")
    if not state.get("regime_results"):
        missing.append("regime")
    if not state.get("theme_results"):
        missing.append("theme")
    return missing


def validation_node(state: GraphState) -> dict:
    t0 = time.monotonic()
    log.info("started")
    _cb = _step_cb.get(None)
    if _cb:
        _cb("validation", 0, "Checking upstream agent outputs…")
    missing = _missing_validation_inputs(state)
    if missing:
        retry_count = int(state.get("validation_retry_count", 0)) + 1
        note = (
            "Validation requested more upstream material: missing "
            + ", ".join(sorted(missing))
            + "."
        )
        if retry_count > config.validation.max_request_rounds:
            raise RuntimeError(
                note + " Validation exceeded retry budget; upstream nodes did not provide "
                "required outputs."
            )
        if _cb:
            _cb("validation", 0, "Missing inputs; requesting upstream refresh…")
        log.warning("%s retry=%d", note, retry_count)
        return {
            "validation_review": None,
            "validation_needs_more": True,
            "validation_missing_inputs": missing,
            "validation_request_note": note,
            "validation_retry_count": retry_count,
        }

    portfolio = state["portfolio"]
    news = state["news_review"]
    if news is None:
        raise RuntimeError("Validation missing news_synthesis after input check.")
    risk_reviews = list(state.get("risk_results", []))
    regime_reviews = list(state.get("regime_results", []))
    theme_reviews = list(state.get("theme_results", []))

    human_msg = build_validation_human_message(
        portfolio,
        news,
        risk_reviews,
        regime_reviews,
        theme_reviews,
    )

    if _cb:
        _cb("validation", 1, "Building validation brief…")
        _cb("validation", 2, "Cross-checking findings for conflicts…")

    result: ValidationReview = invoke_structured(  # type: ignore[assignment]
        ValidationReview,
        [SystemMessage(content=VALIDATION_SYSTEM_PROMPT), HumanMessage(content=human_msg)],
        agent="validation",
    )
    log.info("done in %.1fs", time.monotonic() - t0)
    return {
        "validation_review": result,
        "validation_needs_more": False,
        "validation_missing_inputs": [],
        "validation_request_note": None,
        "validation_retry_count": 0,
    }
