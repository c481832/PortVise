"""News search tools: Yahoo Finance headlines + DuckDuckGo web news."""

from __future__ import annotations

import logging

import yfinance as yf
from langchain_core.tools import tool

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
    """DuckDuckGo news search; returns formatted text or error string."""
    q = query.strip()
    if not q:
        return "Empty query."
    try:
        from duckduckgo_search import DDGS

        lines: list[str] = []
        with DDGS() as ddgs:
            for r in ddgs.news(q, max_results=max_results, timelimit="w"):
                title = r.get("title") or ""
                body = (r.get("body") or "")[:400]
                date = r.get("date", "") or ""
                src = r.get("source", "") or ""
                head = f"• [{date}] {title}" if date else f"• {title}"
                if src:
                    head += f" — {src}"
                lines.append(head)
                if body:
                    lines.append(f"  {body}")
        if not lines:
            return f"No web news results for: {q}"
        return "\n".join(lines)
    except Exception as exc:
        log.warning("Web news search failed for %r: %s", q, exc)
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
    parts.append("### Macro / general (web)\n" + _web_finance_news_text(macro_q, max_results=6))
    return "\n\n".join(parts)
