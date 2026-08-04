"""Small JSON-backed storage for completed web reviews.

The live ``ReviewSession`` objects are intentionally short-lived. This module stores the
result payload needed to reopen a finished review without keeping its graph, event log,
and task objects in memory.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from port.config import REPO_ROOT
from port.web.sessions import ReviewSession

REVIEW_STORE_DIR = REPO_ROOT / "data" / "reviews"
_SAFE_REVIEW_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _review_path(review_id: str) -> Path:
    if not _SAFE_REVIEW_ID_RE.fullmatch(review_id):
        raise ValueError(f"invalid review id: {review_id!r}")
    return REVIEW_STORE_DIR / f"{review_id}.json"


def _manager_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    final_state = payload.get("final_state")
    agent_outputs = payload.get("agent_outputs")
    manager_output = agent_outputs.get("manager") if isinstance(agent_outputs, dict) else {}
    if not isinstance(manager_output, dict):
        manager_output = {}
    if isinstance(final_state, dict) and isinstance(final_state.get("manager_review"), dict):
        return final_state["manager_review"]
    for key in ("manager_review", "planner_review"):
        value = manager_output.get(key)
        if isinstance(value, dict):
            return value
    return manager_output if isinstance(manager_output, dict) else {}


def _allocation_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    final_state = payload.get("final_state")
    agent_outputs = payload.get("agent_outputs")
    candidates: list[Any] = []
    if isinstance(final_state, dict):
        candidates.append(final_state.get("allocation_results"))
        candidates.append(final_state.get("allocation_review"))
    if isinstance(agent_outputs, dict):
        allocation_output = agent_outputs.get("allocation")
        if isinstance(allocation_output, dict):
            candidates.append(allocation_output.get("allocation_results"))
            candidates.append(allocation_output.get("allocation_review"))
            candidates.append(allocation_output)
    for candidate in candidates:
        if isinstance(candidate, list) and candidate:
            candidate = candidate[-1]
        if isinstance(candidate, dict) and "cash_weight" in candidate:
            keys = (
                "allocated_capital",
                "min_allocated_capital",
                "cash_weight",
                "max_cash_weight",
                "allocation_status",
                "required_deployment_pct",
                "deployment_required",
                "drawdown_budget_breached",
            )
            return {key: candidate.get(key) for key in keys}
    return None


def _portfolio_name(session: ReviewSession) -> str:
    return str(getattr(session.portfolio, "name", "") or "").strip()


def review_result_payload(session: ReviewSession, *, saved_at: str | None = None) -> dict[str, Any]:
    return {
        "review_id": session.review_id,
        "saved_at": saved_at or datetime.now(UTC).isoformat(),
        "status": session.status,
        "portfolio_name": _portfolio_name(session),
        "requested_locale": session.locale_state.requested_locale,
        "content_locale": session.locale_state.content_locale,
        "translation_fallback_used": session.locale_state.translation_fallback_used,
        "last_error": session.last_error_event,
        "agent_outputs": session.agent_outputs,
        "agent_output_updated_at": session.agent_output_updated_at,
        "final_state": session.final_state,
        "feedback_rounds": [],
        "inherited_feedback": session.inherited_feedback,
    }


def review_summary_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    manager = _manager_from_payload(payload)
    allocation = _allocation_from_payload(payload)
    preview = ""
    if isinstance(manager, dict):
        preview = str(
            manager.get("executive_summary")
            or manager.get("do_nothing_case")
            or ""
        ).strip()
    summary = {
        "review_id": payload.get("review_id", ""),
        "status": payload.get("status", ""),
        "portfolio_name": payload.get("portfolio_name", ""),
        "saved_at": payload.get("saved_at", ""),
        "requested_locale": payload.get("requested_locale", ""),
        "content_locale": payload.get("content_locale", ""),
        "translation_fallback_used": bool(payload.get("translation_fallback_used")),
        "preview": preview[:240],
    }
    if allocation is not None:
        summary["allocation"] = allocation
    return summary


def save_review_result(session: ReviewSession) -> dict[str, Any]:
    payload = review_result_payload(session)
    return save_review_payload(payload)


def save_review_payload(payload: dict[str, Any]) -> dict[str, Any]:
    review_id = str(payload.get("review_id") or "")
    REVIEW_STORE_DIR.mkdir(parents=True, exist_ok=True)
    path = _review_path(review_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, default=str), encoding="utf-8")
    tmp.replace(path)
    return payload


def load_review_result(review_id: str) -> dict[str, Any] | None:
    path = _review_path(review_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def list_review_summaries(*, limit: int = 30) -> list[dict[str, Any]]:
    if not REVIEW_STORE_DIR.exists():
        return []
    summaries: list[dict[str, Any]] = []
    for path in REVIEW_STORE_DIR.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("status") != "done":
            continue
        summaries.append(review_summary_from_payload(payload))
    summaries.sort(key=lambda item: str(item.get("saved_at") or ""), reverse=True)
    return summaries[:limit]


def _portfolio_fingerprint(portfolio: dict[str, Any]) -> tuple[tuple[str, ...], str, str]:
    positions = portfolio.get("positions")
    tickers = sorted(
        {
            str(position.get("ticker") or "").strip().upper()
            for position in positions
            if isinstance(position, dict) and str(position.get("ticker") or "").strip()
        }
    ) if isinstance(positions, list) else []
    return (
        tuple(tickers),
        str(portfolio.get("benchmark") or "").strip().upper(),
        str(portfolio.get("base_currency") or "").strip().upper(),
    )


def latest_matching_feedback(portfolio: dict[str, Any]) -> dict[str, Any] | None:
    if not REVIEW_STORE_DIR.exists():
        return None
    target = _portfolio_fingerprint(portfolio)
    if not target[0]:
        return None
    matches: list[dict[str, Any]] = []
    for path in REVIEW_STORE_DIR.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        final_state = payload.get("final_state")
        stored_portfolio = final_state.get("portfolio") if isinstance(final_state, dict) else None
        rounds = payload.get("feedback_rounds")
        if (
            payload.get("status") != "done"
            or not isinstance(stored_portfolio, dict)
            or _portfolio_fingerprint(stored_portfolio) != target
            or not isinstance(rounds, list)
        ):
            continue
        items = [
            {
                "source_review_id": str(payload.get("review_id") or ""),
                "round_id": str(round_.get("round_id") or ""),
                "comment": str(round_.get("user_comment") or "").strip(),
                "submitted_at": round_.get("submitted_at"),
            }
            for round_ in rounds
            if isinstance(round_, dict) and str(round_.get("user_comment") or "").strip()
        ]
        items.sort(key=lambda item: str(item.get("submitted_at") or ""), reverse=True)
        items = items[:20]
        if not items:
            continue
        matches.append(
            {
                "source_review_id": payload.get("review_id", ""),
                "portfolio_name": payload.get("portfolio_name", ""),
                "saved_at": payload.get("saved_at", ""),
                "items": items,
            }
        )
    matches.sort(key=lambda item: str(item.get("saved_at") or ""), reverse=True)
    return matches[0] if matches else None
