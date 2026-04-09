from __future__ import annotations

from unittest.mock import MagicMock, patch

from port.tools.news_tools import _web_finance_news_text, fallback_news_gather


def test_web_news_empty_query() -> None:
    result = _web_finance_news_text("")
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
        patch("port.tools.news_tools.settings") as mock_settings,
        patch("duckduckgo_search.DDGS", return_value=mock_ctx),
    ):
        mock_settings.tavily_api_key = ""
        result = _web_finance_news_text("some query")
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
        patch("port.tools.news_tools.settings") as mock_settings,
        patch("duckduckgo_search.DDGS", return_value=mock_ctx),
    ):
        mock_settings.tavily_api_key = ""
        result = _web_finance_news_text("q")
    assert "failed" in result.lower()


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
        patch("port.tools.news_tools.settings") as mock_settings,
        patch("tavily.TavilyClient", return_value=mock_client),
    ):
        mock_settings.tavily_api_key = "fake-key"
        result = _web_finance_news_text("Fed rates")
    assert "Fed holds rates" in result
    assert "2026-04-01" in result


def test_web_news_no_results() -> None:
    mock_client = MagicMock()
    mock_client.search.return_value = {"results": []}
    with (
        patch("port.tools.news_tools.settings") as mock_settings,
        patch("tavily.TavilyClient", return_value=mock_client),
    ):
        mock_settings.tavily_api_key = "fake-key"
        result = _web_finance_news_text("obscure query")
    assert "No web news results" in result


def test_web_news_exception() -> None:
    with (
        patch("port.tools.news_tools.settings") as mock_settings,
        patch("tavily.TavilyClient", side_effect=Exception("timeout")),
    ):
        mock_settings.tavily_api_key = "fake-key"
        result = _web_finance_news_text("query")
    assert "failed" in result.lower()


def test_fallback_news_gather(example_portfolio) -> None:
    mock_client = MagicMock()
    mock_client.search.return_value = {
        "results": [
            {
                "title": "Macro headline",
                "content": "Body",
                "published_date": "2026-04-01",
                "url": "https://example.com/x",
            }
        ]
    }
    with (
        patch("port.tools.news_tools.settings") as mock_settings,
        patch("tavily.TavilyClient", return_value=mock_client),
    ):
        mock_settings.tavily_api_key = "fake-key"
        result = fallback_news_gather(example_portfolio)
    assert "### Macro / general (web)" in result
    assert "Macro headline" in result
