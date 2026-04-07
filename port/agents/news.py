"""News agent — tool-assisted news search, then structured NewsReview from the LLM."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from port.config import make_llm
from port.config import step_callback as _step_cb
from port.models import NewsReview
from port.portfolio import Portfolio, market_data_to_text, news_focus_to_text, portfolio_to_text
from port.prompts import NEWS_SYSTEM_PROMPT, NEWS_TOOLS_SYSTEM_PROMPT
from port.tools.news_tools import NEWS_TOOLS, fallback_news_gather

if TYPE_CHECKING:
    from port.state import GraphState

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 3

_TOOLS_BY_NAME = {t.name: t for t in NEWS_TOOLS}


def _collect_tool_text(messages: list) -> str:
    chunks = [str(m.content) for m in messages if isinstance(m, ToolMessage)]
    return "\n\n---\n\n".join(chunks)


def _run_tool_research(user_content: str, portfolio: Portfolio, step_cb=None) -> str:
    log.info("starting tool research (max %d rounds)", MAX_TOOL_ROUNDS)
    llm = make_llm(fast=True, max_tokens=2048, temperature=0.2, agent="news_tools").bind_tools(
        NEWS_TOOLS
    )
    messages: list = [
        SystemMessage(content=NEWS_TOOLS_SYSTEM_PROMPT),
        HumanMessage(
            content=user_content
            + "\n\nUse the tools to gather additional recent news beyond any snapshot above."
        ),
    ]
    for round_idx in range(MAX_TOOL_ROUNDS):
        log.info("tool round %d/%d — calling fast LLM", round_idx + 1, MAX_TOOL_ROUNDS)
        try:
            if step_cb:
                step_cb("news", 0, f"Round {round_idx + 1}/{MAX_TOOL_ROUNDS} — searching news…")
        except Exception:
            pass
        t0 = time.monotonic()
        ai = llm.invoke(messages)
        log.info("fast LLM responded in %.1fs", time.monotonic() - t0)
        messages.append(ai)
        if not isinstance(ai, AIMessage) or not ai.tool_calls:
            log.info("LLM made no tool calls — ending research loop")
            break
        log.info(
            "LLM requested %d tool call(s): %s",
            len(ai.tool_calls),
            [tc.get("name") for tc in ai.tool_calls],
        )
        round_results: list[str] = []
        for tc in ai.tool_calls:
            name = tc.get("name", "")
            tid = tc.get("id") or ""
            args = tc.get("args") or {}
            tool_fn = _TOOLS_BY_NAME.get(name)
            t1 = time.monotonic()
            try:
                out = f"Unknown tool: {name}" if tool_fn is None else str(tool_fn.invoke(args))
            except Exception as exc:
                out = f"Tool error ({name}): {exc}"
            log.info(
                "tool %r args=%s → %d chars in %.1fs",
                name,
                args,
                len(out),
                time.monotonic() - t1,
            )
            if len(out) > 12000:
                out = out[:12000] + "\n… (truncated)"
            messages.append(ToolMessage(content=out, tool_call_id=tid))
            round_results.append(out)

        _err_markers = (
            "failed",
            "error",
            "no results",
            "no web news",
            "connecterror",
            "unavailable",
        )
        if round_results and all(any(m in r.lower() for m in _err_markers) for r in round_results):
            log.info("all tool calls failed/unavailable — stopping research early")
            break

    research = _collect_tool_text(messages)
    if not research.strip():
        log.info("no tool results collected — using fallback_news_gather")
        research = fallback_news_gather(portfolio)
    log.info("tool research complete (%d chars)", len(research))
    return research


def news_node(state: GraphState) -> dict:
    t_start = time.monotonic()
    log.info("started")

    portfolio = state["portfolio"]
    market_data = state["market_data"]
    focus = state["news_focus"]

    parts: list[str] = []
    if focus is not None:
        parts.append(news_focus_to_text(focus))
    parts.append(
        f"Prepare a market briefing for the following portfolio:\n\n{portfolio_to_text(portfolio)}"
    )
    if market_data:
        parts.append(market_data_to_text(market_data))
    user_content = "\n\n".join(parts)

    cb = _step_cb.get(None)
    tool_research = _run_tool_research(user_content, portfolio, step_cb=cb)
    synthesis_body = f"{user_content}\n\n=== TOOL-GATHERED RESEARCH ===\n{tool_research}"

    try:
        if cb:
            cb("news", 1, "Synthesising findings…")
    except Exception:
        pass

    log.info("calling synthesis LLM (max_tokens=8192)")
    t2 = time.monotonic()
    structured_llm = make_llm(max_tokens=8192, agent="news_synthesis").with_structured_output(
        NewsReview
    )

    result: NewsReview = structured_llm.invoke(  # type: ignore[assignment]
        [
            SystemMessage(content=NEWS_SYSTEM_PROMPT),
            HumanMessage(content=synthesis_body),
        ]
    )
    elapsed_total = time.monotonic() - t_start
    log.info("synthesis done in %.1fs — node total %.1fs", time.monotonic() - t2, elapsed_total)

    return {"news_review": result}
