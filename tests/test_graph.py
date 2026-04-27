from __future__ import annotations

import logging
from typing import cast

from port.graph import (
    _route_after_validation,
    build_checkpoint_saver,
    build_graph,
    make_initial_state,
)
from port.models import DownstreamContextPlan, NewsFocus
from port.state import GraphState


def _edge_set() -> set[tuple[str, str]]:
    g = build_graph().get_graph()
    return {(e.source, e.target) for e in g.edges}


def test_specialists_start_on_direct_dependencies() -> None:
    edges = _edge_set()
    assert ("data", "risk") in edges
    assert ("data", "regime") in edges
    assert ("data", "theme") in edges
    assert ("news_research", "theme") in edges


def test_validation_waits_for_synthesized_news_and_specialists() -> None:
    edges = _edge_set()
    assert ("news_synthesis", "validation") in edges
    assert ("risk", "validation") in edges
    assert ("regime", "validation") in edges
    assert ("theme", "validation") in edges


def test_make_initial_state_seeds_requested_locale(example_portfolio) -> None:
    state = make_initial_state(example_portfolio, requested_locale="zh-CN")
    assert state["requested_locale"] == "zh-CN"
    assert state["validation_needs_more"] is False
    assert state["validation_missing_inputs"] == []
    assert state["validation_retry_count"] == 0


def test_checkpoint_serializer_allows_portfolio_state_models_without_warnings(
    caplog,
    example_portfolio,
    example_market_data,
    example_news,
    example_risk,
    example_regime,
    example_theme,
    example_validation,
    example_manager_review,
) -> None:
    saver = build_checkpoint_saver()

    state_values = [
        example_portfolio,
        NewsFocus(),
        example_market_data,
        example_news,
        DownstreamContextPlan(),
        example_risk,
        example_regime,
        example_theme,
        example_validation,
        example_manager_review,
    ]

    with caplog.at_level(logging.WARNING, logger="langgraph.checkpoint.serde.jsonplus"):
        payload = saver.serde.dumps_typed(state_values)
        loaded = saver.serde.loads_typed(payload)

    assert loaded == state_values
    assert "Deserializing unregistered type" not in caplog.text


def test_route_after_validation_goes_to_manager_when_complete() -> None:
    state = cast(
        GraphState,
        {
            "validation_needs_more": False,
            "validation_missing_inputs": [],
        },
    )
    assert _route_after_validation(state) == "manager"


def test_route_after_validation_requests_only_missing_agents() -> None:
    state = cast(
        GraphState,
        {
            "validation_needs_more": True,
            "validation_missing_inputs": ["risk", "theme"],
        },
    )
    assert _route_after_validation(state) == ["risk", "theme"]
