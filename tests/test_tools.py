from __future__ import annotations

from unittest.mock import MagicMock, patch

from port.tools.news_tools import (
    _web_finance_news_text,
    _yahoo_news_text,
    fallback_news_gather,
)


def test_yahoo_news_empty_ticker() -> None:
    result = _yahoo_news_text("")
    assert result == "Invalid ticker."


def test_yahoo_news_no_results() -> None:
    mock_ticker = MagicMock()
    mock_ticker.news = []
    with patch("port.tools.news_tools.yf.Ticker", return_value=mock_ticker):
        result = _yahoo_news_text("AAPL")
    assert "No Yahoo Finance news" in result


def test_yahoo_news_formats_headlines() -> None:
    mock_ticker = MagicMock()
    mock_ticker.news = [
        {"title": "Apple Earnings Beat", "publisher": "Reuters"},
        {"title": "New iPhone Model", "publisher": ""},
    ]
    with patch("port.tools.news_tools.yf.Ticker", return_value=mock_ticker):
        result = _yahoo_news_text("AAPL")
    assert "Apple Earnings Beat (Reuters)" in result
    assert "New iPhone Model" in result


def test_yahoo_news_exception() -> None:
    with patch("port.tools.news_tools.yf.Ticker", side_effect=Exception("network error")):
        result = _yahoo_news_text("AAPL")
    assert "failed" in result.lower()


def test_web_news_empty_query() -> None:
    result = _web_finance_news_text("")
    assert result == "Empty query."


def test_web_news_no_api_key() -> None:
    with patch("port.tools.news_tools.settings") as mock_settings:
        mock_settings.tavily_api_key = ""
        result = _web_finance_news_text("some query")
    assert "TAVILY_API_KEY not configured" in result


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
    mock_ticker = MagicMock()
    mock_ticker.news = [{"title": "AAPL news", "publisher": "Reuters"}]
    mock_client = MagicMock()
    mock_client.search.return_value = {"results": []}
    with (
        patch("port.tools.news_tools.yf.Ticker", return_value=mock_ticker),
        patch("port.tools.news_tools.settings") as mock_settings,
        patch("tavily.TavilyClient", return_value=mock_client),
    ):
        mock_settings.tavily_api_key = "fake-key"
        result = fallback_news_gather(example_portfolio)
    assert "AAPL" in result
    assert "AAPL news" in result
