from __future__ import annotations

from datetime import date

import pytest

from port.models import (
    CriticalIssue,
    FactorExposure,
    MarketData,
    MarketIndicator,
    NewsReview,
    PositionSnapshot,
    RegimeReview,
    RiskReview,
    ScenarioLoss,
    ThemeAlignment,
    ThemeReview,
    ValidationReview,
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
        factor_exposures=[
            FactorExposure(
                factor="momentum",
                direction="long",
                magnitude="high",
                positions_driving=["AAPL"],
            ),
        ],
        concentration_issues=["Tech >30%"],
        scenario_losses=[
            ScenarioLoss(
                scenario="Rates +200bps",
                estimated_portfolio_loss_pct=-5.0,
                most_affected_positions=["AAPL"],
            ),
        ],
        fragilities=["Crowded tech longs"],
        risk_score=6,
        summary="Moderate risk from tech concentration.",
    )


@pytest.fixture
def example_regime() -> RegimeReview:
    return RegimeReview(
        current_regime="late-cycle expansion",
        regime_confidence=7,
        portfolio_fit_score=6,
        mismatches=["Duration mismatch"],
        regime_appropriate_tilts=["Favor quality"],
        summary="Portfolio roughly aligned.",
    )


@pytest.fixture
def example_theme() -> ThemeReview:
    return ThemeReview(
        dominant_market_themes=["AI capex"],
        theme_alignments=[
            ThemeAlignment(
                theme="AI capex",
                portfolio_stance="aligned",
                relevant_positions=["AAPL"],
            ),
        ],
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
