"""Tests for FastAPI server endpoints in port/server.py."""

from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from port.config import StructuredLLMOutputError
from port.models import AgentTaskSummary, PositionSnapshot, TickerProfile
from port.server import ReviewSession, _graph_agent_for_chain_event, _reviews, app
from port.web import review_store
from port.web.review_store import save_review_result
from port.web.sessions import _review_error_event


@pytest.fixture(autouse=True)
def clear_reviews():
    """Isolate _reviews dict between tests."""
    _reviews.clear()
    yield
    _reviews.clear()


@pytest.fixture
def portfolio_payload():
    return {
        "name": "Test",
        "positions": [
            {
                "ticker": "AAPL",
                "name": "Apple",
                "weight": 0.10,
                "quantity": 10,
                "sector": "Technology",
                "entry_date": "2023-01-01",
                "entry_price": 150.0,
                "current_price": 180.0,
                "dividend": 0.0,
                "split": 1.0,
                "entry_thesis": "Strong ecosystem",
                "asset_class": "equity",
                "country": "US",
                "tags": ["quality"],
            }
        ],
        "cash_weight": 0.90,
        "base_currency": "USD",
        "benchmark": "SPY",
        "review_date": "2026-01-01",
        "context_note": "",
    }


@pytest.fixture
def mock_session(example_portfolio):
    with patch("port.web.sessions.build_graph"):
        session = ReviewSession("test-review-id", example_portfolio)
    return session


async def test_start_review_success(portfolio_payload):
    with (
        patch("port.web.sessions.build_graph"),
        patch("port.web.routes.fetch_corporate_actions", return_value=(7.5, 2.0)),
        patch.object(ReviewSession, "start"),
        patch("port.web.routes.clear_port_log_files") as clear_logs,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/review/start",
                json={"portfolio": portfolio_payload, "locale": "zh-Hans-CN"},
            )
    assert resp.status_code == 200
    review_id = resp.json()["review_id"]
    position = _reviews[review_id].portfolio.positions[0]
    assert position.dividend == 7.5
    assert position.split == 2.0
    clear_logs.assert_called_once_with()


