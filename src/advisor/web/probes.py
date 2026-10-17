from __future__ import annotations

import asyncio
import re

import httpx
from fastapi import HTTPException

from advisor.config import config
from advisor.util import clip_text

BASE_URL_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)


def short_error(exc: Exception) -> str:
    return (
        clip_text(str(exc).strip(), config.truncation.error_detail_chars) or exc.__class__.__name__
    )


def validate_base_url(url: str, label: str) -> None:
    if not BASE_URL_SCHEME_RE.match(url):
        raise HTTPException(
            status_code=400,
            detail=f"{label} API URL must start with http:// or https:// (got {url!r})",
        )


async def probe_llm_endpoint(*, base_url: str, model: str, api_key: str | None) -> None:
    validate_base_url(base_url, "Endpoint")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    headers["Content-Type"] = "application/json"
    try:
        async with httpx.AsyncClient(
            timeout=config.server.llm_test_timeout_seconds, trust_env=False
        ) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
                    "temperature": config.server.llm_test_temperature,
                    "max_tokens": config.server.llm_test_max_tokens,
                },
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Endpoint connection failed: {exc}") from exc

    if response.status_code >= 400:
        detail = (
            clip_text(response.text.strip(), config.truncation.error_detail_chars)
            or response.reason_phrase
        )
        raise HTTPException(
            status_code=502,
            detail=f"Endpoint returned HTTP {response.status_code}: {detail}",
        )
    try:
        response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502, detail="Endpoint test message did not return JSON"
        ) from exc


async def probe_searxng(base_url: str) -> None:
    validate_base_url(base_url, "SearXNG")
    params = {"q": "market", "format": "json", "categories": "news"}
    headers = {"User-Agent": config.search.user_agent, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            timeout=config.search.request_timeout_seconds, trust_env=False
        ) as client:
            response = await client.get(
                f"{base_url.rstrip('/')}/search", params=params, headers=headers
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502, detail=f"SearXNG unreachable: {short_error(exc)}"
        ) from exc
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502, detail=f"SearXNG returned HTTP {response.status_code}."
        )
    try:
        response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502, detail="SearXNG did not return JSON (enable the JSON format)."
        ) from exc


async def probe_tavily(api_key: str) -> None:
    from tavily import TavilyClient

    def call() -> None:
        TavilyClient(api_key=api_key).search("market news", max_results=1, topic="news")

    try:
        await asyncio.wait_for(
            asyncio.to_thread(call), timeout=config.search.request_timeout_seconds
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Tavily key rejected: {short_error(exc)}"
        ) from exc
