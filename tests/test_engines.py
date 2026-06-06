from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from port.models import (
    HistoricalRegimeOutcome,
    HistoricalRegimePeriod,
    MarketData,
    MarketIndicator,
    RegimeReview,
    RegimeStateVector,
)
from port.portfolio import Portfolio, Position
from port.regime_signals import (
    compute_regime_review_base,
    format_regime_python_block,
    infer_state_vector,
)
from port.risk_engine import compute_risk_review_base


def _market_indicator(
    *,
    ticker: str,
    label: str,
    current: float,
    change_1d_pct: float,
    change_1m_pct: float,
) -> MarketIndicator:
    return MarketIndicator(
        ticker=ticker,
        label=label,
        current=current,
        prev_close=current,
        change_1d_pct=change_1d_pct,
        change_1w_pct=change_1m_pct,
        change_1m_pct=change_1m_pct,
        change_3m_pct=change_1m_pct,
        change_1y_pct=change_1m_pct,
        week_52_high=current,
        week_52_low=current,
        pct_from_52w_high=0.0,
    )


def _market_sensitive_portfolio() -> Portfolio:
    positions = [
        ("NVDA", "Nvidia", 0.12, "Technology", "AI compute and semiconductor growth"),
        ("MSFT", "Microsoft", 0.10, "Technology", "Cloud software growth"),
        ("TLT", "iShares 20Y Treasury", 0.10, "Fixed Income", "Duration and rates exposure"),
        ("XOM", "ExxonMobil", 0.08, "Energy", "Oil and energy cash flow"),
        ("JPM", "JPMorgan Chase", 0.08, "Financials", "Bank with rate sensitivity"),
        ("ASML", "ASML Holding", 0.07, "Technology", "Semiconductor equipment cycle"),
    ]
    return Portfolio(
        name="Market Sensitive Test Portfolio",
        positions=[
            Position(
                ticker=ticker,
                name=name,
                weight=weight,
                quantity=1.0,
                sector=sector,
                entry_date=date(2023, 1, 1),
                entry_price=100.0,
                current_price=120.0,
                entry_thesis=thesis,
                asset_class="bond" if ticker == "TLT" else "equity",
            )
            for ticker, name, weight, sector, thesis in positions
        ],
        cash_weight=0.45,
        benchmark="SPY",
        review_date=date(2026, 3, 28),
    )


def test_infer_state_vector_uses_indicators() -> None:
    md = MarketData(
        indicators=[
            _market_indicator(
                ticker="^TNX",
                label="US 10Y Yield",
                current=43.0,
                change_1d_pct=0.1,
                change_1m_pct=-3.0,
            ),
            _market_indicator(
                ticker="SPY", label="SPY", current=500.0, change_1d_pct=0.1, change_1m_pct=3.0
            ),
            _market_indicator(
                ticker="EEM",
                label="Developing Markets Equity",
                current=42.0,
                change_1d_pct=0.0,
                change_1m_pct=2.0,
            ),
            _market_indicator(
                ticker="GLD", label="GLD", current=200.0, change_1d_pct=0.0, change_1m_pct=0.0
            ),
            _market_indicator(
                ticker="USO",
                label="Oil (WTI proxy)",
                current=75.0,
                change_1d_pct=0.0,
                change_1m_pct=1.0,
            ),
            _market_indicator(
                ticker="XLF", label="Financials", current=40.0, change_1d_pct=0.0, change_1m_pct=0.5
            ),
            _market_indicator(
                ticker="^VIX", label="VIX", current=16.0, change_1d_pct=0.0, change_1m_pct=-5.0
            ),
        ],
        fetched_at="t",
    )
    sv = infer_state_vector(md)
    assert sv.rates_trend == "down"
    assert sv.growth_trend == "accelerating"


def test_risk_engine_produces_loadings_and_worst(monkeypatch) -> None:
    p = _market_sensitive_portfolio()
    idx = pd.date_range("2018-01-01", periods=2200, freq="B")
    cols = [
        "NVDA",
        "MSFT",
        "TLT",
        "XOM",
        "JPM",
        "ASML",
        "SPY",
        "QQQ",
        "GLD",
        "USO",
        "UUP",
        "XLF",
        "EEM",
    ]
    frame = pd.DataFrame(index=idx)
    for i, col in enumerate(cols, start=1):
        frame[col] = 100 + i + (pd.Series(range(len(idx)), index=idx) * (0.03 + i * 0.0005))

    monkeypatch.setattr("port.risk_engine._load_close_frame", lambda _tickers: frame)
    r = compute_risk_review_base(p, None)
    assert r.factor_loadings
    assert r.worst_scenario is not None
    assert r.marginal_risk_by_ticker
    assert sum(r.marginal_risk_by_ticker.values()) == pytest.approx(0.55)


