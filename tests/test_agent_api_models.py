from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from port.agent_api_models import AgentReviewRequest, AgentReviewResult
from port.models import ManagerReview


def _portfolio_payload() -> dict:
    return {
        "name": "Agent Test",
        "positions": [
            {
                "ticker": "AAPL",
                "name": "Apple",
                "weight": 0.1,
                "sector": "Technology",
                "entry_date": "2023-01-01",
                "entry_price": 150.0,
                "current_price": 180.0,
                "entry_thesis": "Services growth",
            }
        ],
        "cash_weight": 0.9,
        "review_date": "2026-04-29",
    }


def test_agent_review_request_validates_portfolio_and_defaults() -> None:
    req = AgentReviewRequest.model_validate({"portfolio": _portfolio_payload()})

    assert req.portfolio.name == "Agent Test"
    assert req.portfolio.positions[0].entry_date == date(2023, 1, 1)
    assert req.locale == "en"
    assert req.corporate_actions == "best_effort"
    assert req.timeout_seconds == 1800
    assert req.llm is None


def test_agent_review_request_rejects_invalid_corporate_action_mode() -> None:
    with pytest.raises(ValidationError):
        AgentReviewRequest.model_validate(
            {"portfolio": _portfolio_payload(), "corporate_actions": "sometimes"}
        )


def test_agent_review_result_serializes_nested_models() -> None:
    result = AgentReviewResult(
        review_id="review-1",
        status="done",
        started_at="2026-04-29T00:00:00+00:00",
        finished_at="2026-04-29T00:01:00+00:00",
        requested_locale="en",
        content_locale="en",
        manager_review=ManagerReview(executive_summary="Actionable summary"),
    )

    payload = result.model_dump(mode="json")

    assert payload["status"] == "done"
    assert payload["error"] is None
    assert payload["manager_review"]["executive_summary"] == "Actionable summary"


def test_agent_review_request_and_result_export_json_schema() -> None:
    request_schema = AgentReviewRequest.model_json_schema()
    result_schema = AgentReviewResult.model_json_schema()

    assert "portfolio" in request_schema["properties"]
    assert "manager_review" in result_schema["properties"]
