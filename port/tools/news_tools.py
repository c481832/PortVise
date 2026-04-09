"""News search tools: Tavily web news, with DuckDuckGo when no API key."""

from __future__ import annotations

import logging
import warnings

from langchain_core.tools import tool

from port.config import settings
from port.portfolio import Portfolio

log = logging.getLogger(__name__)


def _web_finance_news_text(query: str, max_results: int = 8) -> str:
    """Web news: Tavily when ``TAVILY_API_KEY`` is set, else DuckDuckGo news (past week)."""
    q = query.strip()
    if not q:
        return "Empty query."
    if settings.tavily_api_key.strip():
        return _tavily_search(q, max_results)
    return _ddg_news_search(q, max_results)


def _ddg_news_search(query: str, max_results: int) -> str:
    try:
        from duckduckgo_search import DDGS

        log.debug("web news search via DuckDuckGo (TAVILY_API_KEY unset)")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            with DDGS() as ddgs:
                raw = ddgs.news(query, timelimit="w", max_results=max_results)
        if not raw:
            return f"No web news results for: {query}"
        lines: list[str] = []
        for r in raw:
            title = r.get("title") or ""
            body = (r.get("body") or "")[:400]
            published = (r.get("date") or "")[:10]
            src = r.get("url", "")
            head = f"• [{published}] {title}" if published else f"• {title}"
            if src:
                head += f" — {src}"
            lines.append(head)
            if body:
                lines.append(f"  {body}")
        return "\n".join(lines)
    except Exception as exc:
        log.warning("DuckDuckGo news search failed for %r: %s", query, exc)
        return f"Web news search failed: {exc}"


def _tavily_search(query: str, max_results: int) -> str:
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=settings.tavily_api_key)
        response = client.search(
            query,
            search_depth="basic",
            topic="news",
            days=7,
            max_results=max_results,
        )
        results = response.get("results") or []
        if not results:
            return f"No web news results for: {query}"
        lines: list[str] = []
        for r in results:
            title = r.get("title") or ""
            content = (r.get("content") or "")[:400]
            published = (r.get("published_date") or "")[:10]
            src = r.get("url", "")
            head = f"• [{published}] {title}" if published else f"• {title}"
            if src:
                head += f" — {src}"
            lines.append(head)
            if content:
                lines.append(f"  {content}")
        return "\n".join(lines)
    except Exception as exc:
        log.warning("Tavily search failed for %r: %s", query, exc)
        return f"Web news search failed: {exc}"


@tool
def search_web_finance_news(query: str) -> str:
    """Search general financial / macro news on the web (past week).

    Backend: Tavily when ``TAVILY_API_KEY`` is set; otherwise DuckDuckGo news (no API key).
    Use for Fed/policy, rates, sectors, commodities, geopolitics, issuer-specific or thematic
    queries, and per-ticker developments when you phrase the query with the company or symbol."""
    return _web_finance_news_text(query)


NEWS_TOOLS = [search_web_finance_news]


def fallback_news_gather(portfolio: Portfolio) -> str:
    """Deterministic fetch when the tool-calling model does not invoke tools."""
    goal = (portfolio.context_note or "").strip()
    macro_q = (
        f"stock market macro Federal Reserve rates {goal}"
        if goal
        else "US stock market macro news week"
    )
    web_result = _web_finance_news_text(macro_q, max_results=6)
    return "### Macro / general (web)\n" + web_result
