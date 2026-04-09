"""Tests for FastAPI server endpoints in port/server.py."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

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
    with patch("port.server.build_graph"), patch.object(ReviewSession, "start"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/review/start", json={"portfolio": portfolio_payload})
    assert resp.status_code == 200
    assert "review_id" in resp.json()


async def test_start_review_invalid_portfolio():
    # Missing required fields (positions, name)
    with patch("port.server.build_graph"), patch.object(ReviewSession, "start"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/review/start", json={"portfolio": {}})
    assert resp.status_code == 422


async def test_get_status_found(mock_session):
    mock_session.status = "running"
    _reviews["test-review-id"] = mock_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/review/test-review-id/status")

    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


async def test_get_status_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/review/nonexistent-id/status")

    assert resp.status_code == 404


async def test_get_result_done(mock_session):
    mock_session.status = "done"
    mock_session.final_state = {"summary": "complete"}
    _reviews["test-review-id"] = mock_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/review/test-review-id/result")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "done"
    assert data["final_state"] == {"summary": "complete"}


async def test_get_result_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/review/nonexistent-id/result")

    assert resp.status_code == 404


async def test_stream_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/review/nonexistent-id/stream")

    assert resp.status_code == 404


async def test_confirm_wrong_status(mock_session):
    mock_session.status = "running"
    _reviews["test-review-id"] = mock_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/review/test-review-id/confirm",
            json={"response": "yes"},
        )

    assert resp.status_code == 409


async def test_confirm_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/review/nonexistent-id/confirm",
            json={"response": "yes"},
        )

    assert resp.status_code == 404


async def test_market_quote_not_found():
    with patch("port.server.fetch_position_snapshot", return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/market/quote/AAPL")

    assert resp.status_code == 404


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


def test_graph_agent_for_chain_event_planner_post_news_maps_to_planner() -> None:
    assert (
        _graph_agent_for_chain_event(
            {"name": "planner_post_news", "metadata": {"langgraph_node": "planner_post_news"}}
        )
        == "planner"
    )
