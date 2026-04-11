"""Planner node: search-query phase, then post-news downstream context (two graph invocations)."""

from __future__ import annotations

import contextlib
import logging
import time
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from port.agents.data import canonical_macro_indicator_ticker
from port.config import invoke_structured
from port.config import step_callback as _step_cb
from port.models import DownstreamContextPlan, NewsFocus, NewsPlannerResult, PositionGoalFocus
from port.portfolio import (
    Portfolio,
    market_data_to_text,
    news_focus_to_text,
    news_to_text,
    portfolio_to_text,
)
from port.prompts import CONTEXT_PLANNER_SYSTEM_PROMPT, PLANNER_SYSTEM_PROMPT

if TYPE_CHECKING:
    from port.state import GraphState

log = logging.getLogger(__name__)

_MAX_MACRO_QUERIES = 4
_MAX_PER_POSITION_THESIS_QUERIES = 2
_MAX_PER_POSITION_TICKER_QUERIES = 2
_MAX_QUERY_LEN = 220
_MAX_THESIS_WORDS_FALLBACK = 10


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
    out: list[str] = []
    seen: set[str] = set()
    for q in raw:
        s = (q or "").strip()
        if not s:
            continue
        if len(s) > _MAX_QUERY_LEN:
            s = s[:_MAX_QUERY_LEN]
        key = s.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= cap:
            break
    return out


def _merge_planner_result(focus: NewsFocus, plan: NewsPlannerResult) -> None:
    focus.portfolio_search_queries = _sanitize_queries(
        plan.portfolio_search_queries, cap=_MAX_MACRO_QUERIES
    )
    thesis_by: dict[str, list[str]] = {}
    ticker_by: dict[str, list[str]] = {}
    for pp in plan.position_plans:
        t = _norm_ticker(pp.ticker)
        if not t:
            continue
        thesis_by[t] = _sanitize_queries(
            pp.thesis_search_queries, cap=_MAX_PER_POSITION_THESIS_QUERIES
        )
        ticker_by[t] = _sanitize_queries(
            pp.ticker_search_queries, cap=_MAX_PER_POSITION_TICKER_QUERIES
        )

    for pg in focus.position_goals:
        t = _norm_ticker(pg.ticker)
        pg.thesis_search_queries = thesis_by.get(t, [])
        pg.ticker_search_queries = ticker_by.get(t, [])

    seen_m: set[str] = set()
    macro_out: list[str] = []
    for raw in plan.macro_indicator_tickers:
        c = canonical_macro_indicator_ticker(str(raw))
        if c and c not in seen_m:
            seen_m.add(c)
            macro_out.append(c)
    focus.macro_indicator_tickers = macro_out


def _heuristic_thesis_queries(ticker: str, thesis: str) -> list[str]:
    """When the model omits thesis-angle queries, build a minimal searchable string."""
    sym = (ticker or "").strip()
    if not sym:
        return []
    words = (thesis or "").split()
    if not words:
        return _sanitize_queries(
            [f"{sym} investment thesis sector catalysts"],
            cap=_MAX_PER_POSITION_THESIS_QUERIES,
        )
    chunk = " ".join(words[:_MAX_THESIS_WORDS_FALLBACK])
    if len(chunk) > 100:
        chunk = chunk[:100].rsplit(maxsplit=1)[0] or chunk[:100]
    return _sanitize_queries([f"{sym} {chunk}".strip()], cap=_MAX_PER_POSITION_THESIS_QUERIES)


def _heuristic_ticker_queries(ticker: str) -> list[str]:
    """When the model omits ticker/security queries, build minimal company/symbol news strings."""
    sym = (ticker or "").strip()
    if not sym:
        return []
    return _sanitize_queries(
        [f"{sym} stock company news earnings guidance week"],
        cap=_MAX_PER_POSITION_TICKER_QUERIES,
    )


def _fill_empty_position_queries(focus: NewsFocus) -> int:
    """Return count of positions where at least one fallback query list was applied."""
    filled = 0
    for pg in focus.position_goals:
        need_thesis = not pg.thesis_search_queries
        need_ticker = not pg.ticker_search_queries
        if need_thesis:
            pg.thesis_search_queries = _heuristic_thesis_queries(pg.ticker, pg.goal)
        if need_ticker:
            pg.ticker_search_queries = _heuristic_ticker_queries(pg.ticker)
        if need_thesis or need_ticker:
            filled += 1
    return filled


