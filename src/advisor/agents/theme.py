from __future__ import annotations

import logging
import re
import time

from langchain_core.messages import HumanMessage, SystemMessage

from advisor.agents.base import build_analysis_prompt
from advisor.config import config
from advisor.llm.context import report_step
from advisor.llm.structured import invoke_structured
from advisor.prompts import theme_system_prompt
from advisor.schemas.state import GraphState
from advisor.schemas.theme import ThemeReview
from advisor.util import truncate_text

log = logging.getLogger(__name__)


def build_research_excerpt(state: GraphState) -> str:
    raw = (state.get("news_collector_text") or "").strip()
    if not raw:
        return ""
    excerpt = truncate_text(raw, config.prompts.theme.research_excerpt_max_chars)
    return f"=== RAW NEWS RESEARCH ===\n\n{excerpt}"


def parse_query_runs(raw_research: str) -> dict[str, str]:
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


def collect_position_queries(state: GraphState) -> list[tuple[str, str]]:
    focus = state.get("news_focus")
    if focus is None:
        return []
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for goal in focus.position_goals:
        ticker = goal.ticker.strip().upper()
        query = (goal.latest_news_query or "").strip()
        if not ticker or not query or query in seen:
            continue
        seen.add(query)
        out.append((ticker, query))
    return out


def build_per_ticker_research(state: GraphState) -> str:
    runs = collect_position_queries(state)
    if not runs:
        return ""
    by_query = parse_query_runs((state.get("news_collector_text") or "").strip())
    lines = [
        "=== PER-TICKER RESEARCH ===",
        "",
    ]
    item_max_chars = config.prompts.theme.per_ticker_item_max_chars
    for ticker, query in runs:
        excerpt = truncate_text(
            by_query.get(query, "(no research found for this query)").strip(),
            item_max_chars,
        )
        lines.append(f"• {ticker} | {query}")
        lines.extend(f"  {line}" for line in excerpt.splitlines())
        lines.append("")
    return truncate_text(
        "\n".join(lines).strip(),
        config.prompts.theme.per_ticker_research_max_chars,
    )


def theme_node(state: GraphState) -> dict:
    t0 = time.monotonic()
    log.info("started")
    report_step("theme", 0, "Extracting news research evidence…")
    research = build_research_excerpt(state)
    report_step("theme", 1, "Mapping per-ticker research to portfolio themes…")
    per_ticker = build_per_ticker_research(state)
    body = build_analysis_prompt(state)
    content = "\n\n".join([x for x in (research, per_ticker, body) if x])

    report_step("theme", 2, "Synthesising theme exposure review…")

    result: ThemeReview = invoke_structured(  # type: ignore[assignment]
        ThemeReview,
        [SystemMessage(content=theme_system_prompt()), HumanMessage(content=content)],
        agent="theme",
        max_tokens=config.llm.structured_max_tokens,
        temperature=config.llm.structured_temperature,
        use_agent_model=True,
    )
    log.info("done in %.1fs", time.monotonic() - t0)
    return {"theme_review": result}
