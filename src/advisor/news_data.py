from __future__ import annotations

import logging
from datetime import datetime

import httpx
from tavily import TavilyClient
from tavily.errors import TimeoutError as TavilyTimeoutError

from advisor.config import config
from advisor.llm.retry import with_retry
from advisor.util import clip_text

log = logging.getLogger(__name__)


def web_finance_news_text(query: str, *, max_results: int) -> str:
    q = query.strip()
    if not q:
        raise ValueError("web news search requires a non-empty query")

    if config.search.provider == "tavily":
        return tavily_news_search(q, max_results)
    elif config.search.provider == "searxng":
        return searxng_news_search(q, max_results)
    else:
        raise ValueError(
            f"unknown search provider {config.search.provider!r}; expected 'tavily' or 'searxng'"
        )


def news_date(raw: object) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text


def format_news_items(items: list[dict]) -> str:
    trunc = config.search.body_truncation_chars
    lines: list[str] = []
    for item in items:
        title = item["title"] or ""
        body = clip_text(item["body"] or "", trunc)
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

    return with_retry(
        attempt,
        label=f"SearXNG GET category={category}",
        attempts=config.search.provider_max_attempts,
        delay=config.search.provider_backoff_seconds,
        retry_on=httpx.TransportError,
    )


def searxng_news_search(query: str, max_results: int) -> str:
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
    api_key = config.search.tavily_api_key.strip()
    if not api_key:
        raise RuntimeError("search provider is 'tavily' but search.tavily_api_key is empty")

    log.info("web news search via Tavily")

    def attempt() -> list[dict]:
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query,
            search_depth="basic",
            topic=config.search.tavily_topic,
            days=config.search.tavily_days,
            max_results=max_results,
            timeout=config.search.request_timeout_seconds,
        )
        return response.get("results") or []

    results = with_retry(
        attempt,
        label=f"Tavily search for {query!r}",
        attempts=config.search.provider_max_attempts,
        delay=config.search.provider_backoff_seconds,
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
