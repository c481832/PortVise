from __future__ import annotations

GRAPH_NODE_NAMES = frozenset(
    {
        "planner",
        "data",
        "news_collector",
        "news_summary",
        "risk",
        "regime",
        "theme",
        "allocation",
        "manager",
    }
)

# The two internal news nodes appear as one agent lifecycle in the UI: the collector starts
# it and the summary finishes it.
SSE_AGENT_FOR_NODE: dict[str, str] = {
    "news_collector": "news",
    "news_summary": "news",
}
START_SUPPRESSED_NODES = frozenset({"news_summary"})
DONE_SUPPRESSED_NODES = frozenset({"news_collector"})


def graph_agent_for_chain_event(event: dict) -> str | None:
    name = event["name"]
    if name not in GRAPH_NODE_NAMES:
        return None
    # Ignore a same-named runnable that is running inside a different node.
    if event["metadata"].get("langgraph_node", name) != name:
        return None
    return SSE_AGENT_FOR_NODE.get(name, name)
