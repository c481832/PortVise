from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, patch

from port.agents.data import data_node
from port.agents.manager import build_manager_human_message, manager_node
from port.agents.news import news_node
from port.agents.planner import build_news_focus, planner_node
from port.agents.regime import regime_node
from port.agents.risk import risk_node
from port.agents.theme import theme_node
from port.agents.validation import build_validation_human_message, validation_node
from port.models import MarketData
from port.state import GraphState


def _make_full_state(
    example_portfolio, example_news, example_risk, example_regime, example_theme, example_validation
) -> GraphState:
    return cast(
        GraphState,
        {
            "portfolio": example_portfolio,
            "news_focus": None,
            "market_data": None,
            "news_review": example_news,
            "risk_results": [example_risk],
            "regime_results": [example_regime],
            "theme_results": [example_theme],
            "validation_review": example_validation,
            "manager_review": None,
        },
    )


def _mock_llm(return_value):
    """MagicMock satisfying make_llm(...).with_structured_output(...).invoke(...) = return_value."""
    chain = MagicMock()
    chain.invoke.return_value = return_value
    llm = MagicMock()
    llm.with_structured_output.return_value = chain
    llm.bind_tools.return_value.invoke.return_value = MagicMock(tool_calls=[])
    return llm


# ── planner ──────────────────────────────────────────────────────────────────


def test_build_news_focus(example_portfolio) -> None:
    focus = build_news_focus(example_portfolio)
    assert focus.portfolio_goal == "Test context note."
    assert any(g.ticker == "AAPL" for g in focus.position_goals)


def test_planner_node(example_portfolio) -> None:
    state = cast(GraphState, {"portfolio": example_portfolio})
    result = planner_node(state)
    assert "news_focus" in result
    assert result["news_focus"].portfolio_goal == "Test context note."


# ── data ─────────────────────────────────────────────────────────────────────


def test_data_node(example_portfolio, example_market_data) -> None:
    snap = example_market_data.positions[0]

    with (
        patch("port.agents.data.fetch_position_snapshot", return_value=snap),
        patch("port.agents.data._fetch_indicator", return_value=None),
    ):
        result = data_node(cast(GraphState, {"portfolio": example_portfolio}))

    assert "market_data" in result
    assert isinstance(result["market_data"], MarketData)


# ── news ──────────────────────────────────────────────────────────────────────


def test_news_node(example_portfolio, example_news) -> None:
    state = cast(
        GraphState, {"portfolio": example_portfolio, "news_focus": None, "market_data": None}
    )
    mock_llm = _mock_llm(example_news)
    with (
        patch("port.agents.news.make_llm", return_value=mock_llm),
        patch("port.agents.news._run_tool_research", return_value="mock research"),
    ):
        result = news_node(state)
    assert result == {"news_review": example_news}


# ── risk ──────────────────────────────────────────────────────────────────────


def test_risk_node(example_portfolio, example_news, example_risk) -> None:
    state = cast(
        GraphState,
        {"portfolio": example_portfolio, "news_review": example_news, "market_data": None},
    )
    with patch("port.agents.risk.make_llm", return_value=_mock_llm(example_risk)):
        result = risk_node(state)
    assert result == {"risk_results": [example_risk]}


# ── regime ────────────────────────────────────────────────────────────────────


def test_regime_node(example_portfolio, example_news, example_regime) -> None:
    state = cast(
        GraphState,
        {"portfolio": example_portfolio, "news_review": example_news, "market_data": None},
    )
    with patch("port.agents.regime.make_llm", return_value=_mock_llm(example_regime)):
        result = regime_node(state)
    assert result == {"regime_results": [example_regime]}


# ── theme ─────────────────────────────────────────────────────────────────────


def test_theme_node(example_portfolio, example_news, example_theme) -> None:
    state = cast(
        GraphState,
        {"portfolio": example_portfolio, "news_review": example_news, "market_data": None},
    )
    with patch("port.agents.theme.make_llm", return_value=_mock_llm(example_theme)):
        result = theme_node(state)
    assert result == {"theme_results": [example_theme]}


# ── validation ────────────────────────────────────────────────────────────────


def test_build_validation_human_message(
    example_portfolio, example_news, example_risk, example_regime, example_theme
) -> None:
    msg = build_validation_human_message(
        example_portfolio, example_news, example_risk, example_regime, example_theme
    )
    assert "ORIGINAL PORTFOLIO" in msg
    assert "MARKET CONTEXT" in msg
    assert "RISK REPORT" in msg
    assert "REGIME REPORT" in msg
    assert "THEME REPORT" in msg


def test_validation_node(
    example_portfolio, example_news, example_risk, example_regime, example_theme, example_validation
) -> None:
    state = _make_full_state(
        example_portfolio,
        example_news,
        example_risk,
        example_regime,
        example_theme,
        example_validation,
    )
    with patch("port.agents.validation.make_llm", return_value=_mock_llm(example_validation)):
        result = validation_node(state)
    assert result == {"validation_review": example_validation}


# ── manager ───────────────────────────────────────────────────────────────────


def test_build_manager_human_message(
    example_portfolio, example_news, example_risk, example_regime, example_theme, example_validation
) -> None:
    state = _make_full_state(
        example_portfolio,
        example_news,
        example_risk,
        example_regime,
        example_theme,
        example_validation,
    )
    msg = build_manager_human_message(state)
    assert "ORIGINAL PORTFOLIO" in msg
    assert "RISK REPORT" in msg
    assert "VALIDATION SYNTHESIS" in msg


def test_manager_node(
    example_portfolio,
    example_news,
    example_risk,
    example_regime,
    example_theme,
    example_validation,
    example_manager_review,
) -> None:
    state = _make_full_state(
        example_portfolio,
        example_news,
        example_risk,
        example_regime,
        example_theme,
        example_validation,
    )
    with patch("port.agents.manager.make_llm", return_value=_mock_llm(example_manager_review)):
        result = manager_node(state)
    assert result == {"manager_review": example_manager_review}
