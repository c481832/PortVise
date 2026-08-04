from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from port.config import load as _load_config

_load_config(Path(__file__).resolve().parent / "fixtures" / "test_config.toml")

from port.logging_config import apply_port_logging_config  # noqa: E402
from port.models import (  # noqa: E402
    Action,
    AllocationReview,
    CriticalIssue,
    DeploymentCandidate,
    ExposureLayer,
    HistoricalRegimeOutcome,
    HistoricalRegimePeriod,
    ManagerReview,
    MarketData,
    MarketIndicator,
    NewsReview,
    PositionSnapshot,
    RegimeReview,
    RegimeStateVector,
    RiskReview,
    ScenarioLoss,
    ThemeAssessment,
    ThemePortfolioSynthesis,
    ThemeReview,
    ValidationReview,
    WorstScenario,
)
from port.portfolio import Portfolio, Position  # noqa: E402


@pytest.fixture
def example_portfolio() -> Portfolio:
    return Portfolio(
        name="Test Portfolio",
        positions=[
            Position(
                ticker="AAPL",
                name="Apple",
                weight=0.15,
                quantity=100.0,
                sector="Technology",
                entry_date=date(2023, 1, 1),
                entry_price=150.0,
                current_price=180.0,
                dividend=0.0,
                split=1.0,
                entry_thesis="Strong ecosystem and services growth",
                asset_class="equity",
                country="US",
                tags=["tech", "quality"],
            ),
        ],
        cash_weight=0.85,
        base_currency="USD",
        benchmark="SPY",
        review_date=date(2026, 3, 31),
        context_note="Test context note.",
    )


@pytest.fixture
def example_news() -> NewsReview:
    return NewsReview(
        macro_context="Fed holding steady. USD flat.",
        market_themes=["AI capex", "rate normalization"],
        key_events=["NVDA earnings beat"],
        thesis_risks=["AAPL"],
        summary="Markets stable.",
    )


@pytest.fixture
def example_risk() -> RiskReview:
    return RiskReview(
        factor_loadings={"momentum": 0.62, "market_beta": 0.35},
        factor_risk_contribution={"momentum": 0.62, "market_beta": 0.38},
        marginal_risk_by_ticker={"AAPL": 1.0},
        exposure_links=[
            ExposureLayer(layer="factor", label="momentum", strength=0.62, maps_to=["AI capex"])
        ],
        concentration_issues=["Tech >30%"],
        concentration_top5_pct=0.15,
        liquidity_notes=[],
        scenario_losses=[
            ScenarioLoss(
                scenario="Rates +200bps",
                estimated_portfolio_loss_pct=-5.0,
                most_affected_positions=["AAPL"],
                scenario_kind="engine",
            ),
        ],
        top_risks=["Momentum crowding in AAPL"],
        worst_scenario=WorstScenario(name="Rates +200bps", estimated_portfolio_loss_pct=-5.0),
        hidden_concentration=["Tech bundle"],
        summary="Moderate risk from tech concentration.",
    )


@pytest.fixture
def example_regime() -> RegimeReview:
    return RegimeReview(
        current_regime="late-cycle expansion",
        state_vector=RegimeStateVector(
            inflation_trend="stable",
            rates_trend="up",
            growth_trend="slowing",
            liquidity="neutral",
            volatility="low",
        ),
        historical_outcome=HistoricalRegimeOutcome(
            runner_available=True,
            message="Analog history available.",
            analog_periods_identified=3,
            avg_return=0.05,
            max_drawdown=-0.1,
            win_rate=0.6,
            top_similar_periods=[
                HistoricalRegimePeriod(
                    period="2020-01-01 to 2020-01-31",
                    forward_window="2020-02-03 to 2020-03-02",
                    forward_horizon_days=21,
                    distance=0.1,
                    match_score=0.9,
                    portfolio_return=0.05,
                    max_drawdown=-0.1,
                )
            ],
        ),
        mismatch_drivers=["Long duration vs rising rates"],
        regime_appropriate_tilts=["Favor quality"],
        exposure_links=[],
        summary="Portfolio roughly aligned.",
    )


