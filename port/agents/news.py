"""News agent — planned web searches for every query, then structured NewsReview from the LLM."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from port.agents.planner import build_news_focus
from port.config import invoke_structured
from port.config import step_callback as _step_cb
from port.models import NewsReview
from port.portfolio import (
    Portfolio,
    market_data_to_text,
    news_focus_to_text,
    planned_news_tool_queries,
    portfolio_to_text,
)
from port.prompts import NEWS_SYSTEM_PROMPT
from port.tools.news_tools import _web_finance_news_text, fallback_news_gather

if TYPE_CHECKING:
    from port.state import GraphState

log = logging.getLogger(__name__)

_RESULT_CAP = 12000


def _run_planned_news_searches(
    portfolio: Portfolio,
    focus,
    *,
    step_cb=None,
) -> tuple[str, int]:
    """Run ``search_web_finance_news``-equivalent fetch for every planned query (no round cap)."""
    queries = planned_news_tool_queries(focus)
    n = len(queries)
    log.info("news web search: %d planned queries (running all before synthesis)", n)

    chunks: list[str] = []
    for i, q in enumerate(queries):
        try:
            if step_cb:
                step_cb("news", 0, f"News search {i + 1}/{n}…")
        except Exception:
            pass
        t0 = time.monotonic()
        out = _web_finance_news_text(q)
        log.info(
            "news web search query %d/%d %r → %d chars in %.1fs",
            i + 1,
            n,
            q,
            len(out),
            time.monotonic() - t0,
        )
        if len(out) > _RESULT_CAP:
            out = out[:_RESULT_CAP] + "\n… (truncated)"
        chunks.append(f"### Query: {q}\n{out}")

    research = "\n\n---\n\n".join(chunks)

    log.info(
        "news web search complete: %d queries executed, %d chars total",
        n,
        len(research),
    )
    return research, n


def _build_news_user_content(state: GraphState, *, include_market_snapshot: bool) -> str:
    """Synthesis phase: SEARCH PRIORITIES + portfolio + optional live data for NewsReview JSON."""
    portfolio = state["portfolio"]
    parts: list[str] = []
    focus = state.get("news_focus")
    if focus is not None:
        parts.append(news_focus_to_text(focus))
    parts.append(
        f"Prepare a market briefing for the following portfolio:\n\n{portfolio_to_text(portfolio)}"
    )
    if include_market_snapshot:
        md = state.get("market_data")
        if md:
            parts.append(market_data_to_text(md))
    return "\n\n".join(parts)


def news_research_node(state: GraphState) -> dict:
    """Run all planner web searches (sequential); runs in parallel with data_node."""
    t_start = time.monotonic()
    log.info("news research started (parallel with data)")
    portfolio = state["portfolio"]
    cb = _step_cb.get(None)
    focus = state.get("news_focus") or build_news_focus(state["portfolio"])
    try:
        if cb:
            cb("news", 0, "Gathering news (all planned web searches, parallel with data)…")
    except Exception:
        pass
    tool_research, query_count = _run_planned_news_searches(portfolio, focus, step_cb=cb)
    log.info("news research done in %.1fs", time.monotonic() - t_start)
    return {
        "news_research_text": tool_research,
        "news_research_query_count": query_count,
    }


def news_synthesis_node(state: GraphState) -> dict:
    """Joins market_data + tool research; runs after data and news_research both finish."""
    t_start = time.monotonic()
    log.info("news synthesis started")
    portfolio = state["portfolio"]
    cb = _step_cb.get(None)
    user_content = _build_news_user_content(state, include_market_snapshot=True)
    research = (state.get("news_research_text") or "").strip()
    if not research:
        log.info("no research text — fallback_news_gather")
        research = fallback_news_gather(portfolio)
    synthesis_body = f"{user_content}\n\n=== TOOL-GATHERED RESEARCH ===\n{research}"

    try:
        if cb:
            cb("news", 1, "Synthesising findings with live market snapshot…")
    except Exception:
        pass

    log.info("calling synthesis LLM")
    t2 = time.monotonic()
    result: NewsReview = invoke_structured(  # type: ignore[assignment]
        NewsReview,
        [SystemMessage(content=NEWS_SYSTEM_PROMPT), HumanMessage(content=synthesis_body)],
        agent="news_synthesis",
    )
    elapsed_total = time.monotonic() - t_start
    log.info("synthesis done in %.1fs — node total %.1fs", time.monotonic() - t2, elapsed_total)

    return {"news_review": result}
