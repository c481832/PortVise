from __future__ import annotations

from datetime import date

import pytest

from port.logging_config import apply_port_logging_config
from port.models import (
    Action,
    CriticalIssue,
    ManagerReview,
    MarketData,
    MarketIndicator,
    NewsReview,
    PositionSnapshot,
    RegimeReview,
    RegimeStateVector,
    RiskReview,
    ScenarioLoss,
    ThemeMatchScore,
    ThemePortfolioSynthesis,
    ThemeReview,
    ValidationReview,
    WorstScenario,
)
from port.portfolio import Portfolio, Position


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
                entry_thesis="Strong ecosystem and services growth",
                tags=["tech", "quality"],
            ),
        ],
        cash_weight=0.85,
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
        marginal_risk_by_ticker={"AAPL": 1.0},
        concentration_issues=["Tech >30%"],
        scenario_losses=[
            ScenarioLoss(
                scenario="Rates +200bps",
                estimated_portfolio_loss_pct=-5.0,
                most_affected_positions=["AAPL"],
            ),
        ],
        top_risks=["Momentum crowding in AAPL"],
        worst_scenario=WorstScenario(name="Rates +200bps", estimated_portfolio_loss_pct=-5.0),
        hidden_concentration=["Tech bundle"],
        fragilities=["Crowded tech longs"],
        risk_score=6,
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
        regime_confidence=7,
        portfolio_fit_score=6,
        mismatch_drivers=["Long duration vs rising rates"],
        mismatches=["Duration mismatch"],
        regime_appropriate_tilts=["Favor quality"],
        summary="Portfolio roughly aligned.",
    )


@pytest.fixture
def example_theme() -> ThemeReview:
    return ThemeReview(
        implicit_portfolio_bet="Overweight AI-linked growth",
        position_profiles=[],
        scored_themes=[
            ThemeMatchScore(
                theme="AI capex",
                portfolio_exposure=0.55,
                news_strength=0.72,
                confidence=0.68,
                supporting_assets=["AAPL"],
                key_evidence=["Supply chain headlines cite AI demand"],
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
        alignment_score=7,
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
        confidence_score=6,
        summary="Portfolio has concentration risk.",
    )


@pytest.fixture
def example_manager_review() -> ManagerReview:
    return ManagerReview(
        actions=[
            Action(
                action_type="reduce",
                position="AAPL",
                rationale="Tech concentration risk",
                priority="this-week",
            )
        ],
        do_nothing_case="Concentration will compound on drawdown",
        overall_confidence=6,
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
                recent_headlines=["Apple launches new product"],
            ),
        ],
        indicators=[
            MarketIndicator(
                ticker="SPY",
                label="S&P 500",
                current=5000.0,
                change_1d_pct=0.5,
                change_1m_pct=2.0,
            ),
        ],
        fetched_at="2026-03-31 12:00 UTC",
    )


def pytest_configure() -> None:
    apply_port_logging_config()
