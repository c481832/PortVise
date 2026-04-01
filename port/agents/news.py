"""News agent — tool-assisted news search, then structured NewsReview from the LLM."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from port.config import make_llm
from port.models import NewsReview
from port.portfolio import Portfolio, market_data_to_text, news_focus_to_text, portfolio_to_text
from port.prompts import NEWS_SYSTEM_PROMPT, NEWS_TOOLS_SYSTEM_PROMPT
from port.tools.news_tools import NEWS_TOOLS, fallback_news_gather

if TYPE_CHECKING:
    from port.state import GraphState

MAX_TOOL_ROUNDS = 8

_TOOLS_BY_NAME = {t.name: t for t in NEWS_TOOLS}


def _collect_tool_text(messages: list) -> str:
    chunks = [str(m.content) for m in messages if isinstance(m, ToolMessage)]
    return "\n\n---\n\n".join(chunks)


def _run_tool_research(user_content: str, portfolio: Portfolio) -> str:
    llm = make_llm(fast=True, max_tokens=2048, temperature=0.2).bind_tools(NEWS_TOOLS)
    messages: list = [
        SystemMessage(content=NEWS_TOOLS_SYSTEM_PROMPT),
        HumanMessage(
            content=user_content
            + "\n\nUse the tools to gather additional recent news beyond any snapshot above."
        ),
    ]
    for _ in range(MAX_TOOL_ROUNDS):
        ai = llm.invoke(messages)
        messages.append(ai)
        if not isinstance(ai, AIMessage) or not ai.tool_calls:
            break
        for tc in ai.tool_calls:
            name = tc.get("name", "")
            tid = tc.get("id") or ""
            args = tc.get("args") or {}
            tool_fn = _TOOLS_BY_NAME.get(name)
            try:
                out = f"Unknown tool: {name}" if tool_fn is None else str(tool_fn.invoke(args))
            except Exception as exc:
                out = f"Tool error ({name}): {exc}"
            if len(out) > 12000:
                out = out[:12000] + "\n… (truncated)"
            messages.append(ToolMessage(content=out, tool_call_id=tid))

    research = _collect_tool_text(messages)
    if not research.strip():
        research = fallback_news_gather(portfolio)
    return research


def news_node(state: GraphState) -> dict:
    portfolio = state["portfolio"]
    market_data = state["market_data"]
    focus = state["news_focus"]

    parts: list[str] = []
    if focus is not None:
        parts.append(news_focus_to_text(focus))
    parts.append(
        "Prepare a market briefing for the following portfolio:\n\n"
        f"{portfolio_to_text(portfolio)}"
    )
    if market_data:
        parts.append(market_data_to_text(market_data))
    user_content = "\n\n".join(parts)

    tool_research = _run_tool_research(user_content, portfolio)
    synthesis_body = f"{user_content}\n\n=== TOOL-GATHERED RESEARCH ===\n{tool_research}"

    llm = make_llm(max_tokens=4096)
    structured_llm = llm.with_structured_output(NewsReview)

    result: NewsReview = structured_llm.invoke(  # type: ignore[assignment]
        [
            SystemMessage(content=NEWS_SYSTEM_PROMPT),
            HumanMessage(content=synthesis_body),
        ]
    )

    return {"news_review": result}
