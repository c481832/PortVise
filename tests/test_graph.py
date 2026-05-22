from __future__ import annotations

import logging
from typing import Any, cast

from port.graph import (
    _route_after_validation,
    build_checkpoint_saver,
    build_graph,
    make_initial_state,
)
from port.models import NewsFocus
from port.state import GraphState


def _edge_set() -> set[tuple[str, str]]:
    g = build_graph().get_graph()
    return {(e.source, e.target) for e in g.edges}


def test_specialists_start_on_direct_dependencies() -> None:
    edges = _edge_set()
    assert ("__start__", "data") in edges
    assert ("planner", "data") not in edges
    assert ("data", "risk") in edges
    assert ("data", "regime") in edges
    assert ("news_research", "theme") in edges


def test_validation_waits_for_synthesized_news_and_specialists() -> None:
    edges = _edge_set()
    assert ("news_synthesis", "validation") in edges
    assert ("risk", "validation") in edges
    assert ("regime", "validation") in edges
    assert ("theme", "validation") in edges


def test_news_synthesis_depends_only_on_news_research() -> None:
    edges = _edge_set()
    assert ("news_research", "news_synthesis") in edges
    assert ("data", "news_synthesis") not in edges


def test_expensive_fan_in_nodes_run_once_after_inputs_are_ready(monkeypatch) -> None:
    calls: dict[str, int] = {
        "planner": 0,
        "data": 0,
        "news_research": 0,
        "news_synthesis": 0,
        "risk": 0,
        "regime": 0,
        "theme": 0,
        "validation": 0,
        "manager": 0,
    }

    def _count(name: str) -> None:
        calls[name] += 1

    def planner_node(_state: GraphState) -> dict[str, Any]:
        _count("planner")
        return {"news_focus": "focus"}

    def data_node(_state: GraphState) -> dict[str, Any]:
        _count("data")
        return {"market_data": "market"}

    def news_research_node(state: GraphState) -> dict[str, Any]:
        _count("news_research")
        assert state.get("news_focus") == "focus"
        return {"news_research_text": "research", "news_research_query_count": 1}

    def news_synthesis_node(state: GraphState) -> dict[str, Any]:
        _count("news_synthesis")
        assert state.get("news_research_text") == "research"
        return {"news_review": "news"}

    def risk_node(state: GraphState) -> dict[str, Any]:
        _count("risk")
        assert state.get("market_data") == "market"
        return {"risk_results": ["risk"]}

    def regime_node(state: GraphState) -> dict[str, Any]:
        _count("regime")
        assert state.get("market_data") == "market"
        return {"regime_results": ["regime"]}

    def theme_node(state: GraphState) -> dict[str, Any]:
        _count("theme")
        assert state.get("market_data") == "market"
        assert state.get("news_research_text") == "research"
        return {"theme_results": ["theme"]}

    def validation_node(state: GraphState) -> dict[str, Any]:
        _count("validation")
        assert state.get("news_review") == "news"
        assert state.get("risk_results") == ["risk"]
        assert state.get("regime_results") == ["regime"]
        assert state.get("theme_results") == ["theme"]
        return {
            "validation_review": "validation",
            "validation_needs_more": False,
            "validation_missing_inputs": [],
            "validation_request_note": None,
            "validation_retry_count": 0,
        }

    def manager_node(state: GraphState) -> dict[str, Any]:
        _count("manager")
        assert state.get("validation_review") == "validation"
        return {"manager_review": "manager"}

    import port.graph as graph_module

    monkeypatch.setattr(graph_module, "planner_node", planner_node)
    monkeypatch.setattr(graph_module, "data_node", data_node)
    monkeypatch.setattr(graph_module, "news_research_node", news_research_node)
    monkeypatch.setattr(graph_module, "news_synthesis_node", news_synthesis_node)
    monkeypatch.setattr(graph_module, "risk_node", risk_node)
    monkeypatch.setattr(graph_module, "regime_node", regime_node)
    monkeypatch.setattr(graph_module, "theme_node", theme_node)
    monkeypatch.setattr(graph_module, "validation_node", validation_node)
    monkeypatch.setattr(graph_module, "manager_node", manager_node)

    graph = build_graph(checkpointer=False)
    graph.invoke(
        {
            "portfolio": "portfolio",
            "requested_locale": "en",
            "news_focus": None,
            "market_data": None,
            "news_research_text": None,
            "news_research_query_count": None,
            "news_review": None,
            "risk_results": [],
            "regime_results": [],
            "theme_results": [],
            "validation_review": None,
            "validation_needs_more": False,
            "validation_missing_inputs": [],
            "validation_request_note": None,
            "validation_retry_count": 0,
            "manager_review": None,
        }
    )

    assert calls == {
        "planner": 1,
        "data": 1,
        "news_research": 1,
        "news_synthesis": 1,
        "risk": 1,
        "regime": 1,
        "theme": 1,
        "validation": 1,
        "manager": 1,
    }


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
        NewsFocus(portfolio_goal="", portfolio_search_queries=[], position_goals=[]),
        example_market_data,
        example_news,
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
