from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from port.models import (
    HistoricalRegimeOutcome,
    MarketData,
    MarketIndicator,
    RegimeReview,
    RegimeStateVector,
    RiskReview,
    ScenarioLoss,
    WorstScenario,
)
from port.portfolio import Portfolio, Position
from port.runner import run_analysis


def test_run_analysis_unknown_task() -> None:
    with pytest.raises(ValueError, match="Unknown task"):
        run_analysis("not_a_task", {})


def test_regime_analysis_payload(example_portfolio: Portfolio) -> None:
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
        ],
        fetched_at="t",
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "port.runner.regime.runner.backtest.find_similar_periods",
            lambda _md, _p: [
                {
                    "period": "2020-01-01 to 2020-01-31",
                    "distance": 0.1,
                    "match_score": 0.9,
                    "forward_return": 0.02,
                    "forward_max_drawdown": -0.03,
                }
            ],
        )
        mp.setattr(
            "port.runner.regime.runner.backtest.portfolio_performance",
            lambda _a: {
                "available": True,
                "message": "ok",
                "avg_return": 0.02,
                "max_drawdown_proxy": -0.03,
                "win_rate": 1.0,
            },
        )
        mp.setattr(
            "port.runner.regime.runner.compute_regime_review_base",
            lambda _p, _md: RegimeReview(
                current_regime="infl_down_rates_down_growth_accelerating_liq_loose_vol_low",
                state_vector=RegimeStateVector(
                    inflation_trend="down",
                    rates_trend="down",
                    growth_trend="accelerating",
                    liquidity="loose",
                    volatility="low",
                ),
                regime_confidence=7,
                portfolio_fit_score=6,
                historical_outcome=HistoricalRegimeOutcome(),
            ),
        )
        out = run_analysis(
            "regime_analysis",
            {
                "portfolio": example_portfolio.model_dump(mode="json"),
                "market_data": md.model_dump(mode="json"),
            },
        )
    assert set(out.keys()) == {"regime_review"}
    assert out["regime_review"]["state_vector"]["growth_trend"] == "accelerating"
    assert out["regime_review"]["historical_outcome"]["runner_available"] is True
    assert out["regime_review"]["historical_outcome"]["analog_periods_identified"] >= 1


def test_regime_analysis_propagates_analog_matching_failures(example_portfolio: Portfolio) -> None:
    def _raise_missing_analogs(_md, _p):
        raise RuntimeError("missing analog inputs")

    md = MarketData(
        indicators=[
            MarketIndicator(
                ticker="^TNX",
                label="US 10Y Yield",
                current=43.0,
                change_1d_pct=0.1,
                change_1m_pct=-3.0,
            )
        ],
        fetched_at="t",
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "port.runner.regime.runner.backtest.find_similar_periods",
            _raise_missing_analogs,
        )
        with pytest.raises(RuntimeError, match="missing analog inputs"):
            run_analysis(
                "regime_analysis",
                {
                    "portfolio": example_portfolio.model_dump(mode="json"),
                    "market_data": md.model_dump(mode="json"),
                },
            )


def test_risk_analysis_payload(example_portfolio: Portfolio) -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "port.runner.risk.runner.compute_risk_review_base",
            lambda _p, _md: RiskReview(
                factor_loadings={"beta_spy": 1.0},
                factor_risk_contribution={"beta_spy": 1.0},
                marginal_risk_by_ticker={"NVDA": 1.0},
                scenario_losses=[
                    ScenarioLoss(
                        scenario="COVID crash",
                        estimated_portfolio_loss_pct=-12.0,
                        most_affected_positions=["NVDA"],
                        scenario_kind="historical",
                    )
                ],
                worst_scenario=WorstScenario(
                    name="COVID crash", estimated_portfolio_loss_pct=-12.0
                ),
                concentration_top5_pct=0.5,
                concentration_issues=["Concentration score: 50/100"],
                risk_score=6,
            ),
        )
        out = run_analysis(
            "risk_analysis",
            {"portfolio": example_portfolio.model_dump(mode="json"), "market_data": None},
        )
    assert set(out.keys()) == {"risk_review"}
    assert out["risk_review"]["factor_loadings"] == {"beta_spy": 1.0}


def test_regime_backtest_uses_forward_returns(monkeypatch) -> None:
    from port.runner.regime import backtest

    portfolio = Portfolio(
        name="Analog Test",
        positions=[
            Position(
                ticker="AAPL",
                name="Apple",
                weight=1.0,
                quantity=1.0,
                sector="Technology",
                entry_date=date(2024, 1, 1),
                entry_price=100.0,
                current_price=120.0,
                entry_thesis="Growth",
            )
        ],
    )
    md = MarketData(
        indicators=[
            MarketIndicator(
                ticker="^TNX",
                label="US 10Y Yield",
                current=43.0,
                change_1d_pct=0.0,
                change_1m_pct=10.0,
            ),
            MarketIndicator(
                ticker="SPY", label="SPY", current=500.0, change_1d_pct=0.0, change_1m_pct=10.0
            ),
            MarketIndicator(
                ticker="EEM", label="EEM", current=42.0, change_1d_pct=0.0, change_1m_pct=10.0
            ),
            MarketIndicator(
                ticker="GLD", label="GLD", current=200.0, change_1d_pct=0.0, change_1m_pct=10.0
            ),
            MarketIndicator(
                ticker="USO", label="USO", current=75.0, change_1d_pct=0.0, change_1m_pct=10.0
            ),
            MarketIndicator(
                ticker="XLF", label="XLF", current=40.0, change_1d_pct=0.0, change_1m_pct=10.0
            ),
        ],
        fetched_at="t",
    )
    dates = pd.date_range("2020-01-01", periods=220, freq="B")
    target_idx = 150

    macro_close = pd.DataFrame(
        100.0, index=dates, columns=["^TNX", "SPY", "EEM", "GLD", "USO", "XLF"]
    )
    macro_close.loc[dates[target_idx] :, :] = 110.0

    pos_close = pd.DataFrame(index=dates, columns=["AAPL"], dtype=float)
    pos_close.loc[:, "AAPL"] = 100.0
    down_segment = pd.Series(
        [100.0 - (20.0 * i / 21.0) for i in range(22)],
        index=dates[target_idx - 21 : target_idx + 1],
    )
    up_segment = pd.Series(
        [80.0 + (40.0 * i / 21.0) for i in range(22)],
        index=dates[target_idx : target_idx + 21 + 1],
    )
    pos_close.loc[down_segment.index, "AAPL"] = down_segment
    pos_close.loc[up_segment.index, "AAPL"] = up_segment
    pos_close.loc[dates[target_idx + 21 + 1] :, "AAPL"] = 120.0

    def _fake_download(tickers: list[str], period: str) -> pd.DataFrame:
        if set(tickers) == {"^TNX", "SPY", "EEM", "GLD", "USO", "XLF"}:
            return macro_close
        if tickers == ["AAPL"]:
            return pos_close
        raise AssertionError(f"unexpected tickers: {tickers!r} period={period!r}")

    monkeypatch.setattr("port.runner.regime.backtest._download_close", _fake_download)
    analogs = backtest.find_similar_periods(md, portfolio, top_n=1)
    assert len(analogs) == 1
    assert analogs[0]["forward_return"] > 0
    expected_forward_start = "2020-07-30"
    assert analogs[0]["forward_window"].startswith(expected_forward_start)
