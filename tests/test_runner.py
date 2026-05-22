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


def test_run_analysis_unknown_task() -> None:
    with pytest.raises(ValueError, match="Unknown task"):
        run_analysis("not_a_task", {})


def test_regime_analysis_payload(example_portfolio: Portfolio) -> None:
    seen_top_n = None

    def fake_find_similar_periods(_md, _p, *, top_n: int):
        nonlocal seen_top_n
        seen_top_n = top_n
        return [
            {
                "period": "2020-01-01 to 2020-01-31",
                "distance": 0.1,
                "match_score": 0.9,
                "forward_return": 0.02,
                "forward_max_drawdown": -0.03,
            }
        ]

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
        ],
        fetched_at="t",
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "port.runner.regime.runner.backtest.find_similar_periods",
            fake_find_similar_periods,
        )
        mp.setattr(
            "port.runner.regime.runner.backtest.portfolio_performance",
            lambda _a: {
                "available": True,
                "message": "ok",
                "avg_return": 0.02,
                "max_drawdown_proxy": -0.03,
                "win_rate": 1.0,
                "top_similar_periods": [
                    {
                        "period": "2020-01-01 to 2020-01-31",
                        "forward_window": "2020-02-03 to 2020-03-02",
                        "forward_horizon_days": 21,
                        "distance": 0.1,
                        "match_score": 0.9,
                        "portfolio_return": 0.02,
                        "max_drawdown": -0.03,
                    }
                ],
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
                historical_outcome=HistoricalRegimeOutcome(
                    runner_available=False,
                    message="Historical analog matching has not been run yet for this review.",
                    analog_periods_identified=0,
                    avg_return=None,
                    max_drawdown=None,
                    win_rate=None,
                    top_similar_periods=[],
                ),
                mismatch_drivers=[],
                mismatches=[],
                regime_appropriate_tilts=[],
                exposure_links=[],
                summary="",
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
    assert (
        out["regime_review"]["historical_outcome"]["top_similar_periods"][0]["portfolio_return"]
        == 0.02
    )
    assert seen_top_n == 3


def test_regime_analysis_propagates_analog_matching_failures(example_portfolio: Portfolio) -> None:
    def _raise_missing_analogs(_md, _p, *, top_n: int):
        assert top_n == 3
        raise RuntimeError("missing analog inputs")

    md = MarketData(
        indicators=[
            _market_indicator(
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
                concentration_issues=["Concentration index: 50/100"],
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
            _market_indicator(
                ticker="^TNX",
                label="US 10Y Yield",
                current=43.0,
                change_1d_pct=0.0,
                change_1m_pct=10.0,
            ),
            _market_indicator(
                ticker="SPY", label="SPY", current=500.0, change_1d_pct=0.0, change_1m_pct=10.0
            ),
            _market_indicator(
                ticker="EEM", label="EEM", current=42.0, change_1d_pct=0.0, change_1m_pct=10.0
            ),
            _market_indicator(
                ticker="GLD", label="GLD", current=200.0, change_1d_pct=0.0, change_1m_pct=10.0
            ),
            _market_indicator(
                ticker="USO", label="USO", current=75.0, change_1d_pct=0.0, change_1m_pct=10.0
            ),
            _market_indicator(
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

    def _fake_load(tickers: list[str]) -> pd.DataFrame:
        if set(tickers) == {"^TNX", "SPY", "EEM", "GLD", "USO", "XLF"}:
            return macro_close
        if tickers == ["AAPL"]:
            return pos_close
        raise AssertionError(f"unexpected tickers: {tickers!r}")

    monkeypatch.setattr("port.runner.regime.backtest._load_close", _fake_load)
    analogs = backtest.find_similar_periods(md, portfolio, top_n=1)
    assert len(analogs) == 1
    assert analogs[0]["forward_return"] > 0
    expected_forward_start = "2020-07-30"
    assert analogs[0]["forward_window"].startswith(expected_forward_start)


def test_regime_backtest_drops_tickers_missing_history(monkeypatch) -> None:
    from port.runner.regime import backtest

    portfolio = Portfolio(
        name="Partial Coverage",
        positions=[
            Position(
                ticker="AAPL",
                name="Apple",
                weight=0.6,
                quantity=1.0,
                sector="Technology",
                entry_date=date(2024, 1, 1),
                entry_price=100.0,
                current_price=120.0,
                entry_thesis="Growth",
            ),
            Position(
                ticker="XOM",
                name="Exxon",
                weight=0.4,
                quantity=1.0,
                sector="Energy",
                entry_date=date(2024, 1, 1),
                entry_price=100.0,
                current_price=110.0,
                entry_thesis="Energy exposure",
            ),
        ],
    )
    md = MarketData(
        indicators=[
            _market_indicator(
                ticker=t,
                label=t,
                current=100.0,
                change_1d_pct=0.0,
                change_1m_pct=10.0,
            )
            for t in ("^TNX", "SPY", "EEM", "GLD", "USO", "XLF")
        ],
        fetched_at="t",
    )

    dates = pd.date_range("2020-01-01", periods=220, freq="B")
    macro_close = pd.DataFrame(
        100.0, index=dates, columns=["^TNX", "SPY", "EEM", "GLD", "USO", "XLF"]
    )
    macro_close.loc[dates[150] :, :] = 110.0
    pos_close = pd.DataFrame({"AAPL": [100.0 + i * 0.1 for i in range(len(dates))]}, index=dates)

    def _fake_load(tickers: list[str]) -> pd.DataFrame:
        if set(tickers) == {"^TNX", "SPY", "EEM", "GLD", "USO", "XLF"}:
            return macro_close
        if set(tickers) == {"AAPL", "XOM"}:
            return pos_close  # XOM intentionally missing — simulates partial provider response
        raise AssertionError(f"unexpected tickers: {tickers!r}")

    monkeypatch.setattr("port.runner.regime.backtest._load_close", _fake_load)
    analogs = backtest.find_similar_periods(md, portfolio, top_n=1)
    assert len(analogs) == 1


def test_regime_backtest_loads_cached_history(monkeypatch) -> None:
    from port.runner.regime import backtest

    dates = pd.date_range("2020-01-01", periods=10, freq="B")
    cached = pd.DataFrame(
        {"AAPL": [100.0] * len(dates), "TLT": [90.0] * len(dates)},
        index=dates,
    )

    def _fake_cached(tickers: list[str], **kwargs) -> pd.DataFrame:
        assert set(tickers) == {"AAPL", "TLT"}
        assert kwargs == {"purpose": "Regime analog matching", "allow_missing": True}
        return cached

    monkeypatch.setattr("port.runner.regime.backtest.load_saved_close_frame", _fake_cached)
    close = backtest._load_close(["AAPL", "TLT"])
    assert "AAPL" in close.columns
    assert "TLT" in close.columns


def test_saved_close_frame_normalizes_timezone_index_dates(tmp_path, monkeypatch) -> None:
    from port import market_data

    root = tmp_path / "market"
    positions = root / "positions"
    positions.mkdir(parents=True)
    pd.DataFrame(
        {"Close": [100.0, 101.0]},
        index=["2024-01-02 00:00:00-05:00", "2024-01-03 00:00:00-05:00"],
    ).to_csv(positions / "AAPL.csv")
    pd.DataFrame(
        {"Close": [200.0, 202.0]},
        index=["2024-01-02 00:00:00-06:00", "2024-01-03 00:00:00-06:00"],
    ).to_csv(positions / "MSFT.csv")
    monkeypatch.setattr(market_data, "_market_data_dir", lambda kind: root / kind)

    close = market_data.load_saved_close_frame(
        ["AAPL", "MSFT"],
        purpose="Test",
        allow_missing=False,
    )

    assert list(close.index) == [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")]
    assert close.notna().all().all()


def test_regime_backtest_load_raises_when_all_missing(monkeypatch) -> None:
    from port.runner.regime import backtest

    def _fake_cached(_tickers: list[str], **_kwargs) -> pd.DataFrame:
        raise RuntimeError("Regime analog matching requires first-step market history")

    monkeypatch.setattr("port.runner.regime.backtest.load_saved_close_frame", _fake_cached)
    with pytest.raises(RuntimeError, match="first-step market history"):
        backtest._load_close(["AAPL", "TLT"])