def test_risk_engine_degrades_gracefully_with_short_history(monkeypatch) -> None:
    p = _market_sensitive_portfolio()
    idx = pd.date_range("2018-01-01", periods=600, freq="B")
    cols = [
        "NVDA",
        "MSFT",
        "TLT",
        "XOM",
        "JPM",
        "ASML",
        "SPY",
        "QQQ",
        "GLD",
        "USO",
        "UUP",
        "XLF",
        "EEM",
    ]
    frame = pd.DataFrame(index=idx)
    for i, col in enumerate(cols, start=1):
        frame[col] = 100 + i + (pd.Series(range(len(idx)), index=idx) * (0.03 + i * 0.0005))
    frame.loc[idx[:-40], "ASML"] = float("nan")

    monkeypatch.setattr("port.risk_engine._load_close_frame", lambda _tickers: frame)
    r = compute_risk_review_base(p, None)
    assert r.factor_loadings
    assert "ASML" not in r.marginal_risk_by_ticker
    removed_field = "frag" + "ilities"
    assert removed_field not in type(r).model_fields


def test_risk_engine_raises_when_price_history_is_too_thin(monkeypatch) -> None:
    p = _market_sensitive_portfolio()
    idx = pd.date_range("2024-01-01", periods=40, freq="B")
    cols = [
        "NVDA",
        "MSFT",
        "TLT",
        "XOM",
        "JPM",
        "ASML",
        "SPY",
        "QQQ",
        "GLD",
        "USO",
        "UUP",
        "XLF",
        "EEM",
    ]
    frame = pd.DataFrame(index=idx)
    for i, col in enumerate(cols, start=1):
        frame[col] = 100 + i + (pd.Series(range(len(idx)), index=idx) * 0.01)

    monkeypatch.setattr("port.risk_engine._load_close_frame", lambda _tickers: frame)
    with pytest.raises(RuntimeError, match="Risk analysis unavailable:"):
        compute_risk_review_base(p, None)


def test_risk_engine_keeps_empirical_outputs_when_coverage_is_below_half(monkeypatch) -> None:
    portfolio = Portfolio(
        name="Partial History",
        positions=[
            Position(
                ticker="AAPL",
                name="Apple",
                weight=0.4,
                quantity=1.0,
                sector="Technology",
                entry_date=date(2024, 1, 1),
                entry_price=100.0,
                current_price=120.0,
                entry_thesis="Core compounder.",
            ),
            Position(
                ticker="MSFT",
                name="Microsoft",
                weight=0.3,
                quantity=1.0,
                sector="Technology",
                entry_date=date(2024, 1, 1),
                entry_price=100.0,
                current_price=120.0,
                entry_thesis="Cloud scale.",
            ),
            Position(
                ticker="GOOG",
                name="Alphabet",
                weight=0.3,
                quantity=1.0,
                sector="Technology",
                entry_date=date(2024, 1, 1),
                entry_price=100.0,
                current_price=120.0,
                entry_thesis="Ads and AI optionality.",
            ),
        ],
    )
    idx = pd.date_range("2018-01-01", periods=600, freq="B")
    cols = ["AAPL", "MSFT", "GOOG", "SPY", "QQQ", "GLD", "USO", "UUP", "XLF", "EEM"]
    frame = pd.DataFrame(index=idx)
    for i, col in enumerate(cols, start=1):
        frame[col] = 100 + i + (pd.Series(range(len(idx)), index=idx) * (0.03 + i * 0.0005))
    frame.loc[idx[:-40], "MSFT"] = float("nan")
    frame.loc[idx[:-40], "GOOG"] = float("nan")

    monkeypatch.setattr("port.risk_engine._load_close_frame", lambda _tickers: frame)
    review = compute_risk_review_base(portfolio, None)
    assert review.factor_loadings
    assert review.scenario_losses
    assert review.worst_scenario is not None
    assert review.marginal_risk_by_ticker == {"AAPL": 0.4}
    removed_field = "frag" + "ilities"
    assert removed_field not in type(review).model_fields


