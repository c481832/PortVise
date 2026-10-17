from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from advisor.config import REPO_ROOT
from advisor.web.sessions import ReviewSession

REVIEW_STORE_DIR = REPO_ROOT / "data" / "reviews"
SAFE_REVIEW_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
ALLOCATION_SUMMARY_KEYS = (
    "allocated_capital",
    "min_allocated_capital",
    "cash_weight",
    "max_cash_weight",
    "required_deployment_pct",
    "deployment_required",
    "drawdown_budget_breached",
)
MAX_FEEDBACK_ITEMS = 20
PREVIEW_CHARS = 240


def review_path(review_id: str) -> Path:
    if not SAFE_REVIEW_ID_RE.fullmatch(review_id):
        raise ValueError(f"invalid review id: {review_id!r}")
    return REVIEW_STORE_DIR / f"{review_id}.json"


def review_result_payload(session: ReviewSession) -> dict[str, Any]:
    return {
        "review_id": session.review_id,
        "saved_at": datetime.now(UTC).isoformat(),
        "status": session.status,
        "portfolio_name": session.portfolio.name.strip(),
        "last_error": session.last_error_event,
        "agent_outputs": session.agent_outputs,
        "agent_output_updated_at": session.agent_output_updated_at,
        "final_state": session.final_state,
        "feedback_rounds": [],
        "inherited_feedback": session.inherited_feedback,
    }


def save_review_payload(payload: dict[str, Any]) -> None:
    REVIEW_STORE_DIR.mkdir(parents=True, exist_ok=True)
    path = review_path(payload["review_id"])
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, default=str), encoding="utf-8")
    tmp.replace(path)


def load_review_result(review_id: str) -> dict[str, Any] | None:
    path = review_path(review_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def done_review_payloads() -> Iterator[dict[str, Any]]:
    for path in REVIEW_STORE_DIR.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload["status"] == "done":
            yield payload


def review_summary(payload: dict[str, Any]) -> dict[str, Any]:
    agent_outputs = payload["agent_outputs"]
    manager = agent_outputs["manager"]["manager_review"]
    preview = manager.get("executive_summary") or manager.get("do_nothing_case") or ""
    summary = {
        "review_id": payload["review_id"],
        "status": payload["status"],
        "portfolio_name": payload["portfolio_name"],
        "saved_at": payload["saved_at"],
        "preview": preview.strip()[:PREVIEW_CHARS],
    }
    allocation = agent_outputs["allocation"].get("allocation_review")
    if allocation is not None:
        summary["allocation"] = {key: allocation.get(key) for key in ALLOCATION_SUMMARY_KEYS}
    return summary


def list_review_summaries(*, limit: int) -> list[dict[str, Any]]:
    summaries = [review_summary(payload) for payload in done_review_payloads()]
    summaries.sort(key=lambda summary: summary["saved_at"], reverse=True)
    return summaries[:limit]


def portfolio_fingerprint(portfolio: dict[str, Any]) -> tuple[tuple[str, ...], str, str]:
    tickers = {(position["ticker"] or "").strip().upper() for position in portfolio["positions"]}
    tickers.discard("")
    return (
        tuple(sorted(tickers)),
        (portfolio["benchmark"] or "").strip().upper(),
        (portfolio["base_currency"] or "").strip().upper(),
    )


def latest_matching_feedback(portfolio: dict[str, Any]) -> dict[str, Any] | None:
    target = portfolio_fingerprint(portfolio)
    if not target[0]:
        return None
    matches: list[dict[str, Any]] = []
    for payload in done_review_payloads():
        if portfolio_fingerprint(payload["final_state"]["portfolio"]) != target:
            continue
        items = [
            {
                "source_review_id": payload["review_id"],
                "round_id": round_["round_id"],
                "comment": round_["user_comment"].strip(),
                "submitted_at": round_["submitted_at"],
            }
            for round_ in payload["feedback_rounds"]
            if round_["user_comment"].strip()
        ]
        if not items:
            continue
        items.sort(key=lambda item: item["submitted_at"], reverse=True)
        matches.append(
            {
                "source_review_id": payload["review_id"],
                "portfolio_name": payload["portfolio_name"],
                "saved_at": payload["saved_at"],
                "items": items[:MAX_FEEDBACK_ITEMS],
            }
        )
    return max(matches, key=lambda match: match["saved_at"], default=None)
