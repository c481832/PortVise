from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from port.agents.data import data_node
from port.agents.manager import manager_node
from port.agents.news import news_research_node, news_synthesis_node
from port.agents.planner import planner_node
from port.agents.regime import regime_node
from port.agents.risk import risk_node
from port.agents.theme import theme_node
from port.agents.validation import validation_node
from port.state import GraphState


def _route_after_validation(state: GraphState) -> str | list[str]:
    if state.get("validation_needs_more"):
        missing = state.get("validation_missing_inputs") or []
        if missing:
            return missing
        return ["risk", "regime", "theme", "news_synthesis"]
    return "manager"


def build_graph(checkpointer=None):
    builder = StateGraph(GraphState)

    builder.add_node("planner", planner_node)
    builder.add_node("data", data_node)
    builder.add_node("news_research", news_research_node)
    builder.add_node("news_synthesis", news_synthesis_node)
    builder.add_node("risk", risk_node)
    builder.add_node("regime", regime_node)
    builder.add_node("theme", theme_node)
    builder.add_node("validation", validation_node)
    builder.add_node("manager", manager_node)

    # Planner first; data and news research in parallel.
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "data")
    builder.add_edge("planner", "news_research")

    # Let deterministic specialists start as soon as their direct inputs exist.
    builder.add_edge("data", "risk")
    builder.add_edge("data", "regime")
    builder.add_edge("data", "theme")
    builder.add_edge("news_research", "theme")

    # News synthesis still joins the raw-research + market-data branches.
    builder.add_edge("data", "news_synthesis")
    builder.add_edge("news_research", "news_synthesis")

    # Validation waits for all specialist outputs and synthesized news.
    builder.add_edge("risk", "validation")
    builder.add_edge("regime", "validation")
    builder.add_edge("theme", "validation")
    builder.add_edge("news_synthesis", "validation")

    builder.add_conditional_edges(
        "validation",
        _route_after_validation,
        {
            "news_synthesis": "news_synthesis",
            "risk": "risk",
            "regime": "regime",
            "theme": "theme",
            "manager": "manager",
        },
    )
    builder.add_edge("manager", END)

    cp = checkpointer if checkpointer is not None else MemorySaver()
    return builder.compile(checkpointer=cp)


def make_initial_state(portfolio, *, requested_locale: str = "en") -> dict:
    return {
        "portfolio": portfolio,
        "requested_locale": requested_locale,
        "news_focus": None,
        "market_data": None,
        "news_research_text": None,
        "news_research_query_count": None,
        "news_review": None,
        "downstream_context": None,
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
