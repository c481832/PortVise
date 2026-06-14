"""News search tool: a single configured provider — Tavily API or self-hosted SearXNG.

Exactly one provider runs per call, selected by ``config.search.provider``. There is no
fallback chain: if the chosen provider fails, the failure is reported as-is (the tool returns
an explanatory string for the agent rather than raising)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from tavily import TavilyClient

from port._retry import with_retry
from port.config import config

log = logging.getLogger(__name__)


def _web_finance_news_text(query: str, *, max_results: int) -> str:
    """Fetch web news from the configured provider (``config.search.provider``)."""
    q = query.strip()
    if not q:
        return "Empty query."

    provider = config.search.provider
    if provider == "tavily":
        if not config.search.tavily_api_key.strip():
            return "Web news search failed: provider is 'tavily' but no Tavily API key is set."
        log.info("web news search via Tavily")
        return _tavily_search(q, max_results)

    if provider == "searxng":
        base = config.search.searxng_url.strip().rstrip("/")
        if not base:
            return "Web news search failed: provider is 'searxng' but no SearXNG URL is set."
        log.info("web news search via SearXNG at %s", base)
        return _searxng_news_search(q, max_results, base)

    return f"Web news search misconfigured: unknown search provider {provider!r}."


def _format_news_items(items: list[dict]) -> str:
    """Render normalized news items (keys: ``title``, ``body``, ``published``, ``url``)."""
    trunc = config.search.body_truncation_chars
    lines: list[str] = []
    for item in items:
        title = item.get("title") or ""
        body = (item.get("body") or "")[:trunc]
        published = (item.get("published") or "")[:10]
        url = item.get("url") or ""
        head = f"• [{published}] {title}" if published else f"• {title}"
        if url:
            head += f" — {url}"
        lines.append(head)
        if body:
            lines.append(f"  {body}")
    return "\n".join(lines)


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

    def attempt() -> dict:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": config.search.user_agent,
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=config.search.request_timeout_seconds) as resp:
            raw = resp.read().decode()
        return json.loads(raw)

    def on_attempt(att: int, exc: Exception, delay: float) -> None:
        log.warning(
            "SearXNG GET attempt %d/%d failed category=%s err=%s — retrying",
            att,
            config.search.provider_max_attempts,
            category,
            exc,
        )

    try:
        data = with_retry(
            attempt,
            attempts=config.search.provider_max_attempts,
            base=config.search.provider_backoff_seconds,
            cap=config.search.provider_backoff_seconds,
            on_attempt=on_attempt,
            retry_on=(
                urllib.error.URLError,
                TimeoutError,
                OSError,
                UnicodeDecodeError,
                json.JSONDecodeError,
            ),
        )
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


def _searxng_news_search(query: str, max_results: int, base_url: str) -> str:
    """SearXNG JSON API: ``news`` then ``general`` if empty, past week."""
    for category in ("news", "general"):
        data, err = _searxng_fetch_json(base_url, query, category=category)
        if err:
            return f"Web news search failed: SearXNG error ({category}): {err}"
        results = data.get("results") or [] if data else []
        if results:
            log.info("SearXNG category=%s returned %d result(s)", category, len(results))
            items = [
                {
                    "title": r.get("title"),
                    "body": r.get("content"),
                    "published": str(r.get("publishedDate") or r.get("pubdate") or ""),
                    "url": r.get("url"),
                }
                for r in results[:max_results]
            ]
            return _format_news_items(items)
        if category == "news":
            log.info("SearXNG category=news returned 0 results — retrying general")

    return f"No web news results for: {query}"


def _tavily_search(query: str, max_results: int) -> str:
    def attempt() -> list:
        client = TavilyClient(api_key=config.search.tavily_api_key)
        response = client.search(
            query,
            search_depth="basic",
            topic=config.search.tavily_topic,
            days=config.search.tavily_days,
            max_results=max_results,
        )
        return response.get("results") or []

    def on_attempt(att: int, exc: Exception, delay: float) -> None:
        log.warning(
            "Tavily search attempt %d/%d failed for %r: %s — retrying",
            att,
            config.search.provider_max_attempts,
            query,
            exc,
        )

    try:
        results = with_retry(
            attempt,
            attempts=config.search.provider_max_attempts,
            base=config.search.provider_backoff_seconds,
            cap=config.search.provider_backoff_seconds,
            on_attempt=on_attempt,
        )
    except Exception as exc:
        log.warning("Tavily search failed for %r: %s", query, exc)
        return f"Web news search failed: {exc}"

    if not results:
        return f"No web news results for: {query}"
    items = [
        {
            "title": r.get("title"),
            "body": r.get("content"),
            "published": r.get("published_date") or "",
            "url": r.get("url"),
        }
        for r in results
    ]
    return _format_news_items(items)
