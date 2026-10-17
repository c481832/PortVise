from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph

from advisor.agents.allocation import allocation_node
from advisor.agents.data import data_node
from advisor.agents.manager import manager_node
from advisor.agents.news import news_collector_node, news_summary_node
from advisor.agents.planner import planner_node
from advisor.agents.regime import regime_node
from advisor.agents.risk import risk_node
from advisor.agents.theme import theme_node
from advisor.schemas.allocation import AllocationReview
from advisor.schemas.manager import ManagerReview
from advisor.schemas.market import MarketData
from advisor.schemas.news import NewsReview
from advisor.schemas.planner import NewsFocus
from advisor.schemas.portfolio import Portfolio
from advisor.schemas.regime import RegimeReview
from advisor.schemas.risk import RiskReview
from advisor.schemas.state import GraphState
from advisor.schemas.theme import ThemeReview

CHECKPOINT_MSGPACK_ALLOWLIST = (
    Portfolio,
    NewsFocus,
    MarketData,
    NewsReview,
    RiskReview,
    RegimeReview,
    ThemeReview,
    AllocationReview,
    ManagerReview,
)


def build_graph():
    builder = StateGraph(GraphState)

    builder.add_node("planner", planner_node)
    builder.add_node("data", data_node)
    builder.add_node("news_collector", news_collector_node)
    builder.add_node("news_summary", news_summary_node)
    builder.add_node("risk", risk_node)
    builder.add_node("regime", regime_node)
    builder.add_node("theme", theme_node)
    builder.add_node("allocation", allocation_node)
    builder.add_node("manager", manager_node)

    # Data and planning are independent roots; fan-in edges enforce the real dependencies.
    builder.add_edge(START, "planner")
    builder.add_edge(START, "data")
    builder.add_edge("planner", "news_collector")

    builder.add_edge("data", "risk")
    builder.add_edge("data", "regime")
    builder.add_edge(["data", "news_collector"], "theme")

    builder.add_edge("news_collector", "news_summary")

    # Every specialist either returns its review or raises, so this fan-in is the completeness gate.
    builder.add_edge(["risk", "regime", "theme", "news_summary"], "allocation")
    builder.add_edge("allocation", "manager")
    builder.add_edge("manager", END)

    # Checkpoints contain Pydantic state objects, so allow only the models the graph owns.
    return builder.compile(
        checkpointer=MemorySaver(
            serde=JsonPlusSerializer(allowed_msgpack_modules=CHECKPOINT_MSGPACK_ALLOWLIST)
        )
    )


def make_initial_state(
    portfolio,
    *,
    inherited_feedback: list[dict] | None,
) -> dict:
    return {
        "portfolio": portfolio,
        "inherited_feedback": list(inherited_feedback or []),
        "news_focus": None,
        "market_data": None,
        "news_collector_text": None,
        "news_review": None,
        "risk_review": None,
        "regime_review": None,
        "theme_review": None,
        "allocation_review": None,
        "manager_review": None,
    }
