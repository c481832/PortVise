from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from port.agents.data import data_node
from port.agents.manager import manager_node
from port.agents.news import news_node
from port.agents.planner import planner_node
from port.agents.regime import regime_node
from port.agents.risk import risk_node
from port.agents.theme import theme_node
from port.agents.validation import validation_node
from port.state import GraphState


def build_graph(checkpointer=None):
    builder = StateGraph(GraphState)

    builder.add_node("planner", planner_node)
    builder.add_node("data", data_node)
    builder.add_node("news", news_node)
    builder.add_node("risk", risk_node)
    builder.add_node("regime", regime_node)
    builder.add_node("theme", theme_node)
    builder.add_node("validation", validation_node)
    builder.add_node("manager", manager_node)

    # Sequential: start → planner → data → news
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "data")
    builder.add_edge("data", "news")

    # Fan-out: news → [risk, regime, theme]
    builder.add_edge("news", "risk")
    builder.add_edge("news", "regime")
    builder.add_edge("news", "theme")

    # Fan-in: [risk, regime, theme] → validation
    builder.add_edge("risk", "validation")
    builder.add_edge("regime", "validation")
    builder.add_edge("theme", "validation")

    builder.add_edge("validation", "manager")
    builder.add_edge("manager", END)

    cp = checkpointer if checkpointer is not None else MemorySaver()
    return builder.compile(checkpointer=cp)


def make_initial_state(portfolio) -> dict:
    return {
        "portfolio": portfolio,
        "news_focus": None,
        "market_data": None,
        "news_review": None,
        "risk_results": [],
        "regime_results": [],
        "theme_results": [],
        "validation_review": None,
        "manager_review": None,
    }
