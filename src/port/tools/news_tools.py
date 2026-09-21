"""News search tool: a single configured provider — Tavily API or self-hosted SearXNG.

Exactly one provider runs per call, selected by ``config.search.provider``. There is no
fallback chain and no error swallowing: transport failures are retried, everything else
fails immediately, and the exception reaches the caller. The only non-exceptional "empty"
answer is a provider that responds normally with zero articles.
"""

from __future__ import annotations

import logging
from datetime import datetime

import httpx
from tavily import TavilyClient
from tavily.errors import TimeoutError as TavilyTimeoutError

from port.config import config
from port.llm.retry import with_retry

log = logging.getLogger(__name__)


def web_finance_news_text(query: str, *, max_results: int) -> str:
    """Fetch web news from the configured provider (``config.search.provider``).

    Returns rendered bullet lines, or a "no results" sentence when the provider answered
    with nothing. Misconfiguration and provider failures raise.
    """
    q = query.strip()
    if not q:
        raise ValueError("web news search requires a non-empty query")

    if config.search.provider == "tavily":
        return tavily_news_search(q, max_results)
    return searxng_news_search(q, max_results)


def news_date(raw: object) -> str:
    """Normalize a provider timestamp to ``YYYY-MM-DD``.

    Providers disagree on format, so anything non-ISO is passed through verbatim rather
    than truncated into a misleading date.
    """
    text = str(raw or "").strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text


def format_news_items(items: list[dict]) -> str:
    """Render normalized news items (keys: ``title``, ``body``, ``published``, ``url``)."""
    trunc = config.search.body_truncation_chars
    lines: list[str] = []
    for item in items:
        title = item["title"] or ""
        body = (item["body"] or "")[:trunc]
        published = item["published"]
        url = item["url"] or ""
        head = f"• [{published}] {title}" if published else f"• {title}"
        if url:
            head += f" — {url}"
        lines.append(head)
        if body:
            lines.append(f"  {body}")
    return "\n".join(lines)


def searxng_fetch(base_url: str, query: str, *, category: str) -> list[dict]:
    """GET SearXNG ``/search`` JSON for one category, past week."""
    url = f"{base_url}/search"
    params = {"q": query, "format": "json", "categories": category, "time_range": "week"}
    headers = {"User-Agent": config.search.user_agent, "Accept": "application/json"}

    def attempt() -> list[dict]:
        with httpx.Client(timeout=config.search.request_timeout_seconds, trust_env=False) as client:
            response = client.get(url, params=params, headers=headers)
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"SearXNG did not return JSON for category={category} at {url} "
                "(enable the JSON format in settings.yml)"
            ) from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"SearXNG returned non-object JSON for category={category}")
        return payload.get("results") or []

    def on_attempt(att: int, exc: Exception, delay: float) -> None:
        log.warning(
            "SearXNG GET attempt %d/%d failed category=%s err=%s — retrying in %.1fs",
            att,
            config.search.provider_max_attempts,
            category,
            exc,
            delay,
        )

    return with_retry(
        attempt,
        attempts=config.search.provider_max_attempts,
        base=config.search.provider_backoff_seconds,
        cap=config.search.provider_backoff_seconds,
        on_attempt=on_attempt,
        retry_on=httpx.TransportError,
    )


def searxng_news_search(query: str, max_results: int) -> str:
    """SearXNG JSON API: ``news`` category, then ``general`` if ``news`` came back empty."""
    base_url = config.search.searxng_url.strip().rstrip("/")
    if not base_url:
        raise RuntimeError("search provider is 'searxng' but search.searxng_url is empty")

    log.info("web news search via SearXNG at %s", base_url)
    for category in ("news", "general"):
        results = searxng_fetch(base_url, query, category=category)
        log.info("SearXNG category=%s returned %d result(s)", category, len(results))
        if not results:
            continue
        items = [
            {
                "title": r.get("title"),
                "body": r.get("content"),
                "published": news_date(r.get("publishedDate") or r.get("pubdate")),
                "url": r.get("url"),
            }
            for r in results[:max_results]
        ]
        rendered = format_news_items(items)
        if category == "news":
            return rendered
        return f"(no dedicated news hits — general web results)\n{rendered}"

    return f"No web news results for: {query}"


def tavily_news_search(query: str, max_results: int) -> str:
    """Tavily search API, restricted to the configured topic and lookback window."""
    api_key = config.search.tavily_api_key.strip()
    if not api_key:
        raise RuntimeError("search provider is 'tavily' but search.tavily_api_key is empty")

    log.info("web news search via Tavily")

    def attempt() -> list[dict]:
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query,
            search_depth="basic",
            topic=config.search.tavily_topic,  # pyright: ignore[reportArgumentType]
            days=config.search.tavily_days,
            max_results=max_results,
            timeout=config.search.request_timeout_seconds,
        )
        return response.get("results") or []

    def on_attempt(att: int, exc: Exception, delay: float) -> None:
        log.warning(
            "Tavily search attempt %d/%d failed for %r: %s — retrying in %.1fs",
            att,
            config.search.provider_max_attempts,
            query,
            exc,
            delay,
        )

    results = with_retry(
        attempt,
        attempts=config.search.provider_max_attempts,
        base=config.search.provider_backoff_seconds,
        cap=config.search.provider_backoff_seconds,
        on_attempt=on_attempt,
        retry_on=(TavilyTimeoutError, OSError),
    )

    log.info("Tavily returned %d result(s)", len(results))
    if not results:
        return f"No web news results for: {query}"
    items = [
        {
            "title": r.get("title"),
            "body": r.get("content"),
            "published": news_date(r.get("published_date")),
            "url": r.get("url"),
        }
        for r in results[:max_results]
    ]
    return format_news_items(items)
