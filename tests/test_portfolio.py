from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from port.models import (
        MarketData,
        NewsReview,
        RegimeReview,
        RiskReview,
        ThemeReview,
        ValidationReview,
    )
from port.models import NewsFocus, PositionGoalFocus
from port.portfolio import (
    Portfolio,
    Position,
    make_example_portfolio,
    market_data_to_text,
    news_focus_to_text,
    news_to_text,
    news_tool_queries_to_text,
    planned_news_tool_queries,
    portfolio_to_text,
    render_regime,
    render_risk,
    render_theme,
    render_validation,
)


def test_portfolio_to_text(example_portfolio: Portfolio) -> None:
    text = portfolio_to_text(example_portfolio)
    assert "Test Portfolio" in text
    assert "AAPL" in text
    assert "Cash:" in text
    assert "Thesis:" in text
    assert "Tags: tech, quality" in text
    assert "CONTEXT: Test context note." in text


def test_news_to_text(example_news: NewsReview) -> None:
    text = news_to_text(example_news)
    assert "MARKET CONTEXT" in text
    assert "Fed holding steady" in text
    assert "AI capex" in text
    assert "NVDA earnings beat" in text
    assert "AAPL" in text


def test_market_data_to_text(example_market_data: MarketData) -> None:
    text = market_data_to_text(example_market_data)
    assert "LIVE MARKET DATA" in text
    assert "AAPL" in text
    assert "S&P 500" in text
    assert "2026-03-31 12:00 UTC" in text


def test_render_risk(example_risk: RiskReview) -> None:
    text = render_risk(example_risk)
    assert "RISK REPORT" in text
    assert "6/10" in text
    assert "Factor loadings" in text
    assert "Rates +200bps" in text
    assert "Crowded tech longs" in text


def test_render_regime(example_regime: RegimeReview) -> None:
    text = render_regime(example_regime)
    assert "REGIME REPORT" in text
    assert "late-cycle expansion" in text
    assert "State vector" in text
    assert "Duration mismatch" in text
    assert "Favor quality" in text


def test_render_theme(example_theme: ThemeReview) -> None:
    text = render_theme(example_theme)
    assert "THEME REPORT" in text
    assert "Scored themes" in text
    assert "AI capex" in text
    assert "AAPL crowded" in text
    assert "AAPL momentum fading" in text


def test_render_validation(example_validation: ValidationReview) -> None:
    text = render_validation(example_validation)
    assert "VALIDATION SYNTHESIS" in text
    assert "Tech concentration" in text
    assert "[HIGH]" in text
    assert "AAPL thesis at risk" in text


def test_news_focus_to_text_with_goals() -> None:
    focus = NewsFocus(
        portfolio_goal="Beat S&P 500",
        position_goals=[
            PositionGoalFocus(ticker="AAPL", goal="Strong ecosystem"),
            PositionGoalFocus(ticker="MSFT", goal="Cloud growth"),
        ],
    )
    text = news_focus_to_text(focus)
    assert "Beat S&P 500" in text
    assert "AAPL: Strong ecosystem" in text
    assert "MSFT: Cloud growth" in text
    assert "SEARCH PRIORITIES" in text


def test_news_focus_to_text_empty_goal() -> None:
    focus = NewsFocus(
        portfolio_goal="",
        position_goals=[PositionGoalFocus(ticker="SPY", goal="")],
    )
    text = news_focus_to_text(focus)
    assert "(none stated)" in text
    assert "SPY: (no thesis stated)" in text


def test_news_focus_to_text_includes_planned_queries() -> None:
    focus = NewsFocus(
        portfolio_goal="Beat benchmark",
        portfolio_search_queries=["Federal Reserve dot plot 2026"],
        position_goals=[
            PositionGoalFocus(
                ticker="XOM",
                goal="Energy FCF",
                latest_news_query="latest news for XOM",
            ),
        ],
    )
    text = news_focus_to_text(focus)
    assert "PLANNED SEARCH QUERIES" in text
    assert "Federal Reserve dot plot 2026" in text
    assert "planned query (latest news): latest news for XOM" in text


def test_news_tool_queries_to_text_lists_queries_only() -> None:
    focus = NewsFocus(
        portfolio_goal="Should not appear in tools prompt",
        portfolio_search_queries=["AI capex sustainability", "Fed policy", "USD strength"],
        position_goals=[
            PositionGoalFocus(
                ticker="NVDA",
                goal="Hidden thesis",
                latest_news_query="latest news for NVDA",
            ),
        ],
    )
    text = news_tool_queries_to_text(focus)
    assert "PLANNED WEB SEARCH" in text
    assert "AI capex sustainability" in text
    assert "Fed policy" in text
    assert "latest news for NVDA" in text
    assert "Hidden thesis" not in text
    assert "Should not appear" not in text


def test_news_tool_queries_to_text_fallback_per_ticker() -> None:
    focus = NewsFocus(
        portfolio_goal="Macro note",
        position_goals=[PositionGoalFocus(ticker="SPY", goal="Market beta")],
    )
    text = news_tool_queries_to_text(focus)
    assert "SPY" in text
    assert "Market beta" not in text
    assert "Macro note" not in text


def test_planned_news_tool_queries_order_and_dedupe() -> None:
    focus = NewsFocus(
        portfolio_search_queries=["macro a", "macro b", "macro c"],
        position_goals=[
            PositionGoalFocus(
                ticker="NVDA",
                goal="x",
                latest_news_query="macro a",
            ),
        ],
    )
    qs = planned_news_tool_queries(focus)
    assert qs == ["macro a", "macro b", "macro c"]


def test_planned_news_tool_queries_empty_position_fallback() -> None:
    focus = NewsFocus(
        position_goals=[PositionGoalFocus(ticker="SPY", goal="Beta")],
    )
    assert planned_news_tool_queries(focus) == ["latest news for SPY"]


def test_news_focus_to_text_includes_macro_indicator_line() -> None:
    focus = NewsFocus(
        portfolio_goal="Rates and vol matter",
        position_goals=[PositionGoalFocus(ticker="SPY", goal="Beta")],
        macro_indicator_tickers=["SPY", "^TNX"],
    )
    text = news_focus_to_text(focus)
    assert "PLANNED MACRO PRICE FETCHES" in text
    assert "SPY" in text and "^TNX" in text


def test_pnl_pct_zero_entry_price() -> None:
    pos = Position(
        ticker="AAPL",
        name="Apple",
        weight=0.1,
        sector="Tech",
        entry_date=date(2023, 1, 1),
        entry_price=0.0,
        current_price=100.0,
        entry_thesis="test",
    )
    assert pos.pnl_pct == 0.0


def test_portfolio_to_text_zero_cash() -> None:
    p = Portfolio(
        name="No Cash",
        positions=[],
        cash_weight=0.0,
        review_date=date(2026, 1, 1),
    )
    text = portfolio_to_text(p)
    assert "Cash: $0" in text


def test_portfolio_to_text_full_cash() -> None:
    p = Portfolio(
        name="All Cash",
        positions=[],
        cash_weight=1.0,
        review_date=date(2026, 1, 1),
    )
    text = portfolio_to_text(p)
    assert "entire portfolio in" in text


def test_make_example_portfolio() -> None:
    p = make_example_portfolio()
    assert p.name == "Growth Tilted Core"
    assert len(p.positions) == 6
    tickers = [pos.ticker for pos in p.positions]
    assert "NVDA" in tickers
    assert "TLT" in tickers
