from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from port.agent_api_models import AgentReviewRequest
from port.config import (
    llm_runtime_overrides,
    locale_runtime_state,
    review_stop_event,
    step_callback,
)
from port.models import ManagerReview
from port.review_runner import run_review


def _manager_review(summary: str = "Done") -> ManagerReview:
    return ManagerReview.model_validate(
        {
            "portfolio_verdict": {
                "action_timing": "watch",
                "investment_horizon": "tactical",
                "horizon_detail": "1-4 weeks",
                "primary_risk": "",
                "recommended_posture": "",
                "revisit_trigger": "Risk conditions change.",
                "rationale": "",
            },
            "actions": [],
            "do_nothing_case": "",
            "executive_summary": summary,
        }
    )


@dataclass
class FakeGraph:
    final_state: dict[str, Any] | None = None
    error: Exception | None = None
    sleep_seconds: float = 0.0
    seen_config: dict[str, Any] | None = None

    async def ainvoke(self, input_: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        self.seen_config = config
        if self.sleep_seconds:
            await asyncio.sleep(self.sleep_seconds)
        if self.error is not None:
            raise self.error
        assert input_["portfolio"].name == "Agent Test"
        return self.final_state or {}


@dataclass
class ContextCapturingGraph:
    seen_locale: Any = None
    seen_stop_event_exists: bool | None = None
    seen_stop_event_is_set: bool | None = None
    seen_llm_overrides: Any = None

    async def ainvoke(self, input_: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        self.seen_locale = locale_runtime_state.get()
        stop_event = review_stop_event.get()
        self.seen_stop_event_exists = stop_event is not None
        self.seen_stop_event_is_set = stop_event.is_set() if stop_event is not None else None
        self.seen_llm_overrides = llm_runtime_overrides.get()
        return {"manager_review": _manager_review()}


@dataclass
class ProgressGraph:
    async def ainvoke(self, input_: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        cb = step_callback.get()
        assert cb is not None
        cb("planner", 0, "Planning news search queries...")
        return {"manager_review": _manager_review()}


def _request_payload() -> dict:
    return {
        "portfolio": {
            "name": "Agent Test",
            "positions": [
                {
                    "ticker": "AAPL",
                    "name": "Apple",
                    "weight": 0.1,
                    "sector": "Technology",
                    "quantity": 10,
                    "entry_date": "2023-01-01",
                    "entry_price": 150.0,
                    "current_price": 180.0,
                    "dividend": 0.0,
                    "split": 1.0,
                    "entry_thesis": "Services growth",
                    "asset_class": "equity",
                    "country": "US",
                    "tags": ["quality"],
                }
            ],
            "cash_weight": 0.9,
            "base_currency": "USD",
            "benchmark": "SPY",
            "review_date": "2026-04-29",
            "context_note": "",
        },
        "corporate_actions": "off",
    }


async def test_run_review_returns_done_result(example_risk, example_regime, example_theme) -> None:
    graph = FakeGraph(
        {
            "manager_review": _manager_review(),
            "risk_results": [example_risk],
            "regime_results": [example_regime],
            "theme_results": [example_theme],
        }
    )

    with patch("port.review_runner.build_graph", return_value=graph):
        result = await run_review(AgentReviewRequest(**_request_payload()))

    assert result.status == "done"
    assert result.manager_review is not None
    assert result.manager_review.executive_summary == "Done"
    assert result.risk_review == example_risk
    assert graph.seen_config is not None
    assert graph.seen_config["configurable"]["thread_id"] == result.review_id


async def test_run_review_emits_progress_callback_events() -> None:
    events: list[dict[str, Any]] = []

    with patch("port.review_runner.build_graph", return_value=ProgressGraph()):
        result = await run_review(
            AgentReviewRequest(**_request_payload()),
            progress_callback=events.append,
        )

    assert result.status == "done"
    assert [event["type"] for event in events] == [
        "review_start",
        "graph_start",
        "agent_step",
        "review_done",
    ]
    assert events[0]["review_id"] == result.review_id
    assert events[2]["agent"] == "planner"
    assert events[2]["label"] == "Planning news search queries..."


async def test_run_review_best_effort_enrichment_records_warning() -> None:
    payload = _request_payload()
    payload["corporate_actions"] = "best_effort"
    graph = FakeGraph({"manager_review": _manager_review()})

    with (
        patch("port.review_runner.build_graph", return_value=graph),
        patch("port.review_runner.fetch_corporate_actions", side_effect=RuntimeError("network")),
    ):
        result = await run_review(AgentReviewRequest(**payload))

    assert result.status == "done"
    assert any("Corporate action fetch failed for AAPL" in item for item in result.warnings)


async def test_run_review_strict_enrichment_failure_returns_error() -> None:
    payload = _request_payload()
    payload["corporate_actions"] = "strict"

    with patch("port.review_runner.fetch_corporate_actions", side_effect=RuntimeError("network")):
        result = await run_review(AgentReviewRequest(**payload))

    assert result.status == "error"
    assert result.error is not None
    assert "Corporate action fetch failed for AAPL" in result.error


async def test_run_review_graph_failure_returns_error() -> None:
    graph = FakeGraph(error=RuntimeError("model unavailable"))

    with patch("port.review_runner.build_graph", return_value=graph):
        result = await run_review(AgentReviewRequest(**_request_payload()))

    assert result.status == "error"
    assert result.error == "model unavailable"


async def test_run_review_timeout_returns_timeout() -> None:
    payload = _request_payload()
    payload["timeout_seconds"] = 1
    graph = FakeGraph(
        {"manager_review": _manager_review()},
        sleep_seconds=2.0,
    )

    with patch("port.review_runner.build_graph", return_value=graph):
        result = await run_review(AgentReviewRequest(**payload))

    assert result.status == "timeout"
    assert result.error == "Review timed out after 1 seconds."


async def test_run_review_timeout_covers_corporate_action_enrichment() -> None:
    payload = _request_payload()
    payload["corporate_actions"] = "best_effort"
    payload["timeout_seconds"] = 1
    graph = FakeGraph({"manager_review": _manager_review()})

    def slow_fetch(*args: Any, **kwargs: Any) -> tuple[float, float]:
        import time

        time.sleep(2.0)
        return 0.0, 1.0

    with (
        patch("port.review_runner.fetch_corporate_actions", side_effect=slow_fetch),
        patch("port.review_runner.build_graph", return_value=graph),
    ):
        result = await run_review(AgentReviewRequest(**payload))

    assert result.status == "timeout"
    assert result.error == "Review timed out after 1 seconds."


async def test_run_review_passes_bounded_corporate_action_fetch_timeout() -> None:
    payload = _request_payload()
    payload["corporate_actions"] = "best_effort"
    payload["timeout_seconds"] = 30
    graph = FakeGraph({"manager_review": _manager_review()})

    with (
        patch("port.review_runner.fetch_corporate_actions", return_value=(0.0, 1.0)) as fetch,
        patch("port.review_runner.build_graph", return_value=graph),
    ):
        result = await run_review(AgentReviewRequest(**payload))

    assert result.status == "done"
    assert fetch.call_count == 1
    assert fetch.call_args.kwargs["timeout"] == 10.0


async def test_run_review_graph_timeout_error_returns_error() -> None:
    graph = FakeGraph(error=TimeoutError("provider read timeout"))

    with patch("port.review_runner.build_graph", return_value=graph):
        result = await run_review(AgentReviewRequest(**_request_payload()))

    assert result.status == "error"
    assert result.error == "provider read timeout"


async def test_run_review_sets_and_resets_runtime_contexts() -> None:
    payload = _request_payload()
    payload["locale"] = "zh-Hans-CN"
    payload["llm"] = {
        "llm_base_url": "http://example.test/v1",
        "llm_model": "best-model",
        "llm_api_key": "test-key",
        "fast_llm_base_url": "http://fast.example.test/v1",
        "fast_llm_model": "fast-model",
        "agent_models": {"risk": "risk-model"},
    }
    graph = ContextCapturingGraph()

    assert locale_runtime_state.get() is None
    assert review_stop_event.get() is None
    assert llm_runtime_overrides.get() is None

    with patch("port.review_runner.build_graph", return_value=graph):
        result = await run_review(AgentReviewRequest(**payload))

    assert result.status == "done"
    assert result.requested_locale == "zh-CN"
    assert graph.seen_locale is not None
    assert graph.seen_locale.requested_locale == "zh-CN"
    assert graph.seen_locale.content_locale == "zh-CN"
    assert graph.seen_stop_event_exists is True
    assert graph.seen_stop_event_is_set is False
    assert graph.seen_llm_overrides is not None
    assert graph.seen_llm_overrides.llm_base_url == "http://example.test/v1"
    assert graph.seen_llm_overrides.llm_model == "best-model"
    assert graph.seen_llm_overrides.llm_api_key == "test-key"
    assert graph.seen_llm_overrides.fast_llm_base_url == "http://fast.example.test/v1"
    assert graph.seen_llm_overrides.fast_llm_model == "fast-model"
    assert graph.seen_llm_overrides.agent_models == (("risk", "risk-model"),)
    assert locale_runtime_state.get() is None
    assert review_stop_event.get() is None
    assert llm_runtime_overrides.get() is None