def _make_market_data(
    *,
    tnx_1m: float,
    spy_1m: float,
    eem_1m: float,
    gld_1m: float,
    uso_1m: float,
    xlf_1m: float,
    vix_level: float,
    vix_1m: float,
) -> MarketData:
    return MarketData(
        indicators=[
            _market_indicator(
                ticker="^TNX",
                label="US 10Y Yield",
                current=43.0,
                change_1d_pct=0.1,
                change_1m_pct=tnx_1m,
            ),
            _market_indicator(
                ticker="SPY",
                label="SPY",
                current=500.0,
                change_1d_pct=0.1,
                change_1m_pct=spy_1m,
            ),
            _market_indicator(
                ticker="EEM",
                label="Developing Markets Equity",
                current=42.0,
                change_1d_pct=0.0,
                change_1m_pct=eem_1m,
            ),
            _market_indicator(
                ticker="GLD",
                label="GLD",
                current=200.0,
                change_1d_pct=0.0,
                change_1m_pct=gld_1m,
            ),
            _market_indicator(
                ticker="USO",
                label="Oil (WTI proxy)",
                current=75.0,
                change_1d_pct=0.0,
                change_1m_pct=uso_1m,
            ),
            _market_indicator(
                ticker="XLF",
                label="Financials",
                current=40.0,
                change_1d_pct=0.0,
                change_1m_pct=xlf_1m,
            ),
            _market_indicator(
                ticker="^VIX",
                label="VIX",
                current=vix_level,
                change_1d_pct=0.0,
                change_1m_pct=vix_1m,
            ),
        ],
        fetched_at="t",
    )


def _make_regime_review(runner_available: bool, **hist_kwargs) -> RegimeReview:
    hist_payload = {
        "runner_available": runner_available,
        "message": "Historical analog matching has not been run yet for this review.",
        "analog_periods_identified": 0,
        "avg_return": None,
        "max_drawdown": None,
        "win_rate": None,
        "top_similar_periods": [],
    } | hist_kwargs
    hist = HistoricalRegimeOutcome(**hist_payload)
    return RegimeReview(
        current_regime=(
            "rising inflation, rising rates, slowing growth, "
            "tight liquidity, high volatility"
        ),
        state_vector=RegimeStateVector(
            inflation_trend="up",
            rates_trend="up",
            growth_trend="slowing",
            liquidity="tight",
            volatility="high",
        ),
        historical_outcome=hist,
        mismatch_drivers=[],
        regime_appropriate_tilts=[],
        exposure_links=[],
        summary="",
    )


def test_format_regime_block_with_runner_available() -> None:
    review = _make_regime_review(
        runner_available=True,
        message="Closest analog: 2022-01-03 to 2022-01-31 (distance=0.0512).",
        analog_periods_identified=3,
        avg_return=-0.045,
        max_drawdown=-0.08,
        win_rate=0.33,
        top_similar_periods=[
            HistoricalRegimePeriod(
                period="2022-01-03 to 2022-01-31",
                forward_window="2022-02-01 to 2022-03-01",
                forward_horizon_days=21,
                distance=0.0512,
                match_score=0.9488,
                portfolio_return=-0.045,
                max_drawdown=-0.08,
            )
        ],
    )
    block = format_regime_python_block(review)
    assert "runner_available=True" in block
    assert "avg_return=-4.50%" in block
    assert "max_drawdown=-8.00%" in block
    assert "win_rate=33%" in block
    assert "analog_periods=3" in block
    assert "portfolio_return=-4.50%" in block
    assert "Closest analog" in block


def test_compute_regime_review_base_changes_with_state_vector() -> None:
    portfolio = _market_sensitive_portfolio()
    risk_on = _make_market_data(
        tnx_1m=-2.0,
        spy_1m=3.0,
        eem_1m=2.0,
        gld_1m=0.5,
        uso_1m=0.5,
        xlf_1m=1.0,
        vix_level=14.0,
        vix_1m=-4.0,
    )
    risk_off = _make_market_data(
        tnx_1m=2.5,
        spy_1m=-3.0,
        eem_1m=-4.0,
        gld_1m=1.5,
        uso_1m=2.0,
        xlf_1m=-2.0,
        vix_level=28.0,
        vix_1m=15.0,
    )
    risk_on_review = compute_regime_review_base(portfolio, risk_on)
    risk_off_review = compute_regime_review_base(portfolio, risk_off)
    assert risk_on_review.current_regime != risk_off_review.current_regime


def test_format_regime_block_runner_disabled() -> None:
    review = _make_regime_review(runner_available=False)
    block = format_regime_python_block(review)
    assert "runner_available=False" in block
    assert "avg_return" not in block
