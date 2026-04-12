"""Tests for FastAPI server endpoints in port/server.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from port.server import ReviewSession, _map_node_to_agent, _reviews, app


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


def test_map_node_to_agent_direct_names() -> None:
    """Nodes whose name matches the UI agent directly."""
    for node in ("planner", "data", "risk", "regime", "theme", "validation", "manager"):
        assert _map_node_to_agent(node) == node


def test_map_node_to_agent_aliases() -> None:
    """Nodes that map to a different UI agent name."""
    assert _map_node_to_agent("planner_post_news") == "planner"
    assert _map_node_to_agent("news_research") == "news"
    assert _map_node_to_agent("news_synthesis") == "news"


def test_map_node_to_agent_unknown_returns_none() -> None:
    assert _map_node_to_agent("ChatOpenAI") is None
    assert _map_node_to_agent("") is None
    assert _map_node_to_agent("some_random_node") is None


@pytest.fixture
def streaming_session(example_portfolio):
    """ReviewSession with mocked graph — provides AsyncMock _emit."""
    with patch("port.server.build_graph"):
        s = ReviewSession("test-id", example_portfolio)
    s._emit = AsyncMock()
    return s


async def test_handle_chunk_messages_emits_agent_start_and_stream(streaming_session):
    """First messages chunk for an agent emits agent_start, then agent_stream."""
    chunk_msg = MagicMock()
    chunk_msg.content = ""
    chunk_msg.tool_call_chunks = [{"args": '{"score": 7'}]
    chunk = {
        "type": "messages",
        "data": (chunk_msg, {"langgraph_node": "risk"}),
    }

    await streaming_session._handle_chunk(chunk)

    calls = [c.args[0]["type"] for c in streaming_session._emit.call_args_list]
    assert calls == ["agent_start", "agent_stream"]
    stream_event = streaming_session._emit.call_args_list[1].args[0]
    assert stream_event["agent"] == "risk"
    assert stream_event["token"] == '{"score": 7'


async def test_handle_chunk_messages_no_duplicate_agent_start(streaming_session):
    """Second messages chunk for same agent should NOT emit another agent_start."""
    chunk_msg = MagicMock()
    chunk_msg.content = ""
    chunk_msg.tool_call_chunks = [{"args": "hello"}]
    chunk = {
        "type": "messages",
        "data": (chunk_msg, {"langgraph_node": "risk"}),
    }

    await streaming_session._handle_chunk(chunk)
    streaming_session._emit.reset_mock()
    await streaming_session._handle_chunk(chunk)

    calls = [c.args[0]["type"] for c in streaming_session._emit.call_args_list]
    assert "agent_start" not in calls
    assert calls == ["agent_stream"]


async def test_handle_chunk_messages_text_content(streaming_session):
    """Text content tokens (msg.content) are streamed when no tool_call_chunks."""
    chunk_msg = MagicMock()
    chunk_msg.content = "analyzing"
    chunk_msg.tool_call_chunks = []
    chunk = {
        "type": "messages",
        "data": (chunk_msg, {"langgraph_node": "manager"}),
    }

    await streaming_session._handle_chunk(chunk)

    stream_event = streaming_session._emit.call_args_list[1].args[0]
    assert stream_event["token"] == "analyzing"


async def test_handle_chunk_messages_unknown_node_ignored(streaming_session):
    """Messages from unmapped nodes are silently ignored."""
    chunk_msg = MagicMock()
    chunk_msg.content = "stuff"
    chunk_msg.tool_call_chunks = []
    chunk = {
        "type": "messages",
        "data": (chunk_msg, {"langgraph_node": "ChatOpenAI"}),
    }

    await streaming_session._handle_chunk(chunk)
    streaming_session._emit.assert_not_called()


async def test_handle_chunk_updates_emits_agent_done(streaming_session):
    """Updates chunk emits agent_done with serialised output."""
    chunk = {
        "type": "updates",
        "data": {"risk": {"risk_results": [{"score": 7}]}},
    }
    streaming_session._streaming_agents.add("risk")

    await streaming_session._handle_chunk(chunk)

    calls = [c.args[0]["type"] for c in streaming_session._emit.call_args_list]
    assert "agent_done" in calls
    done_event = next(
        c.args[0]
        for c in streaming_session._emit.call_args_list
        if c.args[0]["type"] == "agent_done"
    )
    assert done_event["agent"] == "risk"


async def test_handle_chunk_updates_manager_closes_stream(streaming_session):
    """Manager updates chunk emits agent_done then None sentinel."""
    chunk = {
        "type": "updates",
        "data": {"manager": {"manager_review": {"summary": "done"}}},
    }
    streaming_session._streaming_agents.add("manager")

    await streaming_session._handle_chunk(chunk)

    calls = [c.args[0] for c in streaming_session._emit.call_args_list]
    types = [c["type"] if isinstance(c, dict) else c for c in calls]
    assert "agent_done" in types
    assert streaming_session._emit.call_args_list[-1].args[0] is None


async def test_handle_chunk_updates_non_llm_node_emits_start(streaming_session):
    """Non-LLM nodes (like data) that never sent messages still get agent_start from updates."""
    chunk = {
        "type": "updates",
        "data": {"data": {"market_data": {"fetched": True}}},
    }

    await streaming_session._handle_chunk(chunk)

    calls = [
        c.args[0]["type"]
        for c in streaming_session._emit.call_args_list
        if isinstance(c.args[0], dict)
    ]
    assert "agent_start" in calls
    assert "agent_done" in calls


async def test_handle_chunk_messages_empty_tool_args_no_stream(streaming_session):
    """tool_call_chunks with empty args should emit agent_start but NOT agent_stream."""
    chunk_msg = MagicMock()
    chunk_msg.content = ""
    chunk_msg.tool_call_chunks = [{"name": "SomeFunction", "args": ""}]
    chunk = {"type": "messages", "data": (chunk_msg, {"langgraph_node": "risk"})}

    await streaming_session._handle_chunk(chunk)

    calls = [c.args[0]["type"] for c in streaming_session._emit.call_args_list]
    assert calls == ["agent_start"]


async def test_handle_chunk_messages_list_content(streaming_session):
    """List-type content (multimodal) extracts text blocks."""
    chunk_msg = MagicMock()
    chunk_msg.content = [{"type": "text", "text": "analyzing risk"}]
    chunk_msg.tool_call_chunks = []
    chunk = {"type": "messages", "data": (chunk_msg, {"langgraph_node": "risk"})}

    await streaming_session._handle_chunk(chunk)

    stream_event = streaming_session._emit.call_args_list[1].args[0]
    assert stream_event["token"] == "analyzing risk"