async def test_start_review_preserves_inherited_feedback(portfolio_payload):
    inherited = {
        "source_review_id": "source-review",
        "round_id": "round-1",
        "comment": "Keep the strategic horizon in view.",
        "submitted_at": "2026-06-05T12:00:00+00:00",
    }
    with (
        patch("port.web.sessions.build_graph"),
        patch("port.web.routes.fetch_corporate_actions", return_value=(0.0, 1.0)),
        patch.object(ReviewSession, "start"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/review/start",
                json={"portfolio": portfolio_payload, "inherited_feedback": [inherited]},
            )

    assert resp.status_code == 200
    review_id = resp.json()["review_id"]
    assert _reviews[review_id].inherited_feedback == [inherited]


async def test_feedback_candidates_returns_latest_exact_portfolio_match(
    mock_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(review_store, "REVIEW_STORE_DIR", tmp_path)
    mock_session.status = "done"
    mock_session.final_state = {
        "portfolio": mock_session.portfolio.model_dump(mode="json"),
        "manager_review": None,
    }
    payload = save_review_result(mock_session)
    payload["feedback_rounds"] = [
        {
            "round_id": f"round-{index:02d}",
            "submitted_at": f"2026-06-{index + 1:02d}T12:00:00+00:00",
            "user_comment": f"Feedback item {index:02d}",
            "status": "done",
        }
        for index in range(25)
    ]
    review_store.save_review_payload(payload)
    _reviews.clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/reviews/feedback-candidates",
            json={"portfolio": mock_session.portfolio.model_dump(mode="json")},
        )

    assert resp.status_code == 200
    match = resp.json()["match"]
    assert match["source_review_id"] == "test-review-id"
    assert len(match["items"]) == 20
    assert match["items"][0]["round_id"] == "round-24"
    assert match["items"][0]["comment"] == "Feedback item 24"
    assert match["items"][-1]["round_id"] == "round-05"


async def test_track_record_endpoint_returns_computed_review():
    from port.models import PastCallOutcome, PastPerformanceReview

    review = PastPerformanceReview(
        review_id="rid",
        review_date="2026-01-01",
        benchmark="SPY",
        min_comparison_days=5,
        matured_count=1,
        validated_count=1,
        outcomes=[
            PastCallOutcome(
                position="AAPL",
                action_type="reduce",
                days_elapsed=12,
                daily_outperf_pct=-0.18,
                verdict="validated",
            )
        ],
    )
    with (
        patch("port.web.routes.load_review_result", return_value={"status": "done"}),
        patch("port.web.routes.compute_track_record", return_value=review) as compute,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/review/rid/track-record")

    assert resp.status_code == 200
    body = resp.json()
    assert body["validated_count"] == 1
    assert body["outcomes"][0]["position"] == "AAPL"
    assert body["outcomes"][0]["verdict"] == "validated"
    compute.assert_called_once()


async def test_track_record_endpoint_404_when_missing():
    with patch("port.web.routes.load_review_result", return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/review/nope/track-record")
    assert resp.status_code == 404


async def test_track_record_endpoint_409_when_not_done():
    with patch("port.web.routes.load_review_result", return_value={"status": "running"}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/review/rid/track-record")
    assert resp.status_code == 409


def test_structured_llm_error_event_is_user_facing() -> None:
    exc = StructuredLLMOutputError(agent="theme", schema_name="ThemeReview")

    event = _review_error_event(exc)

    assert event["type"] == "error"
    assert event["agent"] == "theme"
    assert "Theme agent returned malformed structured output" in event["message"]
    assert "Invalid json output" not in event["message"]


async def test_start_review_preserves_supplied_corporate_actions(portfolio_payload):
    portfolio_payload["positions"][0]["dividend"] = 3.0
    portfolio_payload["positions"][0]["split"] = 4.0
    with (
        patch("port.web.sessions.build_graph"),
        patch("port.web.routes.fetch_corporate_actions") as fetch_actions,
        patch.object(ReviewSession, "start"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/review/start", json={"portfolio": portfolio_payload})

    assert resp.status_code == 200
    fetch_actions.assert_not_called()
    review_id = resp.json()["review_id"]
    position = _reviews[review_id].portfolio.positions[0]
    assert position.dividend == 3.0
    assert position.split == 4.0


async def test_start_review_enriches_default_corporate_actions(portfolio_payload):
    portfolio_payload["positions"][0]["dividend"] = 0.0
    portfolio_payload["positions"][0]["split"] = 1.0
    with (
        patch("port.web.sessions.build_graph"),
        patch("port.web.routes.fetch_corporate_actions", return_value=(2.0, 3.0)) as fetch_actions,
        patch.object(ReviewSession, "start"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/review/start", json={"portfolio": portfolio_payload})

    assert resp.status_code == 200
    fetch_actions.assert_called_once()
    assert fetch_actions.call_args.kwargs["timeout"] == 8.0
    review_id = resp.json()["review_id"]
    position = _reviews[review_id].portfolio.positions[0]
    assert position.dividend == 2.0
    assert position.split == 3.0


async def test_start_review_invalid_portfolio():
    with patch("port.web.sessions.build_graph"), patch.object(ReviewSession, "start"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/review/start", json={"portfolio": {}})
    assert resp.status_code == 422


async def test_config_api_exposes_and_updates_capital_allocation_policy():
    with patch("port.web.routes.write_ui_overrides") as write_overrides:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            get_response = await client.get("/api/config")
            post_response = await client.post(
                "/api/config",
                json={
                    "min_allocated_capital": 0.75,
                    "max_drawdown": 0.4,
                    "cash_yield_annual_pct": 3.25,
                },
            )

    assert get_response.status_code == 200
    assert get_response.json()["min_allocated_capital"] == 0.8
    assert get_response.json()["max_cash_weight"] == pytest.approx(0.2)
    assert post_response.status_code == 200
    assert write_overrides.call_args.kwargs["min_allocated_capital"] == 0.75
    assert write_overrides.call_args.kwargs["max_drawdown"] == 0.4
    assert write_overrides.call_args.kwargs["cash_yield_annual_pct"] == 3.25


async def test_config_test_endpoint_sends_test_message():
    class FakeHttpClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            assert url == "http://llm.test/v1/chat/completions"
            assert headers == {
                "Authorization": "Bearer test-key",
                "Content-Type": "application/json",
            }
            assert json is not None
            assert json["model"] == "model-a"
            assert json["messages"] == [{"role": "user", "content": "Reply with exactly: ok"}]
            return httpx.Response(
                200,
                json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
            )

    with patch("port.web.routes.httpx.AsyncClient", FakeHttpClient):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/config/test",
                json={
                    "llm_base_url": "http://llm.test/v1",
                    "llm_model": "model-a",
                    "llm_api_key": "test-key",
                },
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["message"] == "Endpoint reachable."
    assert body["model"] == "model-a"


async def test_config_test_endpoint_uses_model_name_as_api_model():
    class FakeHttpClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            assert url == "http://llm.test/v1/chat/completions"
            assert json is not None
            assert json["model"] == "deepseek"
            return httpx.Response(
                200,
                json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
            )

    with patch("port.web.routes.httpx.AsyncClient", FakeHttpClient):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/config/test",
                json={"llm_base_url": "http://llm.test/v1", "llm_model": "deepseek"},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["model"] == "deepseek"


async def test_config_test_endpoint_rejects_url_without_scheme():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/config/test",
            json={"llm_base_url": "llm.test/v1", "llm_model": "model-a"},
        )
    assert resp.status_code == 400
    assert "http://" in resp.json()["detail"]


async def test_get_result_done(mock_session):
    mock_session.status = "done"
    mock_session.final_state = {"summary": "complete"}
    mock_session.agent_outputs = {
        "risk": {"risk_review": {"marginal_risk_by_ticker": {"AAPL": 0.1}}}
    }
    mock_session.agent_output_updated_at = {"risk": "2026-04-23T00:00:00+00:00"}
    mock_session.locale_state.requested_locale = "zh-CN"
    mock_session.locale_state.content_locale = "zh-CN"
    mock_session.locale_state.translation_fallback_used = True
    _reviews["test-review-id"] = mock_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/review/test-review-id/result")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "done"
    assert data["final_state"] == {"summary": "complete"}
    assert data["agent_outputs"] == {
        "risk": {"risk_review": {"marginal_risk_by_ticker": {"AAPL": 0.1}}}
    }
    assert data["agent_output_updated_at"] == {"risk": "2026-04-23T00:00:00+00:00"}
    assert data["requested_locale"] == "zh-CN"
    assert data["content_locale"] == "zh-CN"
    assert data["translation_fallback_used"] is True


async def test_get_result_loads_persisted_review_after_live_session_evicted(
    mock_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(review_store, "REVIEW_STORE_DIR", tmp_path)
    mock_session.status = "done"
    mock_session.final_state = {
        "manager_review": {"executive_summary": "Persisted summary"},
        "validation_review": {"summary": "Validated"},
    }
    mock_session.agent_outputs = {
        "manager": {"manager_review": {"executive_summary": "Persisted summary"}}
    }
    save_review_result(mock_session)
    _reviews.clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/review/test-review-id/result")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "done"
    assert data["review_id"] == "test-review-id"
    assert data["final_state"]["manager_review"]["executive_summary"] == "Persisted summary"


async def test_review_summaries_are_lightweight_and_do_not_require_live_session(
    mock_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(review_store, "REVIEW_STORE_DIR", tmp_path)
    mock_session.status = "done"
    mock_session.final_state = {
        "manager_review": {
            "executive_summary": "This is the compact history preview.",
            "do_nothing_case": "Fallback preview.",
        }
    }
    mock_session.agent_outputs = {
        "manager": {
            "manager_review": {
                "executive_summary": "This is the compact history preview.",
                "actions": [{"position": "AAPL"}],
            }
        },
        "risk": {"large": "payload"},
    }
    save_review_result(mock_session)
    _reviews.clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/reviews")

    assert resp.status_code == 200
    reviews = resp.json()["reviews"]
    assert reviews == [
        {
            "review_id": "test-review-id",
            "status": "done",
            "portfolio_name": "Test Portfolio",
            "saved_at": reviews[0]["saved_at"],
            "requested_locale": "en",
            "content_locale": "en",
            "translation_fallback_used": False,
            "preview": "This is the compact history preview.",
        }
    ]
    assert "agent_outputs" not in reviews[0]


def test_review_summary_includes_compact_allocation_policy(example_allocation) -> None:
    allocation = example_allocation.model_dump(mode="json")
    summary = review_store.review_summary_from_payload(
        {
            "review_id": "allocation-review",
            "status": "done",
            "final_state": {"allocation_results": [allocation]},
        }
    )

    assert summary["allocation"] == {
        "allocated_capital": 0.15,
        "min_allocated_capital": 0.8,
        "cash_weight": 0.85,
        "max_cash_weight": 0.2,
        "allocation_status": "below minimum",
        "required_deployment_pct": 0.65,
        "deployment_required": True,
        "drawdown_budget_breached": False,
    }
    assert "agent_outputs" not in summary


async def test_review_feedback_reruns_manager_and_persists_round(
    mock_session,
    tmp_path,
    monkeypatch,
    example_portfolio,
    example_news,
    example_risk,
    example_regime,
    example_theme,
    example_validation,
    example_allocation,
    example_manager_review,
):
    monkeypatch.setattr(review_store, "REVIEW_STORE_DIR", tmp_path)
    mock_session.status = "done"
    mock_session.final_state = {
        "portfolio": example_portfolio.model_dump(mode="json"),
        "requested_locale": "en",
        "news_focus": None,
        "market_data": None,
        "news_research_text": None,
        "news_research_query_count": None,
        "news_review": example_news.model_dump(mode="json"),
        "risk_results": [example_risk.model_dump(mode="json")],
        "regime_results": [example_regime.model_dump(mode="json")],
        "theme_results": [example_theme.model_dump(mode="json")],
        "allocation_results": [example_allocation.model_dump(mode="json")],
        "validation_review": example_validation.model_dump(mode="json"),
        "validation_needs_more": False,
        "validation_missing_inputs": [],
        "validation_request_note": None,
        "validation_retry_count": 0,
        "manager_review": example_manager_review.model_dump(mode="json"),
    }
    mock_session.agent_outputs = {
        "manager": {"manager_review": example_manager_review.model_dump(mode="json")}
    }
    save_review_result(mock_session)
    _reviews.clear()

    updated_manager = example_manager_review.model_copy(
        update={"executive_summary": "Revised after feedback."}
    )
    with patch("port.web.routes.run_manager_review", return_value=updated_manager) as rerun:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/review/test-review-id/feedback",
                json={"comment": "Focus more on AAPL upside."},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["final_state"]["manager_review"]["executive_summary"] == "Revised after feedback."
    assert data["agent_outputs"]["manager"]["manager_review"]["executive_summary"] == (
        "Revised after feedback."
    )
    assert data["feedback_rounds"][0]["status"] == "done"
    assert data["feedback_rounds"][0]["user_comment"] == "Focus more on AAPL upside."
    assert data["feedback_rounds"][0]["manager_review"]["executive_summary"] == (
        "Revised after feedback."
    )
    rerun.assert_called_once()

    stored = review_store.load_review_result("test-review-id")
    assert stored is not None
    assert stored["feedback_rounds"][0]["user_comment"] == "Focus more on AAPL upside."


async def test_review_feedback_allows_missing_prior_manager_review(
    mock_session,
    tmp_path,
    monkeypatch,
    example_portfolio,
    example_news,
    example_risk,
    example_regime,
    example_theme,
    example_validation,
    example_allocation,
    example_manager_review,
):
    monkeypatch.setattr(review_store, "REVIEW_STORE_DIR", tmp_path)
    mock_session.status = "done"
    mock_session.final_state = {
        "portfolio": example_portfolio.model_dump(mode="json"),
        "requested_locale": "en",
        "news_focus": None,
        "market_data": None,
        "news_research_text": None,
        "news_research_query_count": None,
        "news_review": example_news.model_dump(mode="json"),
        "risk_results": [example_risk.model_dump(mode="json")],
        "regime_results": [example_regime.model_dump(mode="json")],
        "theme_results": [example_theme.model_dump(mode="json")],
        "allocation_results": [example_allocation.model_dump(mode="json")],
        "validation_review": example_validation.model_dump(mode="json"),
        "validation_needs_more": False,
        "validation_missing_inputs": [],
        "validation_request_note": None,
        "validation_retry_count": 0,
        "manager_review": None,
    }
    mock_session.agent_outputs = {}
    save_review_result(mock_session)
    _reviews.clear()

    with patch("port.web.routes.run_manager_review", return_value=example_manager_review):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/review/test-review-id/feedback",
                json={"comment": "Please revisit the final action plan."},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["feedback_rounds"][0]["status"] == "done"
    assert data["final_state"]["manager_review"]["executive_summary"] == (
        example_manager_review.executive_summary
    )


async def test_review_feedback_rejects_empty_comment(mock_session):
    _reviews["test-review-id"] = mock_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/review/test-review-id/feedback", json={"comment": "  "})

    assert resp.status_code == 400


async def test_get_snapshot_found(mock_session):
    mock_session.status = "running"
    mock_session.agent_outputs = {"planner": {"news_focus": {"portfolio_goal": "Goal"}}}
    mock_session.agent_output_updated_at = {"planner": "2026-04-23T00:00:00+00:00"}
    mock_session.locale_state.requested_locale = "en"
    mock_session.locale_state.content_locale = "en"
    _reviews["test-review-id"] = mock_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/review/test-review-id/snapshot")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["agent_outputs"] == {"planner": {"news_focus": {"portfolio_goal": "Goal"}}}
    assert data["agent_output_updated_at"] == {"planner": "2026-04-23T00:00:00+00:00"}
    assert data["requested_locale"] == "en"
    assert data["content_locale"] == "en"
    assert data["last_error"] is None


async def test_get_snapshot_includes_last_error(mock_session):
    mock_session.status = "error"
    mock_session.last_error_event = {
        "type": "error",
        "agent": "theme",
        "message": "Theme agent returned malformed structured output",
        "ts": "2026-04-23T00:00:00+00:00",
    }
    _reviews["test-review-id"] = mock_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/review/test-review-id/snapshot")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert data["last_error"]["agent"] == "theme"
    assert data["last_error"]["message"] == "Theme agent returned malformed structured output"


async def test_get_snapshot_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/review/nonexistent-id/snapshot")
    assert resp.status_code == 404


async def test_start_review_normalizes_locale(portfolio_payload):
    with (
        patch("port.web.sessions.build_graph"),
        patch("port.web.routes.fetch_corporate_actions", return_value=(0.0, 1.0)),
        patch.object(ReviewSession, "start"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/review/start",
                json={"portfolio": portfolio_payload, "locale": "zh-Hans-CN"},
            )
    review_id = resp.json()["review_id"]
    assert _reviews[review_id].locale_state.requested_locale == "zh-CN"


async def test_get_result_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/review/nonexistent-id/result")

    assert resp.status_code == 404


async def test_stream_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/review/nonexistent-id/stream")

    assert resp.status_code == 404


async def test_market_quote_not_found():
    with patch("port.web.routes.fetch_position_snapshot", return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/market/quote/AAPL?actions_start=2023-01-01")

    assert resp.status_code == 404


async def test_market_quote_passes_actions_start():
    snap = PositionSnapshot(
        ticker="AAPL",
        current_price=180.0,
        prev_close=179.0,
        change_1d_pct=0.56,
        change_1w_pct=1.0,
        change_1m_pct=2.0,
        change_1y_pct=10.0,
        change_3m_pct=4.0,
        week_52_high=190.0,
        week_52_low=140.0,
        pct_from_52w_high=-5.26,
        dividend=2.5,
        split=2.0,
    )
    with patch("port.web.routes.fetch_position_snapshot", return_value=snap) as fetch_snapshot:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/market/quote/AAPL?actions_start=2023-01-01")

    assert resp.status_code == 200
    assert resp.json()["dividend"] == 2.5
    assert resp.json()["split"] == 2.0
    fetch_snapshot.assert_called_once_with("AAPL", date(2023, 1, 1))


async def test_market_quote_requires_actions_start():
    with patch("port.web.routes.fetch_position_snapshot") as fetch_snapshot:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/market/quote/AAPL")

    assert resp.status_code == 400
    assert resp.json()["detail"] == "actions_start is required"
    fetch_snapshot.assert_not_called()


async def test_market_quote_invalid_ticker():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/market/quote/!!!invalid")
    assert resp.status_code == 400


async def test_market_profile_returns_name_sector():
    profile = TickerProfile(
        ticker="AAPL",
        name="Apple Inc.",
        sector="Technology",
        industry="Consumer Electronics",
    )
    with patch("port.web.routes.fetch_ticker_profile", return_value=profile) as fetch_profile:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/market/profile/aapl")

    assert resp.status_code == 200
    assert resp.json() == {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
    }
    fetch_profile.assert_called_once_with("AAPL")


async def test_market_profile_invalid_ticker():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/market/profile/!!!invalid")
    assert resp.status_code == 400


async def test_market_profile_not_found():
    with patch("port.web.routes.fetch_ticker_profile", side_effect=RuntimeError("missing")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/market/profile/UNKNOWN")
    assert resp.status_code == 404


def test_graph_agent_for_chain_event_accepts_matching_langgraph_node() -> None:
    assert (
        _graph_agent_for_chain_event(
            {"name": "risk", "metadata": {"langgraph_node": "risk", "thread_id": "t"}}
        )
        == "risk"
    )


def test_graph_agent_for_chain_event_rejects_name_node_mismatch() -> None:
    """Ignore nested chains whose ``name`` collides with a graph slot."""
    assert (
        _graph_agent_for_chain_event(
            {"name": "risk", "metadata": {"langgraph_node": "news", "thread_id": "t"}}
        )
        is None
    )


def test_graph_agent_for_chain_event_unknown_name() -> None:
    assert _graph_agent_for_chain_event({"name": "ChatOpenAI", "metadata": {}}) is None


async def test_agent_done_emits_agent_summary(mock_session):
    with patch(
        "port.web.sessions.summarize_agent_output",
        return_value=AgentTaskSummary(
            title="Risk complete",
            summary="Risk review found concentration pressure.",
            bullets=["Top risk is mega-cap concentration."],
        ),
    ):
        await mock_session._handle_event(
            {
                "event": "on_chain_end",
                "name": "risk",
                "metadata": {"langgraph_node": "risk"},
                "data": {"output": {"risk_review": {"summary": "Risk review"}}},
            }
        )
        await mock_session._wait_for_agent_summaries()

    event_types = [event["type"] for event in mock_session._events if isinstance(event, dict)]
    assert event_types == ["agent_done", "agent_summary"]
    summary_event = mock_session._events[-1]
    assert summary_event["agent"] == "risk"
    assert summary_event["title"] == "Risk complete"
    assert summary_event["bullets"] == ["Top risk is mega-cap concentration."]


async def test_heartbeat_is_delivered_without_replay_buffer_growth(mock_session):
    subscription = mock_session.subscribe()
    next_event = asyncio.create_task(anext(subscription))
    await asyncio.sleep(0)

    await mock_session._emit(
        {"type": "heartbeat", "ts": "2026-04-23T00:00:00+00:00"},
        persist=False,
    )

    event = await asyncio.wait_for(next_event, timeout=1)
    assert event["type"] == "heartbeat"
    assert mock_session._events == []
    await subscription.aclose()


async def test_terminal_callback_compacts_replay_buffer(mock_session):
    mock_session._on_terminal = lambda _session: None
    await mock_session._emit(
        {
            "type": "agent_done",
            "agent": "risk",
            "output": {"large": "payload"},
            "ts": "2026-04-23T00:00:00+00:00",
        }
    )
    await mock_session._close_stream()

    await mock_session._notify_terminal()

    assert mock_session._events == [None]


async def test_manager_summary_emits_before_stream_closes(mock_session):
    mock_session.graph.aget_state = AsyncMock(return_value=type("State", (), {"values": {}})())
    with patch(
        "port.web.sessions.summarize_agent_output",
        return_value=AgentTaskSummary(
            title="Manager complete",
            summary="Final action plan is ready.",
            bullets=["Review the decision memo."],
        ),
    ):
        await mock_session._handle_event(
            {
                "event": "on_chain_end",
                "name": "manager",
                "metadata": {"langgraph_node": "manager"},
                "data": {"output": {"manager_review": {"executive_summary": "Ready"}}},
            }
        )

    assert mock_session.status == "done"
    assert mock_session._events[-1] is None
    event_types = [event["type"] for event in mock_session._events if isinstance(event, dict)]
    assert event_types == ["agent_done", "agent_summary"]


async def test_agent_summaries_emit_in_completion_order(mock_session):
    async def emit_data_first():
        await mock_session._emit_ordered_agent_summary(
            1,
            {
                "type": "agent_summary",
                "agent": "data",
                "title": "Data complete",
                "summary": "Data finished first.",
                "bullets": [],
                "ts": "2026-04-28T00:00:01+00:00",
            },
        )
        assert not [
            event
            for event in mock_session._events
            if isinstance(event, dict) and event.get("type") == "agent_summary"
        ]
        await mock_session._emit_ordered_agent_summary(
            0,
            {
                "type": "agent_summary",
                "agent": "planner",
                "title": "Planner complete",
                "summary": "Planner finished second.",
                "bullets": [],
                "ts": "2026-04-28T00:00:00+00:00",
            },
        )

    await emit_data_first()

    summaries = [
        event["agent"]
        for event in mock_session._events
        if isinstance(event, dict) and event.get("type") == "agent_summary"
    ]
    assert summaries == ["planner", "data"]


async def test_news_research_does_not_emit_duplicate_summary(mock_session):
    with patch(
        "port.web.sessions.summarize_agent_output",
        return_value=AgentTaskSummary(
            title="News complete",
            summary="News synthesis is ready.",
            bullets=[],
        ),
    ) as summarize:
        await mock_session._handle_event(
            {
                "event": "on_chain_end",
                "name": "news_research",
                "metadata": {"langgraph_node": "news_research"},
                "data": {"output": {"news_research_text": "raw research"}},
            }
        )
        await mock_session._wait_for_agent_summaries()
        await mock_session._handle_event(
            {
                "event": "on_chain_end",
                "name": "news_synthesis",
                "metadata": {"langgraph_node": "news_synthesis"},
                "data": {"output": {"news_review": {"summary": "briefing"}}},
            }
        )
        await mock_session._wait_for_agent_summaries()

    news_summaries = [
        event
        for event in mock_session._events
        if isinstance(event, dict)
        and event.get("type") == "agent_summary"
        and event.get("agent") == "news"
    ]
    assert len(news_summaries) == 1
    assert news_summaries[0]["title"] == "News complete"
    assert summarize.call_count == 1
    assert mock_session.agent_outputs["news"]["news_research_text"] == "raw research"
    news_done = [
        event
        for event in mock_session._events
        if isinstance(event, dict)
        and event.get("type") == "agent_done"
        and event.get("agent") == "news"
    ]
    assert len(news_done) == 1
    assert news_done[0]["output"] == {
        "news_research_text": "raw research",
        "news_review": {"summary": "briefing"},
    }


async def test_news_internal_phases_emit_single_agent_lifecycle(mock_session):
    await mock_session._handle_event(
        {
            "event": "on_chain_start",
            "name": "news_research",
            "metadata": {"langgraph_node": "news_research"},
            "data": {},
        }
    )
    await mock_session._handle_event(
        {
            "event": "on_chain_start",
            "name": "news_synthesis",
            "metadata": {"langgraph_node": "news_synthesis"},
            "data": {},
        }
    )
    await mock_session._handle_event(
        {
            "event": "on_chain_end",
            "name": "news_research",
            "metadata": {"langgraph_node": "news_research"},
            "data": {"output": {"news_research_text": "raw research"}},
        }
    )
    with patch(
        "port.web.sessions.summarize_agent_output",
        return_value=AgentTaskSummary(
            title="News complete",
            summary="News synthesis is ready.",
            bullets=[],
        ),
    ):
        await mock_session._handle_event(
            {
                "event": "on_chain_end",
                "name": "news_synthesis",
                "metadata": {"langgraph_node": "news_synthesis"},
                "data": {"output": {"news_review": {"summary": "briefing"}}},
            }
        )
        await mock_session._wait_for_agent_summaries()

    news_events = [
        event["type"]
        for event in mock_session._events
        if isinstance(event, dict) and event.get("agent") == "news"
    ]
    assert news_events == ["agent_start", "agent_done", "agent_summary"]
    assert mock_session.agent_outputs["news"]["news_review"] == {"summary": "briefing"}


def test_graph_agent_for_chain_event_fallback_without_langgraph_node_key() -> None:
    assert (
        _graph_agent_for_chain_event({"name": "news_synthesis", "metadata": {"thread_id": "t"}})
        == "news"
    )


def test_graph_agent_for_chain_event_news_research_maps_to_news() -> None:
    assert (
        _graph_agent_for_chain_event(
            {"name": "news_research", "metadata": {"langgraph_node": "news_research"}}
        )
        == "news"
    )
