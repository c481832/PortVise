from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from port.tools.news_tools import _web_finance_news_text


def _config(
    *, provider: str = "searxng", tavily_api_key: str = "", searxng_url: str = ""
) -> SimpleNamespace:
    return SimpleNamespace(
        search=SimpleNamespace(
            provider=provider,
            tavily_api_key=tavily_api_key,
            searxng_url=searxng_url,
            tavily_topic="news",
            tavily_days=7,
            provider_max_attempts=1,
            provider_backoff_seconds=0.0,
            body_truncation_chars=500,
            request_timeout_seconds=1.0,
            user_agent="test",
        )
    )


def test_web_news_empty_query() -> None:
    result = _web_finance_news_text("", max_results=5)
    assert result == "Empty query."


def test_searxng_provider_without_url_reports_misconfig() -> None:
    with patch("port.tools.news_tools.config", _config(provider="searxng", searxng_url="")):
        result = _web_finance_news_text("q", max_results=5)
    assert "failed" in result.lower()
    assert "searxng" in result.lower()


def test_tavily_provider_without_key_reports_misconfig() -> None:
    with patch("port.tools.news_tools.config", _config(provider="tavily", tavily_api_key="")):
        result = _web_finance_news_text("q", max_results=5)
    assert "failed" in result.lower()
    assert "tavily" in result.lower()


def test_searxng_news_empty_then_general() -> None:
    """SearXNG ``news`` can be empty; we retry ``general``."""

    def _resp(payload: bytes) -> MagicMock:
        m = MagicMock()
        m.read.return_value = payload
        m.__enter__.return_value = m
        m.__exit__.return_value = None
        return m

    empty = b'{"results":[]}'
    full = json.dumps(
        {
            "results": [
                {
                    "title": "General hit",
                    "content": "Body.",
                    "url": "https://example.com/g",
                    "publishedDate": "2026-04-03",
                }
            ]
        }
    ).encode()

    with (
        patch(
            "port.tools.news_tools.config",
            _config(provider="searxng", searxng_url="http://127.0.0.1:9999"),
        ),
        patch(
            "port.tools.news_tools.urllib.request.urlopen",
            side_effect=[_resp(empty), _resp(full)],
        ),
    ):
        result = _web_finance_news_text("query", max_results=5)
    assert "General hit" in result


def test_searxng_formats_results() -> None:
    payload = json.dumps(
        {
            "results": [
                {
                    "title": "SearX headline",
                    "content": "Macro body text.",
                    "url": "https://example.com/sx",
                    "publishedDate": "2026-04-02T00:00:00",
                }
            ]
        }
    ).encode()
    mock_http = MagicMock()
    mock_http.read.return_value = payload
    mock_http.__enter__.return_value = mock_http
    mock_http.__exit__.return_value = None
    with (
        patch(
            "port.tools.news_tools.config",
            _config(provider="searxng", searxng_url="http://127.0.0.1:9999"),
        ),
        patch("port.tools.news_tools.urllib.request.urlopen", return_value=mock_http),
    ):
        result = _web_finance_news_text("Fed outlook", max_results=5)
    assert "SearX headline" in result
    assert "2026-04-02" in result


def test_tavily_provider_formats_results() -> None:
    mock_client = MagicMock()
    mock_client.search.return_value = {
        "results": [
            {
                "title": "Fed holds rates",
                "content": "The Fed decided to hold rates steady.",
                "published_date": "2026-04-01",
                "url": "https://example.com/fed",
            }
        ]
    }
    with (
        patch(
            "port.tools.news_tools.config",
            _config(provider="tavily", tavily_api_key="fake-key"),
        ),
        patch("port.tools.news_tools.TavilyClient", return_value=mock_client),
    ):
        result = _web_finance_news_text("Fed rates", max_results=5)
    assert "Fed holds rates" in result
    assert "2026-04-01" in result


def test_tavily_provider_no_results() -> None:
    mock_client = MagicMock()
    mock_client.search.return_value = {"results": []}
    with (
        patch(
            "port.tools.news_tools.config",
            _config(provider="tavily", tavily_api_key="fake-key"),
        ),
        patch("port.tools.news_tools.TavilyClient", return_value=mock_client),
    ):
        result = _web_finance_news_text("obscure query", max_results=5)
    assert "No web news results" in result


def test_tavily_provider_exception() -> None:
    with (
        patch(
            "port.tools.news_tools.config",
            _config(provider="tavily", tavily_api_key="fake-key"),
        ),
        patch("port.tools.news_tools.TavilyClient", side_effect=Exception("timeout")),
    ):
        result = _web_finance_news_text("query", max_results=5)
    assert "failed" in result.lower()
