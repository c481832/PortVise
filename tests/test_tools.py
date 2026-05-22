from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from port.tools.news_tools import _web_finance_news_text


def _config(*, tavily_api_key: str = "", searxng_url: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        search=SimpleNamespace(
            tavily_api_key=tavily_api_key,
            searxng_url=searxng_url,
            duckduckgo_timelimit="w",
            duckduckgo_topic="news",
            duckduckgo_days=7,
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


def test_web_news_no_api_key_uses_duckduckgo() -> None:
    mock_ddgs = MagicMock()
    mock_ddgs.news.return_value = [
        {
            "date": "2026-04-01T12:00:00+00:00",
            "title": "DDG headline",
            "body": "Macro snippet text.",
            "url": "https://example.com/news",
        }
    ]
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_ddgs
    mock_ctx.__exit__.return_value = None
    with (
        patch("port.tools.news_tools.config", _config()),
        patch("port.tools.news_tools.DDGS", return_value=mock_ctx),
    ):
        result = _web_finance_news_text("some query", max_results=5)
    assert "DDG headline" in result
    assert "2026-04-01" in result
    mock_ddgs.news.assert_called_once()
    call_kw = mock_ddgs.news.call_args
    assert call_kw[0][0] == "some query"
    assert call_kw[1]["timelimit"] == "w"


def test_web_news_no_api_key_ddg_failure() -> None:
    mock_ddgs = MagicMock()
    mock_ddgs.news.side_effect = RuntimeError("rate limited")
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_ddgs
    mock_ctx.__exit__.return_value = None
    with (
        patch("port.tools.news_tools.config", _config()),
        patch("port.tools.news_tools.DDGS", return_value=mock_ctx),
    ):
        result = _web_finance_news_text("q", max_results=5)
    assert "failed" in result.lower()
    assert "searxng" in result.lower()


def test_web_news_ddg_failure_searxng_news_empty_then_general() -> None:
    """SearXNG ``news`` can be empty; we retry ``general``."""
    mock_ddgs = MagicMock()
    mock_ddgs.news.side_effect = RuntimeError("rate limited")
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_ddgs
    mock_ctx.__exit__.return_value = None

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
        patch("port.tools.news_tools.config", _config(searxng_url="http://127.0.0.1:9999")),
        patch("port.tools.news_tools.DDGS", return_value=mock_ctx),
        patch(
            "port.tools.news_tools.urllib.request.urlopen",
            side_effect=[_resp(empty), _resp(full)],
        ),
    ):
        result = _web_finance_news_text("query", max_results=5)
    assert "General hit" in result


def test_web_news_ddg_failure_falls_back_to_searxng() -> None:
    mock_ddgs = MagicMock()
    mock_ddgs.news.side_effect = RuntimeError("rate limited")
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_ddgs
    mock_ctx.__exit__.return_value = None
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
        patch("port.tools.news_tools.config", _config(searxng_url="http://127.0.0.1:9999")),
        patch("port.tools.news_tools.DDGS", return_value=mock_ctx),
        patch("port.tools.news_tools.urllib.request.urlopen", return_value=mock_http),
    ):
        result = _web_finance_news_text("Fed outlook", max_results=5)
    assert "SearX headline" in result
    assert "2026-04-02" in result


def test_web_news_formats_results() -> None:
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
        patch("port.tools.news_tools.config", _config(tavily_api_key="fake-key")),
        patch("port.tools.news_tools.TavilyClient", return_value=mock_client),
    ):
        result = _web_finance_news_text("Fed rates", max_results=5)
    assert "Fed holds rates" in result
    assert "2026-04-01" in result


def test_web_news_no_results() -> None:
    mock_client = MagicMock()
    mock_client.search.return_value = {"results": []}
    with (
        patch("port.tools.news_tools.config", _config(tavily_api_key="fake-key")),
        patch("port.tools.news_tools.TavilyClient", return_value=mock_client),
    ):
        result = _web_finance_news_text("obscure query", max_results=5)
    assert "No web news results" in result


def test_web_news_exception() -> None:
    with (
        patch("port.tools.news_tools.config", _config(tavily_api_key="fake-key")),
        patch("port.tools.news_tools.TavilyClient", side_effect=Exception("timeout")),
    ):
        result = _web_finance_news_text("query", max_results=5)
    assert "failed" in result.lower()
