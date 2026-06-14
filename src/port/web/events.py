from __future__ import annotations

from datetime import date
from typing import Any

_GRAPH_NODE_NAMES = frozenset(
    {
        "planner",
        "data",
        "news_research",
        "news_synthesis",
        "risk",
        "regime",
        "theme",
        "validation",
        "manager",
    }
)

_SSE_AGENT_FOR_NODE: dict[str, str] = {
    "news_research": "news",
    "news_synthesis": "news",
}

# The two internal news nodes appear as one agent lifecycle in the UI.
SUMMARY_SUPPRESSED_NODES = frozenset({"news_research"})
START_SUPPRESSED_NODES = frozenset({"news_synthesis"})
DONE_SUPPRESSED_NODES = frozenset({"news_research"})
MERGED_OUTPUT_NODES = frozenset({"news_synthesis"})


def merge_agent_output(existing: Any, new: Any) -> Any:
    if isinstance(existing, dict) and isinstance(new, dict):
        merged = dict(existing)
        merged.update(new)
        return merged
    return new


def graph_agent_for_chain_event(event: dict) -> str | None:
    """Map a LangGraph chain event to the UI's agent slot, or None to ignore."""
    name = event.get("name", "")
    if not isinstance(name, str) or name not in _GRAPH_NODE_NAMES:
        return None
    md = event.get("metadata")
    if isinstance(md, dict) and "langgraph_node" in md:
        gn = md.get("langgraph_node")
        if gn is not None and gn != name:
            return None
    return _SSE_AGENT_FOR_NODE.get(name, name)


def serialise(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return {k: serialise(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialise(i) for i in obj]
    if isinstance(obj, date):
        return obj.isoformat()
    return obj
