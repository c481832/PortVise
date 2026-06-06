from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph

from port.agents.data import data_node
from port.agents.manager import manager_node
from port.agents.news import news_research_node, news_synthesis_node
from port.agents.planner import planner_node
from port.agents.regime import regime_node
from port.agents.risk import risk_node
from port.agents.theme import theme_node
from port.agents.validation import validation_node
from port.portfolio import Portfolio
from port.schemas.manager import ManagerReview
from port.schemas.market import MarketData
from port.schemas.news import NewsReview
from port.schemas.planner import NewsFocus
from port.schemas.regime import RegimeReview
from port.schemas.risk import RiskReview
from port.schemas.theme import ThemeReview
from port.schemas.validation import ValidationReview
from port.state import GraphState

_CHECKPOINT_MSGPACK_ALLOWLIST = (
    Portfolio,
    NewsFocus,
    MarketData,
    NewsReview,
    RiskReview,
    RegimeReview,
    ThemeReview,
    ValidationReview,
    ManagerReview,
)


def build_checkpoint_saver():
    # Checkpoints contain Pydantic state objects, so allow only the models the graph owns.
    return MemorySaver(
        serde=JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_MSGPACK_ALLOWLIST)
    )


def _route_after_validation(state: GraphState) -> str | list[str]:
    if state.get("validation_needs_more"):
        missing = state.get("validation_missing_inputs") or []
        if missing:
            return missing
        # A validation retry without a precise diagnosis reruns every fan-in dependency.
        return ["risk", "regime", "theme", "news_synthesis"]
    return "manager"


def build_graph(*, checkpointer=None):
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

    # Data and planning are independent roots; fan-in edges enforce the real dependencies.
    builder.add_edge(START, "planner")
    builder.add_edge(START, "data")
    builder.add_edge("planner", "news_research")

    builder.add_edge("data", "risk")
    builder.add_edge("data", "regime")
    builder.add_edge(["data", "news_research"], "theme")

    builder.add_edge("news_research", "news_synthesis")

    builder.add_edge(["risk", "regime", "theme", "news_synthesis"], "validation")

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

    cp = checkpointer if checkpointer is not None else build_checkpoint_saver()
    return builder.compile(checkpointer=cp)


def make_initial_state(
    portfolio,
    *,
    requested_locale: str,
    inherited_feedback: list[dict] | None = None,
) -> dict:
    return {
        "portfolio": portfolio,
        "requested_locale": requested_locale,
        "inherited_feedback": list(inherited_feedback or []),
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
