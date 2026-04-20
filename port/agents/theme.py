"""Theme agent — portfolio seed + news evidence + LLM scoring (tightly coupled with News)."""

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from port.agents._base import build_analysis_prompt
from port.config import invoke_structured
from port.config import step_callback as _step_cb
from port.models import ThemeReview
from port.prompts import THEME_SYSTEM_PROMPT

if TYPE_CHECKING:
    from port.state import GraphState

log = logging.getLogger(__name__)

_RESEARCH_CAP = 14000
_PER_TICKER_CAP = 3000
_BLOCK_ITEM_CAP = 1300


def _truncate_block(text: str, cap: int) -> str:
    text = text.strip()
    if len(text) <= cap:
        return text
    return text[:cap] + "\n… (truncated)"


def _news_research_excerpt(state: GraphState) -> str:
    raw = (state.get("news_research_text") or "").strip()
    if not raw:
        return ""
    return f"=== RAW NEWS RESEARCH (evidence for theme scoring) ===\n\n{_truncate_block(raw, _RESEARCH_CAP)}"


def _parse_query_runs(raw_research: str) -> dict[str, str]:
    """Parse news agent query sections into {query: body} by `### Query:` headers."""
    raw = raw_research.strip()
    if not raw:
        return {}
    out: dict[str, str] = {}
    matches = list(re.finditer(r"(?m)^### Query:\s*(.+)$", raw))
    for i, match in enumerate(matches):
        query = match.group(1).strip()
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        body = re.sub(r"\n*\s*---\s*$", "", raw[body_start:body_end].strip(), flags=re.S).strip()
        if query and body:
            out[query] = body
    return out


def _line_item_queries(state: GraphState) -> list[tuple[str, str]]:
    focus = state.get("news_focus")
    if focus is None:
        return []
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for goal in focus.position_goals:
        ticker = (goal.ticker or "").strip().upper()
        query = (goal.latest_news_query or "").strip()
        if not ticker or not query or query in seen:
            continue
        seen.add(query)
        out.append((ticker, query))
    return out


def _per_ticker_research_block(state: GraphState) -> str:
    """Structure already-gathered research by ticker so the LLM can cross-reference holdings."""
    runs = _line_item_queries(state)
    if not runs:
        return ""
    by_query = _parse_query_runs((state.get("news_research_text") or "").strip())
    lines = [
        "=== PER-TICKER RESEARCH (use to detect shared narratives across holdings) ===",
        "",
    ]
    for ticker, query in runs:
        excerpt = _truncate_block(by_query.get(query, "(no research found for this query)"), _BLOCK_ITEM_CAP)
        lines.append(f"• {ticker} | {query}")
        lines.extend(f"  {line}" for line in excerpt.splitlines())
        lines.append("")
    return _truncate_block("\n".join(lines), _PER_TICKER_CAP)


def theme_node(state: GraphState) -> dict:
    t0 = time.monotonic()
    log.info("started")
    research = _news_research_excerpt(state)
    per_ticker = _per_ticker_research_block(state)
    body = build_analysis_prompt(state, curated_for="theme")
    content = "\n\n".join([x for x in (research, per_ticker, body) if x])

    _cb = _step_cb.get(None)
    if _cb:
        _cb("theme", 0, "Mapping portfolio themes to news evidence…")

    result: ThemeReview = invoke_structured(  # type: ignore[assignment]
        ThemeReview,
        [SystemMessage(content=THEME_SYSTEM_PROMPT), HumanMessage(content=content)],
        agent="theme",
    )
    log.info("done in %.1fs", time.monotonic() - t0)
    return {"theme_results": [result]}
