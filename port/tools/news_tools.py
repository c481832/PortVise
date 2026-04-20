"""News search tools: Tavily web news, else DuckDuckGo, else optional local SearXNG."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
import warnings

from langchain_core.tools import tool

from port.config import settings

log = logging.getLogger(__name__)

_SEARX_UA = "port/0.1 (news-tools)"


def _web_finance_news_text(query: str, max_results: int = 8) -> str:
    """Web news: Tavily with ``TAVILY_API_KEY``; else DuckDuckGo, else SearXNG if configured."""
    q = query.strip()
    if not q:
        return "Empty query."
    if settings.tavily_api_key.strip():
        return _tavily_search(q, max_results)

    ddg = _try_ddg_news_search(q, max_results)
    if ddg is not None:
        return ddg

    base = (getattr(settings, "searxng_url", None) or "").strip().rstrip("/")
    if not base:
        return (
            "Web news search failed: DuckDuckGo is unavailable and SearXNG is disabled "
            "(set SEARXNG_URL to your local instance, or remove SEARXNG_URL from .env to use the "
            "default http://127.0.0.1:8888)."
        )

    log.info(
        "web news search via SearXNG at %s (DuckDuckGo unavailable)",
        base,
    )
    return _searxng_news_search(q, max_results, base)


def _try_ddg_news_search(query: str, max_results: int) -> str | None:
    """Return formatted results, ``None`` if DuckDuckGo failed (caller may try SearXNG)."""
    try:
        from duckduckgo_search import DDGS

        log.info("web news search via DuckDuckGo (TAVILY_API_KEY unset)")
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
        return None


def _searxng_fetch_json(
    base_url: str, query: str, *, category: str
) -> tuple[dict | None, str | None]:
    """GET SearXNG ``/search`` JSON. Returns ``(data, None)`` or ``(None, error_message)``."""
    params = urllib.parse.urlencode(
        {
            "q": query,
            "format": "json",
            "categories": category,
            "time_range": "week",
        }
    )
    url = f"{base_url}/search?{params}"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": _SEARX_UA,
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
        data = json.loads(raw)
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        log.warning("SearXNG GET failed category=%s url=%s err=%s", category, url, exc)
        return None, str(exc)
    if not isinstance(data, dict):
        log.warning("SearXNG returned non-object JSON for category=%s", category)
        return None, "invalid JSON response"
    return data, None


def _format_searx_results(results: list, max_results: int) -> str:
    lines: list[str] = []
    for r in results[:max_results]:
        title = r.get("title") or ""
        body = (r.get("content") or "")[:400]
        pub_raw = r.get("publishedDate") or r.get("pubdate") or ""
        published = str(pub_raw)[:10]
        src = r.get("url", "")
        head = f"• [{published}] {title}" if published else f"• {title}"
        if src:
            head += f" — {src}"
        lines.append(head)
        if body:
            lines.append(f"  {body}")
    return "\n".join(lines)


def _searxng_news_search(query: str, max_results: int, base_url: str) -> str:
    """SearXNG JSON API: ``news`` then ``general`` if empty, past week."""
    for category in ("news", "general"):
        data, err = _searxng_fetch_json(base_url, query, category=category)
        if err:
            return (
                f"Web news search failed: DuckDuckGo unavailable; SearXNG error ({category}): {err}"
            )
        results = data.get("results") or [] if data else []
        if results:
            log.info("SearXNG category=%s returned %d result(s)", category, len(results))
            return _format_searx_results(results, max_results)
        if category == "news":
            log.info("SearXNG category=news returned 0 results — retrying general")

    return f"No web news results for: {query}"


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

    Backend: Tavily when ``TAVILY_API_KEY`` is set; otherwise DuckDuckGo, then ``SEARXNG_URL``
    (local SearXNG) if DuckDuckGo fails. Use for Fed/policy, rates, sectors, commodities,
    geopolitics, issuer-specific or thematic queries, and per-ticker developments when you phrase
    the query with the company or symbol."""
    return _web_finance_news_text(query)


NEWS_TOOLS = [search_web_finance_news]
