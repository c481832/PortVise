from __future__ import annotations

from port.graph import build_graph


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


def test_specialists_no_longer_wait_on_planner_post_news() -> None:
    edges = _edge_set()
    assert ("planner_post_news", "risk") not in edges
    assert ("planner_post_news", "regime") not in edges
    assert ("planner_post_news", "theme") not in edges
