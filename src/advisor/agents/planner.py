from __future__ import annotations

import logging
import time

from langchain_core.messages import HumanMessage, SystemMessage

from advisor.config import config
from advisor.llm.context import report_step
from advisor.llm.structured import invoke_structured
from advisor.market_data import company_name_for
from advisor.news_data import ticker_news_query
from advisor.prompts import planner_system_prompt
from advisor.prompts.portfolio import portfolio_to_text
from advisor.schemas.planner import NewsFocus, NewsPlannerResult, PositionGoalFocus
from advisor.schemas.portfolio import Portfolio
from advisor.schemas.state import GraphState
from advisor.util import clip_text

log = logging.getLogger(__name__)


def build_news_focus(portfolio: Portfolio) -> NewsFocus:
    return NewsFocus(
        portfolio_goal=(portfolio.context_note or "").strip(),
        position_goals=[
            PositionGoalFocus(
                ticker=p.ticker,
                goal=(p.entry_thesis or "").strip(),
                latest_news_query=ticker_news_query(p.ticker, company_name_for(p.ticker, p.name)),
            )
            for p in portfolio.positions
        ],
    )


def sanitize_queries(raw: list[str], *, cap: int) -> list[str]:
    max_len = config.prompts.planner.max_query_chars
    out: list[str] = []
    seen: set[str] = set()
    for q in raw:
        s = (q or "").strip()
        if not s:
            continue
        if len(s) > max_len:
            s = clip_text(s, max_len)
        key = s.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= cap:
            break
    return out


def apply_planner_result(focus: NewsFocus, plan: NewsPlannerResult) -> None:
    focus.portfolio_search_queries = sanitize_queries(
        plan.portfolio_search_queries, cap=config.prompts.planner.portfolio_query_count
    )


def planner_node(state: GraphState) -> dict:
    t0 = time.monotonic()
    log.info("news search-query planning started")
    portfolio = state["portfolio"]
    focus = build_news_focus(portfolio)

    messages = [
        SystemMessage(content=planner_system_prompt()),
        HumanMessage(content=portfolio_to_text(portfolio)),
    ]

    report_step("planner", 0, "Preparing portfolio context for search planning…")
    report_step("planner", 1, "Generating portfolio-wide search queries…")

    plan: NewsPlannerResult = invoke_structured(  # type: ignore[assignment]
        NewsPlannerResult,
        messages,
        agent="planner",
        max_tokens=config.llm.planner_max_tokens,
        temperature=config.llm.planner_temperature,
        use_agent_model=True,
    )
    apply_planner_result(focus, plan)

    log.info(
        "news search-query planning done in %.1fs — %d positions, %d portfolio queries",
        time.monotonic() - t0,
        len(focus.position_goals),
        len(focus.portfolio_search_queries),
    )
    return {"news_focus": focus}
