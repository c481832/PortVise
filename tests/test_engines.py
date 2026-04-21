from __future__ import annotations

from datetime import date

import pandas as pd

from port.models import (
    HistoricalRegimeOutcome,
    MarketData,
    MarketIndicator,
    RegimeReview,
    RegimeStateVector,
)
from port.portfolio import Portfolio, Position, make_example_portfolio
from port.regime_signals import (
    compute_regime_review_base,
    format_regime_python_block,
    infer_state_vector,
)
from port.risk_engine import compute_risk_review_base


def test_infer_state_vector_uses_indicators() -> None:
    md = MarketData(
        indicators=[
            MarketIndicator(
                ticker="^TNX",
                label="US 10Y Yield",
                current=43.0,
                change_1d_pct=0.1,
                change_1m_pct=-3.0,
            ),
            MarketIndicator(
                ticker="SPY", label="SPY", current=500.0, change_1d_pct=0.1, change_1m_pct=3.0
            ),
            MarketIndicator(
                ticker="EEM",
                label="Developing Markets Equity",
                current=42.0,
                change_1d_pct=0.0,
                change_1m_pct=2.0,
            ),
            MarketIndicator(
                ticker="GLD", label="GLD", current=200.0, change_1d_pct=0.0, change_1m_pct=0.0
            ),
            MarketIndicator(
                ticker="USO",
                label="Oil (WTI proxy)",
                current=75.0,
                change_1d_pct=0.0,
                change_1m_pct=1.0,
            ),
            MarketIndicator(
                ticker="XLF", label="Financials", current=40.0, change_1d_pct=0.0, change_1m_pct=0.5
            ),
            MarketIndicator(
                ticker="^VIX", label="VIX", current=16.0, change_1d_pct=0.0, change_1m_pct=-5.0
            ),
        ],
        fetched_at="t",
    )
    sv = infer_state_vector(md)
    assert sv.rates_trend == "down"
    assert sv.growth_trend == "accelerating"


def test_risk_engine_produces_loadings_and_worst(monkeypatch) -> None:
    p = make_example_portfolio()
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

    monkeypatch.setattr("port.risk_engine._download_close_frame", lambda _tickers: frame)
    r = compute_risk_review_base(p, None)
    assert r.factor_loadings
    assert r.worst_scenario is not None
    assert r.marginal_risk_by_ticker
    assert 1 <= r.risk_score <= 10


def test_risk_engine_degrades_gracefully_with_short_history(monkeypatch) -> None:
    p = make_example_portfolio()
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

    monkeypatch.setattr("port.risk_engine._download_close_frame", lambda _tickers: frame)
    r = compute_risk_review_base(p, None)
    assert r.factor_loadings
    assert "ASML" not in r.marginal_risk_by_ticker
    assert any("ASML" in note for note in r.fragilities)
    assert any("covers" in note for note in r.fragilities)


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

    monkeypatch.setattr("port.risk_engine._download_close_frame", lambda _tickers: frame)
    review = compute_risk_review_base(portfolio, None)
    assert review.factor_loadings
    assert review.scenario_losses
    assert review.worst_scenario is not None
    assert review.marginal_risk_by_ticker == {"AAPL": 1.0}
    assert any("below 50%" in note for note in review.fragilities)
    assert any("40%" in note for note in review.fragilities)


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
            MarketIndicator(
                ticker="^TNX",
                label="US 10Y Yield",
                current=43.0,
                change_1d_pct=0.1,
                change_1m_pct=tnx_1m,
            ),
            MarketIndicator(
                ticker="SPY",
                label="SPY",
                current=500.0,
                change_1d_pct=0.1,
                change_1m_pct=spy_1m,
            ),
            MarketIndicator(
                ticker="EEM",
                label="Developing Markets Equity",
                current=42.0,
                change_1d_pct=0.0,
                change_1m_pct=eem_1m,
            ),
            MarketIndicator(
                ticker="GLD",
                label="GLD",
                current=200.0,
                change_1d_pct=0.0,
                change_1m_pct=gld_1m,
            ),
            MarketIndicator(
                ticker="USO",
                label="Oil (WTI proxy)",
                current=75.0,
                change_1d_pct=0.0,
                change_1m_pct=uso_1m,
            ),
            MarketIndicator(
                ticker="XLF",
                label="Financials",
                current=40.0,
                change_1d_pct=0.0,
                change_1m_pct=xlf_1m,
            ),
            MarketIndicator(
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
    hist = HistoricalRegimeOutcome(runner_available=runner_available, **hist_kwargs)
    return RegimeReview(
        current_regime="infl_up_rates_up_growth_slowing_liq_tight_vol_high",
        state_vector=RegimeStateVector(
            inflation_trend="up",
            rates_trend="up",
            growth_trend="slowing",
            liquidity="tight",
            volatility="high",
        ),
        regime_confidence=7,
        portfolio_fit_score=4,
        historical_outcome=hist,
    )


def test_format_regime_block_with_runner_available() -> None:
    review = _make_regime_review(
        runner_available=True,
        message="Closest analog: 2022-01-03 to 2022-01-31 (distance=0.0512).",
        analog_periods_identified=3,
        avg_return=-0.045,
        max_drawdown=-0.08,
        win_rate=0.33,
    )
    block = format_regime_python_block(review)
    assert "runner_available=True" in block
    assert "avg_return=-4.50%" in block
    assert "max_drawdown=-8.00%" in block
    assert "win_rate=33%" in block
    assert "analog_periods=3" in block
    assert "Closest analog" in block


def test_compute_regime_review_base_changes_with_state_vector(monkeypatch) -> None:
    monkeypatch.setattr("port.regime_signals._empirical_fit_score", lambda _portfolio: (0.5, []))
    portfolio = make_example_portfolio()
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
    assert risk_on_review.portfolio_fit_score != risk_off_review.portfolio_fit_score


def test_compute_regime_review_base_falls_back_when_empirical_history_is_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "port.regime_signals._empirical_fit_score",
        lambda _portfolio: (None, ["Empirical fit unavailable in test"]),
    )
    review = compute_regime_review_base(
        make_example_portfolio(),
        _make_market_data(
            tnx_1m=-2.0,
            spy_1m=3.0,
            eem_1m=2.0,
            gld_1m=0.5,
            uso_1m=0.5,
            xlf_1m=1.0,
            vix_level=14.0,
            vix_1m=-4.0,
        ),
    )
    assert 1 <= review.portfolio_fit_score <= 10
    assert review.fit_notes == ["Empirical fit unavailable in test"]


def test_format_regime_block_runner_disabled() -> None:
    review = _make_regime_review(runner_available=False)
    review.fit_notes = ["Empirical fit unavailable"]
    block = format_regime_python_block(review)
    assert "runner_available=False" in block
    assert "avg_return" not in block
    assert "fit_notes: Empirical fit unavailable" in block
