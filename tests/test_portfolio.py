from __future__ import annotations

from port.models import (
    MarketData,
    NewsReview,
    RegimeReview,
    RiskReview,
    ThemeReview,
    ValidationReview,
)
from port.portfolio import (
    Portfolio,
    market_data_to_text,
    news_to_text,
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
    assert "momentum" in text
    assert "Rates +200bps" in text
    assert "Crowded tech longs" in text


def test_render_regime(example_regime: RegimeReview) -> None:
    text = render_regime(example_regime)
    assert "REGIME REPORT" in text
    assert "late-cycle expansion" in text
    assert "Duration mismatch" in text
    assert "Favor quality" in text


def test_render_theme(example_theme: ThemeReview) -> None:
    text = render_theme(example_theme)
    assert "THEME REPORT" in text
    assert "AI capex" in text
    assert "AAPL crowded" in text
    assert "AAPL momentum fading" in text


def test_render_validation(example_validation: ValidationReview) -> None:
    text = render_validation(example_validation)
    assert "VALIDATION SYNTHESIS" in text
    assert "Tech concentration" in text
    assert "[HIGH]" in text
    assert "AAPL thesis at risk" in text
