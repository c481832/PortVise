"""News search tools: Yahoo Finance headlines + Tavily web news."""

from __future__ import annotations

import logging

import yfinance as yf
from langchain_core.tools import tool

from port.config import settings
from port.portfolio import Portfolio

log = logging.getLogger(__name__)


def _yahoo_news_text(ticker: str, max_items: int = 10) -> str:
    """Fetch Yahoo Finance news for a symbol; returns formatted text or error string."""
    sym = ticker.strip().upper()
    if not sym:
        return "Invalid ticker."
    try:
        t = yf.Ticker(sym)
        raw = t.news or []
        if not raw:
            return f"No Yahoo Finance news items returned for {sym}."
        lines: list[str] = []
        for item in raw[:max_items]:
            title = item.get("title") or ""
            pub = item.get("publisher", "") or ""
            lines.append(f"• {title}" + (f" ({pub})" if pub else ""))
        return "\n".join(lines)
    except Exception as exc:
        log.warning("Yahoo news failed for %s: %s", sym, exc)
        return f"Yahoo Finance news fetch failed for {sym}: {exc}"


def _web_finance_news_text(query: str, max_results: int = 8) -> str:
    """Web news search — uses Tavily if TAVILY_API_KEY is set, otherwise DuckDuckGo."""
    q = query.strip()
    if not q:
        return "Empty query."
    if settings.tavily_api_key:
        return _tavily_search(q, max_results)
    return _ddg_search(q, max_results)


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


def _ddg_search(query: str, max_results: int) -> str:
    try:
        from duckduckgo_search import DDGS

        results = list(DDGS().news(query, max_results=max_results))
        if not results:
            return f"No web news results for: {query}"
        lines: list[str] = []
        for r in results:
            title = r.get("title") or ""
            body = (r.get("body") or "")[:400]
            date = (r.get("date") or "")[:10]
            src = r.get("url", "")
            head = f"• [{date}] {title}" if date else f"• {title}"
            if src:
                head += f" — {src}"
            lines.append(head)
            if body:
                lines.append(f"  {body}")
        return "\n".join(lines)
    except Exception as exc:
        log.warning("DuckDuckGo search failed for %r: %s", query, exc)
        return f"Web news search failed: {exc}"


@tool
def search_ticker_news(ticker: str) -> str:
    """Recent Yahoo Finance headlines for one stock or ETF (e.g. AAPL, MSFT, SPY).

    Use for company- or issuer-specific developments that may not appear in macro-only search."""
    return _yahoo_news_text(ticker)


@tool
def search_web_finance_news(query: str) -> str:
    """Search general financial / macro news on the web (past week).

    Use for Fed/policy, rates, sectors, commodities, geopolitics, or other themes not tied to one
    ticker."""
    return _web_finance_news_text(query)


NEWS_TOOLS = [search_ticker_news, search_web_finance_news]


def fallback_news_gather(portfolio: Portfolio) -> str:
    """Deterministic fetch when the tool-calling model does not invoke tools."""
    parts: list[str] = []
    for p in portfolio.positions:
        block = _yahoo_news_text(p.ticker)
        parts.append(f"### {p.ticker}\n{block}")
    goal = (portfolio.context_note or "").strip()
    macro_q = (
        f"stock market macro Federal Reserve rates {goal}"
        if goal
        else "US stock market macro news week"
    )
    web_result = _web_finance_news_text(macro_q, max_results=6)
    _err_markers = ("failed", "error", "no results", "connecterror")
    if not any(m in web_result.lower() for m in _err_markers):
        parts.append("### Macro / general (web)\n" + web_result)
    return "\n\n".join(parts)
