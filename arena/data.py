from __future__ import annotations

from datetime import UTC, date, datetime

from arena.models import MarketSnapshot
from port.market_data import fetch_position_snapshot
from port.tools.news_tools import _web_finance_news_text


def fetch_market_snapshot(
    watchlist: list[str],
    *,
    benchmark: str,
    include_web_news: bool,
) -> MarketSnapshot:
    tickers = []
    seen: set[str] = set()
    for ticker in [*watchlist, benchmark]:
        symbol = ticker.strip().upper()
        if symbol and symbol not in seen:
            tickers.append(symbol)
            seen.add(symbol)

    prices: dict[str, float] = {}
    movement: dict[str, dict[str, float]] = {}
    headlines: dict[str, list[str]] = {}
    errors: list[str] = []

    for ticker in tickers:
        snap = fetch_position_snapshot(ticker, actions_start=date.today())
        prices[ticker] = snap.current_price
        movement[ticker] = {
            "change_1d_pct": snap.change_1d_pct,
            "change_1w_pct": snap.change_1w_pct,
            "change_1m_pct": snap.change_1m_pct,
            "change_3m_pct": snap.change_3m_pct,
            "change_1y_pct": snap.change_1y_pct,
            "pct_from_52w_high": snap.pct_from_52w_high,
        }
        ticker_headlines: list[str] = []
        if include_web_news:
            web_text = _web_finance_news_text(f"latest news for {ticker}", max_results=3)
            if not web_text or web_text.startswith("No web news results"):
                raise RuntimeError(f"web news lookup returned no usable results for {ticker}")
            ticker_headlines.append(web_text)
        headlines[ticker] = ticker_headlines

    return MarketSnapshot(
        as_of=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        prices=prices,
        benchmark=benchmark,
        benchmark_price=prices.get(benchmark),
        price_movement=movement,
        headlines=headlines,
        errors=errors,
    )