def _planner_search_queries_phase(state: GraphState) -> dict:
    t0 = time.monotonic()
    log.info("planner phase 1 (search queries) started")
    portfolio = state["portfolio"]
    focus = build_news_focus(portfolio)

    tickers = ", ".join(_norm_ticker(p.ticker) for p in portfolio.positions)
    human = (
        "Plan web news searches for the following portfolio.\n\n"
        f"{portfolio_to_text(portfolio)}\n\n"
        "Tickers (you MUST include one position_plans entry per symbol, each with "
        "1-2 non-empty thesis_search_queries AND 1-2 non-empty ticker_search_queries): "
        f"{tickers}\n\n"
        "Return a NewsPlannerResult: portfolio_search_queries (1-4 macro/context-wide only), "
        "position_plans (one row per ticker; thesis + ticker query lists never empty), "
        "macro_indicator_tickers (3-8 from SPY, QQQ, IWM, TLT, HYG, GLD, ^VIX, UUP, or [] for "
        "default all), brief_rationale."
    )
    messages = [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=human),
    ]

    cb = _step_cb.get(None)
    if cb:
        with contextlib.suppress(Exception):
            cb("planner", 0, "Planning news search queries…")

    try:
        plan: NewsPlannerResult = invoke_structured(  # type: ignore[assignment]
            NewsPlannerResult,
            messages,
            agent="planner",
            max_tokens=2048,
            temperature=0.2,
        )
        _merge_planner_result(focus, plan)
        if plan.brief_rationale.strip():
            log.info("planner rationale: %s", plan.brief_rationale.strip()[:500])
    except Exception as exc:
        log.warning("planner LLM failed — continuing with goals only (no planned queries): %s", exc)

    n_fallback = _fill_empty_position_queries(focus)
    if n_fallback:
        log.info(
            "planner: filled %d position(s) with heuristic thesis/ticker queries (model left gaps)",
            n_fallback,
        )

    n_macro = len(focus.portfolio_search_queries)
    n_with_q = sum(
        1 for pg in focus.position_goals if pg.thesis_search_queries or pg.ticker_search_queries
    )
    log.info(
        "planner phase 1 done in %.1fs — %d positions, %d macro queries, "
        "%d positions with per-ticker queries",
        time.monotonic() - t0,
        len(focus.position_goals),
        n_macro,
        n_with_q,
    )
    return {"news_focus": focus}


def _planner_downstream_context_phase(state: GraphState) -> dict:
    t0 = time.monotonic()
    log.info("planner phase 2 (downstream context) started")
    news = state["news_review"]
    if news is None:
        log.info("planner phase 2: no news_review — skipping")
        return {"downstream_context": None}

    portfolio = state["portfolio"]
    parts: list[str] = [
        "=== NEWS AGENT BRIEFING ===",
        "",
        news_to_text(news),
    ]
    focus = state.get("news_focus")
    if focus:
        parts.extend(["", news_focus_to_text(focus)])
    md = state.get("market_data")
    if md:
        parts.extend(["", market_data_to_text(md)])
    parts.extend(["", "=== PORTFOLIO (reference) ===", "", portfolio_to_text(portfolio)])
    human = "\n".join(parts)

    messages = [
        SystemMessage(content=CONTEXT_PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=human),
    ]

    cb = _step_cb.get(None)
    if cb:
        with contextlib.suppress(Exception):
            cb("planner", 1, "Planning downstream context from news briefing…")

    try:
        plan: DownstreamContextPlan = invoke_structured(  # type: ignore[assignment]
            DownstreamContextPlan,
            messages,
            agent="planner",
            max_tokens=3072,
            temperature=0.2,
        )
        if plan.brief_rationale.strip():
            log.info("planner phase 2 rationale: %s", plan.brief_rationale.strip()[:500])
    except Exception as exc:
        log.warning(
            "planner phase 2 LLM failed — parallel agents will use raw news context only: %s",
            exc,
        )
        return {"downstream_context": None}

    log.info("planner phase 2 done in %.1fs", time.monotonic() - t0)
    return {"downstream_context": plan}


def planner_node(state: GraphState) -> dict:
    """Phase 1: search queries. Phase 2: curated context (runs after news in the graph)."""
    if state.get("news_review") is None:
        return _planner_search_queries_phase(state)
    return _planner_downstream_context_phase(state)
