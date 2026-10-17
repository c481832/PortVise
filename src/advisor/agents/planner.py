from __future__ import annotations

import logging
import time

from langchain_core.messages import HumanMessage, SystemMessage

from advisor.config import config
from advisor.llm.context import report_step
from advisor.llm.structured import invoke_structured
from advisor.prompts import planner_system_prompt
from advisor.prompts.portfolio import portfolio_to_text
from advisor.schemas.planner import NewsFocus, NewsPlannerResult, PositionGoalFocus
from advisor.schemas.portfolio import Portfolio
from advisor.schemas.state import GraphState
from advisor.util import clip_text, format_inherited_feedback

log = logging.getLogger(__name__)


def build_news_focus(portfolio: Portfolio) -> NewsFocus:
    return NewsFocus(
        portfolio_goal=(portfolio.context_note or "").strip(),
        position_goals=[
            PositionGoalFocus(ticker=p.ticker, goal=(p.entry_thesis or "").strip())
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
    latest_by: dict[str, str] = {}
    for pp in plan.position_plans:
        t = pp.ticker.strip().upper()
        if not t:
            continue
        cleaned = sanitize_queries([pp.latest_news_query], cap=1)
        latest_by[t] = cleaned[0] if cleaned else ""

    for pg in focus.position_goals:
        t = pg.ticker.strip().upper()
        pg.latest_news_query = latest_by.get(t, "")


def planner_node(state: GraphState) -> dict:
    t0 = time.monotonic()
    log.info("news search-query planning started")
    portfolio = state["portfolio"]
    focus = build_news_focus(portfolio)

    tickers = ", ".join(p.ticker for p in portfolio.positions)
    sections = [
        portfolio_to_text(portfolio),
        f"TICKERS: {tickers}",
        format_inherited_feedback(
            state.get("inherited_feedback") or [],
            heading="CARRIED-FORWARD USER GUIDANCE:",
        ),
    ]
    human = "\n\n".join(section for section in sections if section)
    messages = [
        SystemMessage(content=planner_system_prompt()),
        HumanMessage(content=human),
    ]

    report_step("planner", 0, "Preparing portfolio context for search planning…")
    report_step("planner", 1, "Generating portfolio and ticker search queries…")

    plan: NewsPlannerResult = invoke_structured(  # type: ignore[assignment]
        NewsPlannerResult,
        messages,
        agent="planner",
        max_tokens=config.llm.planner_max_tokens,
        temperature=config.llm.planner_temperature,
        use_agent_model=True,
    )
    apply_planner_result(focus, plan)

    report_step("planner", 2, "Validating ticker query coverage…")

    missing = [pg.ticker for pg in focus.position_goals if not pg.latest_news_query]
    if missing:
        raise RuntimeError(
            f"planner returned no latest_news_query for {len(missing)} position(s): {missing}"
        )

    log.info(
        "news search-query planning done in %.1fs — %d positions, %d portfolio queries",
        time.monotonic() - t0,
        len(focus.position_goals),
        len(focus.portfolio_search_queries),
    )
    return {"news_focus": focus}
