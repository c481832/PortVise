"""Registered task: deterministic regime analysis."""

from __future__ import annotations

from typing import Any

from port.models import HistoricalRegimeOutcome
from port.regime_signals import compute_regime_review_base
from port.runner.core.registry import register_task
from port.runner.data.loader import DataLoader
from port.runner.regime import backtest, classifier, features


@register_task("regime_analysis")
def regime_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    loader = DataLoader(payload)
    portfolio = loader.portfolio()
    md = loader.market_data()

    feat = features.build_regime_features(md)
    regime_id = classifier.classify_regime_id(md)
    analogs: list[dict[str, Any]]
    performance: dict[str, Any]
    try:
        analogs = backtest.find_similar_periods(md, regime_id, portfolio)
        performance = backtest.portfolio_performance(analogs)
    except RuntimeError as exc:
        analogs = []
        performance = {
            "available": False,
            "message": f"Historical analog matching unavailable: {exc}",
            "optimistic_return": None,
            "pessimistic_return": None,
            "extreme_return": None,
            "avg_return": None,
            "win_rate": None,
            "max_drawdown_proxy": None,
        }

    base = compute_regime_review_base(portfolio, md)
    hist = HistoricalRegimeOutcome(
        runner_available=bool(performance["available"]),
        message=str(performance["message"]),
        analog_periods_identified=len(analogs),
        avg_return=performance["avg_return"],
        max_drawdown=performance["max_drawdown_proxy"],
        win_rate=performance["win_rate"],
    )
    base = base.model_copy(update={"historical_outcome": hist})
    return {
        "task": "regime_analysis",
        "regime": regime_id,
        "features": feat,
        "analogs": analogs,
        "performance": performance,
        "regime_review": base.model_dump(mode="json"),
    }
