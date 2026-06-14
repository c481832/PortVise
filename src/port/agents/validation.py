"""Validation agent — deterministic upstream input completeness gate."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from port.config import config
from port.config import step_callback as _step_cb
from port.models import ValidationReview

if TYPE_CHECKING:
    from port.state import GraphState

log = logging.getLogger(__name__)


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

    inherited_count = len(state.get("inherited_feedback") or [])
    summary = "Completeness check passed: news, risk, regime, and theme outputs are present."
    if inherited_count:
        summary += f" The run also carries {inherited_count} user feedback item(s) into Manager."
    result = ValidationReview(
        critical_issues=[],
        thesis_breaks=[],
        internal_contradictions=[],
        summary=summary,
    )
    log.info("done in %.1fs", time.monotonic() - t0)
    return {
        "validation_review": result,
        "validation_needs_more": False,
        "validation_missing_inputs": [],
        "validation_request_note": None,
        "validation_retry_count": 0,
    }
