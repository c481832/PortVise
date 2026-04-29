from __future__ import annotations

from unittest.mock import patch

import pytest

from port.agent_api_models import AgentReviewResult
from port.mcp_server import mcp, run_portfolio_review
from port.models import ManagerReview


def _portfolio() -> dict:
    return {
        "name": "MCP Test",
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
    }


async def test_run_portfolio_review_returns_structured_result() -> None:
    result = AgentReviewResult(
        review_id="review-1",
        status="done",
        started_at="2026-04-29T00:00:00+00:00",
        finished_at="2026-04-29T00:01:00+00:00",
        requested_locale="en",
        content_locale="en",
        manager_review=ManagerReview(executive_summary="Done"),
    )

    with patch("port.mcp_server.run_review", return_value=result):
        returned = await run_portfolio_review(portfolio=_portfolio(), corporate_actions="off")

    assert returned == result
    assert returned.manager_review is not None
    assert returned.manager_review.executive_summary == "Done"


async def test_run_portfolio_review_reports_context_progress() -> None:
    result = AgentReviewResult(
        review_id="review-1",
        status="done",
        started_at="2026-04-29T00:00:00+00:00",
        finished_at="2026-04-29T00:01:00+00:00",
        requested_locale="en",
        content_locale="en",
        manager_review=ManagerReview(executive_summary="Done"),
    )

    class FakeContext:
        def __init__(self) -> None:
            self.infos: list[str] = []
            self.progress_messages: list[str] = []

        async def info(self, message: str) -> None:
            self.infos.append(message)

        async def report_progress(self, *, progress: float, total: float, message: str) -> None:
            self.progress_messages.append(message)

    async def fake_run_review(_request, *, progress_callback):
        progress_callback(
            {
                "type": "agent_step",
                "agent": "manager",
                "label": "Generating action plan...",
            }
        )
        return result

    ctx = FakeContext()
    with patch("port.mcp_server.run_review", side_effect=fake_run_review):
        returned = await run_portfolio_review(
            portfolio=_portfolio(),
            corporate_actions="off",
            ctx=ctx,  # type: ignore[arg-type]
        )

    assert returned == result
    assert ctx.infos == ["manager: Generating action plan..."]
    assert ctx.progress_messages == ["manager: Generating action plan..."]


async def test_mcp_registers_run_portfolio_review_with_structured_schemas() -> None:
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    assert "run_portfolio_review" in tools

    tool = tools["run_portfolio_review"]
    input_schema = tool.inputSchema
    input_defs = input_schema.get("$defs", {})
    portfolio_property = input_schema["properties"]["portfolio"]
    llm_property = input_schema["properties"]["llm"]

    assert "Portfolio" in input_defs
    assert portfolio_property.get("$ref") == "#/$defs/Portfolio"
    assert {"name", "positions"}.issubset(set(input_defs["Portfolio"]["required"]))

    assert "AgentLLMConfig" in input_defs
    assert "llm_base_url" in input_defs["AgentLLMConfig"]["properties"]
    assert _schema_contains_ref(llm_property, "#/$defs/AgentLLMConfig")

    timeout_schema = input_schema["properties"]["timeout_seconds"]
    assert timeout_schema["minimum"] == 0
    timeout_description = timeout_schema["description"].lower()
    assert "0" in timeout_description
    assert "disable" in timeout_description
    assert "indefinitely" in timeout_description

    output_schema = tool.outputSchema
    assert output_schema is not None
    assert "manager_review" in output_schema["properties"]


async def test_mcp_call_tool_returns_structured_content() -> None:
    result = AgentReviewResult(
        review_id="review-1",
        status="done",
        started_at="2026-04-29T00:00:00+00:00",
        finished_at="2026-04-29T00:01:00+00:00",
        requested_locale="en",
        content_locale="en",
        manager_review=ManagerReview(executive_summary="Done"),
    )

    with patch("port.mcp_server.run_review", return_value=result):
        _content_blocks, structured_content = await mcp.call_tool(
            "run_portfolio_review",
            {"portfolio": _portfolio(), "corporate_actions": "off"},
        )

    assert structured_content["status"] == "done"
    assert structured_content["manager_review"]["executive_summary"] == "Done"


async def test_run_portfolio_review_raises_for_failed_result() -> None:
    result = AgentReviewResult(
        review_id="review-1",
        status="error",
        started_at="2026-04-29T00:00:00+00:00",
        finished_at="2026-04-29T00:01:00+00:00",
        requested_locale="en",
        content_locale="en",
        error="model unavailable",
    )

    with (
        patch("port.mcp_server.run_review", return_value=result),
        pytest.raises(RuntimeError, match="model unavailable"),
    ):
        await run_portfolio_review(portfolio=_portfolio(), corporate_actions="off")


def _schema_contains_ref(schema: object, ref: str) -> bool:
    if isinstance(schema, dict):
        return schema.get("$ref") == ref or any(
            _schema_contains_ref(value, ref) for value in schema.values()
        )
    if isinstance(schema, list):
        return any(_schema_contains_ref(value, ref) for value in schema)
    return False
