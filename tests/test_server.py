"""Tests for FastAPI server endpoints in port/server.py."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from port.models import PositionSnapshot
from port.server import ReviewSession, _graph_agent_for_chain_event, _reviews, app


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
                "sector": "Technology",
                "entry_date": "2023-01-01",
                "entry_price": 150.0,
                "current_price": 180.0,
                "entry_thesis": "Strong ecosystem",
            }
        ],
        "cash_weight": 0.90,
        "review_date": "2026-01-01",
    }


@pytest.fixture
def mock_session(example_portfolio):
    with patch("port.server.build_graph"):
        session = ReviewSession("test-review-id", example_portfolio)
    return session


async def test_start_review_success(portfolio_payload):
    with (
        patch("port.server.build_graph"),
        patch("port.server.fetch_corporate_actions", return_value=(7.5, 2.0)),
        patch.object(ReviewSession, "start"),
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


async def test_start_review_preserves_supplied_corporate_actions(portfolio_payload):
    portfolio_payload["positions"][0]["dividend"] = 3.0
    portfolio_payload["positions"][0]["split"] = 4.0
    with (
        patch("port.server.build_graph"),
        patch("port.server.fetch_corporate_actions") as fetch_actions,
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
        patch("port.server.build_graph"),
        patch("port.server.fetch_corporate_actions", return_value=(2.0, 3.0)) as fetch_actions,
        patch.object(ReviewSession, "start"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/review/start", json={"portfolio": portfolio_payload})

    assert resp.status_code == 200
    fetch_actions.assert_called_once()
    review_id = resp.json()["review_id"]
    position = _reviews[review_id].portfolio.positions[0]
    assert position.dividend == 2.0
    assert position.split == 3.0


async def test_start_review_invalid_portfolio():
    # Missing required fields (positions, name)
    with patch("port.server.build_graph"), patch.object(ReviewSession, "start"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/review/start", json={"portfolio": {}})
    assert resp.status_code == 422


async def test_get_result_done(mock_session):
    mock_session.status = "done"
    mock_session.final_state = {"summary": "complete"}
    mock_session.agent_outputs = {"risk": {"risk_review": {"risk_score": 6}}}
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
    assert data["agent_outputs"] == {"risk": {"risk_review": {"risk_score": 6}}}
    assert data["agent_output_updated_at"] == {"risk": "2026-04-23T00:00:00+00:00"}
    assert data["requested_locale"] == "zh-CN"
    assert data["content_locale"] == "zh-CN"
    assert data["translation_fallback_used"] is True


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


async def test_get_snapshot_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/review/nonexistent-id/snapshot")
    assert resp.status_code == 404


async def test_start_review_normalizes_locale(portfolio_payload):
    with (
        patch("port.server.build_graph"),
        patch("port.server.fetch_corporate_actions", return_value=(0.0, 1.0)),
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
    with patch("port.server.fetch_position_snapshot", return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/market/quote/AAPL")

    assert resp.status_code == 404


async def test_market_quote_passes_actions_start():
    snap = PositionSnapshot(ticker="AAPL", current_price=180.0, dividend=2.5, split=2.0)
    with patch("port.server.fetch_position_snapshot", return_value=snap) as fetch_snapshot:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/market/quote/AAPL?actions_start=2023-01-01")

    assert resp.status_code == 200
    assert resp.json()["dividend"] == 2.5
    assert resp.json()["split"] == 2.0
    fetch_snapshot.assert_called_once_with("AAPL", date(2023, 1, 1))


async def test_market_quote_invalid_ticker():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/market/quote/!!!invalid")
    assert resp.status_code == 400


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
