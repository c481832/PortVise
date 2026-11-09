from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx
from tavily import TavilyClient
from tavily.errors import TimeoutError as TavilyTimeoutError

from advisor.config import config
from advisor.llm.retry import with_retry
from advisor.util import clip_text

log = logging.getLogger(__name__)

NO_RESULTS_PREFIX = "No web news results for:"


def has_news_results(text: str) -> bool:
    return bool(text) and not text.startswith(NO_RESULTS_PREFIX)


def ticker_news_query(ticker: str, name: str) -> str:
    symbol = ticker.strip().upper()
    company = name.strip()
    if not symbol:
        raise ValueError("ticker news query requires a ticker")
    if not company or company.upper() == symbol:
        raise ValueError(f"ticker news query for {symbol} requires a company name")
    return f"latest news for {company} ({symbol})"


def web_finance_news_text(query: str, *, max_results: int) -> str:
    q = query.strip()
    if not q:
        raise ValueError("web news search requires a non-empty query")

    if config.search.provider == "tavily":
        items = tavily_news_items(q, max_results)
    elif config.search.provider == "searxng":
        items = searxng_news_items(q)
    else:
        raise ValueError(
            f"unknown search provider {config.search.provider!r}; expected 'tavily' or 'searxng'"
        )

    if not items:
        return f"{NO_RESULTS_PREFIX} {q}"
    return format_news_items(items[:max_results])


def parse_published(raw: object) -> datetime | None:
    text = str(raw or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def format_news_items(items: list[dict]) -> str:
    trunc = config.search.body_truncation_chars
    lines: list[str] = []
    for item in items:
        parsed = parse_published(item["published"])
        published = parsed.date().isoformat() if parsed else str(item["published"] or "").strip()
        title = item["title"] or ""
        body = clip_text(item["body"] or "", trunc)
        url = item["url"] or ""
        head = f"• [{published}] {title}" if published else f"• {title}"
        if url:
            head += f" — {url}"
        lines.append(head)
        if body:
            lines.append(f"  {body}")
    return "\n".join(lines)


def searxng_fetch(base_url: str, query: str) -> list[dict]:
    url = f"{base_url}/search"
    params = {"q": query, "format": "json", "categories": "news"}
    headers = {"User-Agent": config.search.user_agent, "Accept": "application/json"}

    def attempt() -> list[dict]:
        with httpx.Client(timeout=config.search.request_timeout_seconds, trust_env=False) as client:
            response = client.get(url, params=params, headers=headers)
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"SearXNG did not return JSON at {url} (enable the JSON format in settings.yml)"
            ) from exc
        if not isinstance(payload, dict):
            raise RuntimeError("SearXNG returned non-object JSON")
        for name, reason in payload.get("unresponsive_engines") or []:
            log.warning("SearXNG engine %s unresponsive: %s", name, reason)
        return payload.get("results") or []

    return with_retry(
        attempt,
        label="SearXNG GET category=news",
        attempts=config.search.provider_max_attempts,
        delay=config.search.provider_backoff_seconds,
        retry_on=httpx.TransportError,
    )


def recent_news_items(items: list[dict], *, days: int) -> list[dict]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    dated: list[tuple[datetime, dict]] = []
    undated: list[dict] = []
    for item in items:
        published = parse_published(item["published"])
        if published is None:
            undated.append(item)
        elif published >= cutoff:
            dated.append((published, item))
    dated.sort(key=lambda pair: pair[0], reverse=True)
    log.info(
        "SearXNG news: %d raw, %d within %dd, %d undated",
        len(items),
        len(dated),
        days,
        len(undated),
    )
    return [item for _, item in dated] + undated


def searxng_news_items(query: str) -> list[dict]:
    base_url = config.search.searxng_url.strip().rstrip("/")
    if not base_url:
        raise RuntimeError("search provider is 'searxng' but search.searxng_url is empty")
    log.info("web news search via SearXNG at %s", base_url)

    items = [
        {
            "title": r.get("title"),
            "body": r.get("content"),
            "published": r.get("publishedDate") or r.get("pubdate"),
            "url": r.get("url"),
        }
        for r in searxng_fetch(base_url, query)
    ]
    return recent_news_items(items, days=config.search.searxng_news_days)


def tavily_news_items(query: str, max_results: int) -> list[dict]:
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
    return [
        {
            "title": r.get("title"),
            "body": r.get("content"),
            "published": r.get("published_date"),
            "url": r.get("url"),
        }
        for r in results
    ]
