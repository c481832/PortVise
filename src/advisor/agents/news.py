from __future__ import annotations

import logging
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait

from langchain_core.messages import HumanMessage, SystemMessage

from advisor.config import config
from advisor.llm.context import raise_if_review_stopped, report_step
from advisor.llm.structured import invoke_structured
from advisor.news_data import web_finance_news_text
from advisor.prompts import news_system_prompt
from advisor.prompts.news import news_focus_to_text
from advisor.prompts.portfolio import portfolio_to_text
from advisor.schemas.news import NewsReview
from advisor.schemas.planner import NewsFocus
from advisor.schemas.state import GraphState

log = logging.getLogger(__name__)


def collect_planned_queries(focus: NewsFocus) -> list[str]:
    out: list[str] = []
    pq = [q.strip() for q in focus.portfolio_search_queries if q and q.strip()]
    out.extend(pq)

    for pg in focus.position_goals:
        lq = (pg.latest_news_query or "").strip()
        if lq:
            out.append(lq)

    if not out:
        raise RuntimeError(
            "collect_planned_queries produced no queries; planner must populate either "
            "portfolio_search_queries or per-position latest_news_query."
        )
    return list(dict.fromkeys(out))


def run_planned_news_searches(focus: NewsFocus) -> str:
    queries = collect_planned_queries(focus)
    n = len(queries)
    max_workers = max(1, min(n, config.search.concurrent_requests))
    log.info(
        "news web search: %d planned queries (max concurrency=%d, running all before summary)",
        n,
        max_workers,
    )
    report_step("news", 1, f"Searching {n} news sources…")

    def search_one(i: int, q: str) -> tuple[int, str, str, float]:
        raise_if_review_stopped()
        t0 = time.monotonic()
        out = web_finance_news_text(q, max_results=config.search.default_max_results)
        return i, q, out, time.monotonic() - t0

    results: list[str] = [""] * n
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="news-search") as pool:
        pending: set[Future[tuple[int, str, str, float]]] = {
            pool.submit(search_one, i, q) for i, q in enumerate(queries)
        }
        while pending:
            raise_if_review_stopped()
            done, pending = wait(pending, timeout=0.25, return_when=FIRST_COMPLETED)
            for future in done:
                i, q, out, elapsed = future.result()
                results[i] = out
                log.info(
                    "news web search query %d/%d %r → %d chars in %.1fs",
                    i + 1,
                    n,
                    q,
                    len(out),
                    elapsed,
                )

    research = "\n\n---\n\n".join(
        f"### Query: {q}\n{out}" for q, out in zip(queries, results, strict=True)
    )
    report_step("news", 2, f"Combined {n} search result sets…")

    log.info(
        "news web search complete: %d queries executed, %d chars total",
        n,
        len(research),
    )
    return research


def build_news_prompt(state: GraphState) -> str:
    portfolio = state["portfolio"]
    parts: list[str] = []
    focus = state.get("news_focus")
    if focus is not None:
        parts.append(news_focus_to_text(focus))
    parts.append(portfolio_to_text(portfolio))
    return "\n\n".join(parts)


def news_collector_node(state: GraphState) -> dict:
    t_start = time.monotonic()
    log.info("news collector started (parallel with data)")
    focus = state["news_focus"]
    if focus is None:
        raise RuntimeError("news collector requires news_focus from the planner")
    report_step("news", 0, "Preparing planned news searches…")
    collected_text = run_planned_news_searches(focus)
    log.info("news collector done in %.1fs", time.monotonic() - t_start)
    return {"news_collector_text": collected_text}


def news_summary_node(state: GraphState) -> dict:
    t_start = time.monotonic()
    log.info("news summary started")
    user_content = build_news_prompt(state)
    research = (state.get("news_collector_text") or "").strip()
    if not research:
        raise RuntimeError(
            "news_collector_text is empty: refusing to summarize "
            "without real tool-gathered news data"
        )
    summary_body = f"{user_content}\n\n=== TOOL-GATHERED RESEARCH ===\n{research}"

    report_step("news", 3, "Preparing briefing prompt from search results…")
    report_step("news", 4, "Summarising retrieved news findings…")

    log.info("calling summary LLM")
    t2 = time.monotonic()
    result: NewsReview = invoke_structured(  # type: ignore[assignment]
        NewsReview,
        [SystemMessage(content=news_system_prompt()), HumanMessage(content=summary_body)],
        agent="news_summary",
        max_tokens=config.llm.structured_max_tokens,
        temperature=config.llm.structured_temperature,
        use_agent_model=True,
    )
    elapsed_total = time.monotonic() - t_start
    log.info("summary done in %.1fs — node total %.1fs", time.monotonic() - t2, elapsed_total)

    return {"news_review": result}
