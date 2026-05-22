"""News agent — planned web searches for every query, then structured NewsReview from the LLM."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from port.agents.planner import build_news_focus
from port.config import config, invoke_structured, raise_if_review_stopped
from port.config import step_callback as _step_cb
from port.models import NewsReview
from port.portfolio import (
    Portfolio,
    news_focus_to_text,
    planned_news_tool_queries,
    portfolio_to_text,
)
from port.prompts import NEWS_SYSTEM_PROMPT
from port.tools.news_tools import _web_finance_news_text

if TYPE_CHECKING:
    from port.state import GraphState

log = logging.getLogger(__name__)


def _run_planned_news_searches(
    portfolio: Portfolio,
    focus,
    *,
    step_cb=None,
) -> tuple[str, int]:
    """Run a web news fetch for every planned query (no round cap)."""
    queries = planned_news_tool_queries(focus)
    n = len(queries)
    log.info("news web search: %d planned queries (running all before synthesis)", n)

    chunks: list[str] = []
    for i, q in enumerate(queries):
        raise_if_review_stopped()
        if step_cb:
            step_cb("news", 1, f"News search {i + 1}/{n}: {q}")
        t0 = time.monotonic()
        out = _web_finance_news_text(q, max_results=config.search.default_max_results)
        log.info(
            "news web search query %d/%d %r → %d chars in %.1fs",
            i + 1,
            n,
            q,
            len(out),
            time.monotonic() - t0,
        )
        chunks.append(f"### Query: {q}\n{out}")

    research = "\n\n---\n\n".join(chunks)
    if step_cb:
        step_cb("news", 2, f"Assembled {n} search result sets…")

    log.info(
        "news web search complete: %d queries executed, %d chars total",
        n,
        len(research),
    )
    return research, n


def _build_news_user_content(state: GraphState) -> str:
    """Synthesis phase: SEARCH PRIORITIES + portfolio context for NewsReview JSON."""
    portfolio = state["portfolio"]
    parts: list[str] = []
    focus = state.get("news_focus")
    if focus is not None:
        parts.append(news_focus_to_text(focus))
    parts.append(
        f"Prepare a market briefing for the following portfolio:\n\n{portfolio_to_text(portfolio)}"
    )
    return "\n\n".join(parts)


def news_research_node(state: GraphState) -> dict:
    """Run all planner web searches (sequential); runs in parallel with data_node."""
    t_start = time.monotonic()
    log.info("news research started (parallel with data)")
    portfolio = state["portfolio"]
    cb = _step_cb.get(None)
    focus = state.get("news_focus") or build_news_focus(state["portfolio"])
    if cb:
        cb("news", 0, "Preparing planned web searches…")
    tool_research, query_count = _run_planned_news_searches(portfolio, focus, step_cb=cb)
    log.info("news research done in %.1fs", time.monotonic() - t_start)
    return {
        "news_research_text": tool_research,
        "news_research_query_count": query_count,
    }


def news_synthesis_node(state: GraphState) -> dict:
    """Summarize retrieved news research into a structured portfolio briefing."""
    t_start = time.monotonic()
    log.info("news synthesis started")
    cb = _step_cb.get(None)
    user_content = _build_news_user_content(state)
    research = (state.get("news_research_text") or "").strip()
    if not research:
        raise RuntimeError(
            "news_research_text is empty: refusing to synthesize "
            "without real tool-gathered news data"
        )
    synthesis_body = f"{user_content}\n\n=== TOOL-GATHERED RESEARCH ===\n{research}"

    if cb:
        cb("news", 3, "Preparing briefing prompt from retrieved research…")
        cb("news", 4, "Synthesising retrieved news findings…")

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