@pytest.fixture
def example_theme() -> ThemeReview:
    return ThemeReview(
        implicit_portfolio_bet="Overweight AI-linked growth",
        position_profiles=[],
        theme_assessments=[
            ThemeAssessment(
                theme="AI capex",
                supporting_assets=["AAPL"],
                key_evidence=["Supply chain headlines cite AI demand"],
                assessment="News flow supports the AI capex narrative.",
                implication="The book remains exposed to AI capex sentiment.",
                narrative_kind="structural",
            ),
        ],
        synthesis=ThemePortfolioSynthesis(
            dominant_themes=["AI capex"],
            redundant_expressions=[],
            missing_exposures=[],
            theme_drift_note="",
        ),
        crowding_risks=["AAPL crowded"],
        momentum_conflicts=["AAPL momentum fading"],
        exposure_links=[],
        summary="Well-aligned with dominant themes.",
    )


@pytest.fixture
def example_validation() -> ValidationReview:
    return ValidationReview(
        critical_issues=[
            CriticalIssue(
                issue="Tech concentration",
                severity="high",
                affected_positions=["AAPL"],
                source_agents=["risk", "theme"],
            ),
        ],
        thesis_breaks=["AAPL thesis at risk"],
        internal_contradictions=[],
        summary="Portfolio has concentration risk.",
    )


@pytest.fixture
def example_allocation() -> AllocationReview:
    return AllocationReview(
        cash_weight=0.85,
        allocated_capital=0.15,
        min_allocated_capital=0.80,
        max_cash_weight=0.20,
        allocation_status="below minimum",
        required_deployment_pct=0.65,
        cash_yield_annual_pct=0.0,
        benchmark_return_1y_pct=10.0,
        cash_opportunity_cost_pct=8.5,
        drawdown_budget_pct=50.0,
        worst_scenario_loss_pct=5.0,
        drawdown_budget_breached=False,
        deployment_required=True,
        deployment_candidates=[
            DeploymentCandidate(
                ticker="AAPL",
                rationale="Entry thesis intact and earnings momentum supports adding.",
            ),
        ],
        constraint_conflicts=["All deployment candidates sit in the technology sector."],
        summary="Allocation is far below the configured minimum; cash must be deployed.",
    )


@pytest.fixture
def example_manager_review() -> ManagerReview:
    return ManagerReview(
        portfolio_verdict={
            "action_timing": "watch",
            "investment_horizon": "tactical",
            "horizon_detail": "1-4 weeks",
            "primary_risk": "Tech concentration",
            "recommended_posture": "Trim exposure",
            "revisit_trigger": "Risk conditions change.",
            "rationale": "Risk is elevated.",
        },
        actions=[
            Action(
                action_type="reduce",
                position="AAPL",
                rationale="Tech concentration risk",
                priority="this-week",
                size_guidance="Trim 2%.",
                hedge_instrument="",
                scope="position",
                risk_addressed="Tech concentration",
                supporting_evidence=["Risk review flagged concentration."],
                revisit_trigger="Marginal concentration falls.",
            )
        ],
        do_nothing_case="Concentration will compound on drawdown",
        executive_summary="Portfolio has elevated concentration risk.",
    )


@pytest.fixture
def example_market_data() -> MarketData:
    return MarketData(
        positions=[
            PositionSnapshot(
                ticker="AAPL",
                current_price=180.0,
                prev_close=178.0,
                change_1d_pct=1.12,
                change_1w_pct=2.5,
                change_1m_pct=5.0,
                change_1y_pct=18.0,
                change_3m_pct=10.0,
                week_52_high=195.0,
                week_52_low=140.0,
                pct_from_52w_high=-7.69,
                dividend=0.0,
                split=1.0,
            ),
        ],
        indicators=[
            MarketIndicator(
                ticker="SPY",
                label="S&P 500",
                current=5000.0,
                prev_close=4990.0,
                change_1d_pct=0.5,
                change_1w_pct=1.0,
                change_1m_pct=2.0,
                change_3m_pct=3.0,
                change_1y_pct=10.0,
                week_52_high=5100.0,
                week_52_low=4200.0,
                pct_from_52w_high=-1.96,
            ),
        ],
        fetched_at="2026-03-31 12:00 UTC",
        errors=[],
    )


def pytest_configure() -> None:
    apply_port_logging_config(enable_file_logging=False)
