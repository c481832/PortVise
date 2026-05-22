"""Planner node: builds search priorities for the data and news branches."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from port.config import config, invoke_structured
from port.config import step_callback as _step_cb
from port.models import NewsFocus, NewsPlannerResult, PositionGoalFocus
from port.portfolio import Portfolio, portfolio_to_text
from port.prompts import PLANNER_SYSTEM_PROMPT

if TYPE_CHECKING:
    from port.state import GraphState

log = logging.getLogger(__name__)


def build_news_focus(portfolio: Portfolio) -> NewsFocus:
    """Portfolio goal (`context_note`) + each position's entry thesis (queries filled by LLM)."""
    return NewsFocus(
        portfolio_goal=(portfolio.context_note or "").strip(),
        position_goals=[
            PositionGoalFocus(ticker=p.ticker, goal=(p.entry_thesis or "").strip())
            for p in portfolio.positions
        ],
    )


def _norm_ticker(t: str) -> str:
    return (t or "").strip().upper()


def _sanitize_queries(raw: list[str], *, cap: int) -> list[str]:
    max_len = config.prompts.planner.max_query_chars
    out: list[str] = []
    seen: set[str] = set()
    for q in raw:
        s = (q or "").strip()
        if not s:
            continue
        if len(s) > max_len:
            s = s[:max_len]
        key = s.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= cap:
            break
    return out


def _sanitize_one_query(raw: str) -> str:
    out = _sanitize_queries([raw] if raw else [], cap=1)
    return out[0] if out else ""


def _merge_planner_result(focus: NewsFocus, plan: NewsPlannerResult) -> None:
    focus.portfolio_search_queries = _sanitize_queries(
        plan.portfolio_search_queries, cap=config.prompts.planner.portfolio_query_count
    )
    latest_by: dict[str, str] = {}
    for pp in plan.position_plans:
        t = _norm_ticker(pp.ticker)
        if not t:
            continue
        latest_by[t] = _sanitize_one_query(pp.latest_news_query)

    for pg in focus.position_goals:
        t = _norm_ticker(pg.ticker)
        pg.latest_news_query = latest_by.get(t, "")


def _planner_search_queries_phase(state: GraphState) -> dict:
    t0 = time.monotonic()
    log.info("planner search-query planning started")
    portfolio = state["portfolio"]
    focus = build_news_focus(portfolio)

    tickers = ", ".join(_norm_ticker(p.ticker) for p in portfolio.positions)
    human = (
        "Plan web news searches for the following portfolio.\n\n"
        f"{portfolio_to_text(portfolio)}\n\n"
        "Tickers (you MUST include one position_plans entry per symbol, each with a non-empty "
        f'latest_news_query exactly like "latest news for {{TICKER}}"): {tickers}\n\n'
        "Return a NewsPlannerResult: portfolio_search_queries (exactly three macro topics), "
        "position_plans (one row per ticker; latest_news_query per row)."
    )
    messages = [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=human),
    ]

    cb = _step_cb.get(None)
    if cb:
        cb("planner", 0, "Preparing portfolio context for search planning…")
        cb("planner", 1, "Generating portfolio and ticker search queries…")

    plan: NewsPlannerResult = invoke_structured(  # type: ignore[assignment]
        NewsPlannerResult,
        messages,
        agent="planner",
        max_tokens=config.llm.planner_max_tokens,
        temperature=config.llm.planner_temperature,
    )
    _merge_planner_result(focus, plan)

    if cb:
        cb("planner", 2, "Validating ticker query coverage…")

    missing = [
        pg.ticker
        for pg in focus.position_goals
        if not _sanitize_one_query(pg.latest_news_query)
    ]
    if missing:
        raise RuntimeError(
            f"planner returned no latest_news_query for {len(missing)} position(s): {missing}"
        )

    n_search_queries = len(focus.portfolio_search_queries)
    n_with_q = sum(1 for pg in focus.position_goals if _sanitize_one_query(pg.latest_news_query))
    log.info(
        "planner search-query planning done in %.1fs — %d positions, %d portfolio queries, "
        "%d positions with per-ticker latest-news query",
        time.monotonic() - t0,
        len(focus.position_goals),
        n_search_queries,
        n_with_q,
    )
    return {"news_focus": focus}


def planner_node(state: GraphState) -> dict:
    """Build search query focus for downstream news nodes."""
    return _planner_search_queries_phase(state)
