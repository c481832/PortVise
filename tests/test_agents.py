from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from port.agents._base import build_analysis_prompt
from port.agents.data import data_node, macro_indicator_rows_for_focus
from port.agents.manager import build_manager_human_message, manager_node
from port.agents.news import news_research_node, news_synthesis_node
from port.agents.planner import build_news_focus, planner_node
from port.agents.regime import regime_node
from port.agents.risk import risk_node
from port.agents.theme import theme_node
from port.agents.validation import build_validation_human_message, validation_node
from port.models import (
    DownstreamContextPlan,
    MarketData,
    MarketIndicator,
    NewsFocus,
    NewsPlannerResult,
    PositionSearchPlan,
)
from port.prompts import MANAGER_SYSTEM_PROMPT
from port.state import GraphState


def _make_full_state(
    example_portfolio, example_news, example_risk, example_regime, example_theme, example_validation
) -> GraphState:
    return cast(
        GraphState,
        {
            "portfolio": example_portfolio,
            "requested_locale": "en",
            "news_focus": None,
            "market_data": None,
            "news_research_text": None,
            "news_research_query_count": None,
            "news_review": example_news,
            "downstream_context": None,
            "risk_results": [example_risk],
            "regime_results": [example_regime],
            "theme_results": [example_theme],
            "validation_review": example_validation,
            "validation_needs_more": False,
            "validation_missing_inputs": [],
            "validation_request_note": None,
            "validation_retry_count": 0,
            "manager_review": None,
        },
    )


def _mock_llm_for_tools():
    """MagicMock satisfying make_llm(...).bind_tools(...).invoke(...) = no tool calls."""
    llm = MagicMock()
    llm.bind_tools.return_value.invoke.return_value = MagicMock(tool_calls=[])
    return llm


# ── planner ──────────────────────────────────────────────────────────────────


def test_build_news_focus(example_portfolio) -> None:
    focus = build_news_focus(example_portfolio)
    assert focus.portfolio_goal == "Test context note."
    assert any(g.ticker == "AAPL" for g in focus.position_goals)


def test_planner_node(example_portfolio) -> None:
    state = cast(GraphState, {"portfolio": example_portfolio})
    plan = NewsPlannerResult(
        portfolio_search_queries=[
            "Fed rates outlook 2026",
            "US tech earnings trends",
            "USD and liquidity",
        ],
        position_plans=[
            PositionSearchPlan(
                ticker="AAPL",
                latest_news_query="latest news for AAPL",
            ),
        ],
        brief_rationale="Focus on rates and mega-cap tech.",
    )
    with patch("port.agents.planner.invoke_structured", return_value=plan):
        result = planner_node(state)
    assert "news_focus" in result
    nf = result["news_focus"]
    assert nf.portfolio_goal == "Test context note."
    assert "Fed rates outlook 2026" in nf.portfolio_search_queries
    assert nf.position_goals[0].latest_news_query == "latest news for AAPL"


def test_planner_fills_empty_per_ticker_queries(example_portfolio) -> None:
    """Model sometimes omits per-ticker query; we backfill to 'latest news for {TICKER}'."""
    state = cast(GraphState, {"portfolio": example_portfolio})
    plan = NewsPlannerResult(
        portfolio_search_queries=["macro only", "macro two", "macro three"],
        position_plans=[PositionSearchPlan(ticker="AAPL", latest_news_query="")],
        brief_rationale="x",
    )
    with patch("port.agents.planner.invoke_structured", return_value=plan):
        result = planner_node(state)
    nf = result["news_focus"]
    assert nf.position_goals[0].latest_news_query == "latest news for AAPL"


def test_planner_phase2_downstream_context(example_portfolio, example_news) -> None:
    state = cast(
        GraphState,
        {
            "portfolio": example_portfolio,
            "news_focus": None,
            "market_data": None,
            "news_review": example_news,
        },
    )
    plan = DownstreamContextPlan(
        brief_rationale="Rates and tech.",
        risk_focus="Stress rates +200bps; watch AAPL size.",
        regime_focus="Policy on hold; risk-on tilt.",
        theme_focus="AI capex narrative.",
    )
    with patch("port.agents.planner.invoke_structured", return_value=plan):
        result = planner_node(state)
    assert result == {"downstream_context": plan}


def test_planner_phase1_when_no_news_review(example_portfolio) -> None:
    """First graph invocation: only portfolio; news_review unset → search-query planning."""
    state = cast(GraphState, {"portfolio": example_portfolio})
    fake = NewsPlannerResult(
        portfolio_search_queries=["macro", "macro b", "macro c"],
        position_plans=[
            PositionSearchPlan(
                ticker="AAPL",
                latest_news_query="latest news for AAPL",
            )
        ],
        brief_rationale="x",
    )
    with patch("port.agents.planner.invoke_structured", return_value=fake):
        result = planner_node(state)
    assert "news_focus" in result
    assert "downstream_context" not in result


def test_build_analysis_prompt_curated_risk(example_portfolio, example_news) -> None:
    dc = DownstreamContextPlan(
        risk_focus="Emphasise single-name tech beta.",
        regime_focus="",
        theme_focus="",
    )
    state = cast(
        GraphState,
        {
            "portfolio": example_portfolio,
            "news_focus": None,
            "market_data": None,
            "news_research_text": None,
            "news_review": example_news,
            "downstream_context": dc,
            "risk_results": [],
            "regime_results": [],
            "theme_results": [],
            "validation_review": None,
            "manager_review": None,
        },
    )
    text = build_analysis_prompt(state, curated_for="risk")
    assert "PLANNER-CURATED CONTEXT FOR RISK ANALYSIS" in text
    assert "Emphasise single-name tech beta." in text
    assert "MARKET CONTEXT (News Agent)" in text


# ── data ─────────────────────────────────────────────────────────────────────


def test_data_node(example_portfolio, example_market_data) -> None:
    snap = example_market_data.positions[0]
    ind = MarketIndicator(
        ticker="SPY",
        label="S&P 500",
        current=500.0,
        change_1d_pct=0.1,
        change_1m_pct=1.0,
    )

    with (
        patch("port.agents.data.fetch_position_snapshot", return_value=snap),
        patch("port.agents.data._fetch_indicator", return_value=ind),
    ):
        result = data_node(cast(GraphState, {"portfolio": example_portfolio}))

    assert "market_data" in result
    assert isinstance(result["market_data"], MarketData)


def test_data_node_macro_subset_from_focus(example_portfolio, example_market_data) -> None:
    snap = example_market_data.positions[0]
    focus = NewsFocus(macro_indicator_tickers=["SPY", "QQQ", "bogus"])
    fetch_mock = MagicMock(return_value=None)
    with (
        patch("port.agents.data.fetch_position_snapshot", return_value=snap),
        patch("port.agents.data._fetch_indicator", fetch_mock),
    ):
        result = data_node(
            cast(
                GraphState,
                {"portfolio": example_portfolio, "news_focus": focus},
            )
        )
    assert fetch_mock.call_count == 8
    tickers_called = {c[0][0] for c in fetch_mock.call_args_list}
    assert tickers_called == {"^TNX", "SPY", "EEM", "XLF", "GLD", "USO", "^VIX", "QQQ"}
    assert set(result["market_data"].errors) == tickers_called


def test_data_node_keeps_running_when_a_position_quote_is_missing(
    example_portfolio, example_market_data
) -> None:
    ind = MarketIndicator(
        ticker="SPY",
        label="S&P 500",
        current=500.0,
        change_1d_pct=0.1,
        change_1m_pct=1.0,
    )
    with (
        patch("port.agents.data.fetch_position_snapshot", return_value=None),
        patch("port.agents.data._fetch_indicator", return_value=ind),
    ):
        result = data_node(cast(GraphState, {"portfolio": example_portfolio}))
    assert result["market_data"].positions == []
    assert "AAPL" in result["market_data"].errors


def test_data_node_raises_when_no_market_data_is_usable(example_portfolio) -> None:
    with (
        patch("port.agents.data.fetch_position_snapshot", return_value=None),
        patch("port.agents.data._fetch_indicator", return_value=None),
        pytest.raises(
            RuntimeError,
            match="live market data fetch failed for all requested positions and indicators",
        ),
    ):
        data_node(cast(GraphState, {"portfolio": example_portfolio}))


def test_macro_indicator_rows_for_focus_empty_means_all() -> None:
    rows_all = macro_indicator_rows_for_focus(None)
    rows_empty = macro_indicator_rows_for_focus(NewsFocus())
    assert len(rows_all) == len(rows_empty) == 9


# ── news ──────────────────────────────────────────────────────────────────────


def test_news_research_node(example_portfolio) -> None:
    state = cast(GraphState, {"portfolio": example_portfolio, "news_focus": None})
    with patch(
        "port.agents.news._run_planned_news_searches",
        return_value=("mock research", 5),
    ):
        result = news_research_node(state)
    assert result == {
        "news_research_text": "mock research",
        "news_research_query_count": 5,
    }


def test_news_synthesis_node(example_portfolio, example_news) -> None:
    state = cast(
        GraphState,
        {
            "portfolio": example_portfolio,
            "news_focus": None,
            "market_data": None,
            "news_research_text": "tool blob",
        },
    )
    with patch("port.agents.news.invoke_structured", return_value=example_news):
        result = news_synthesis_node(state)
    assert result == {"news_review": example_news}


def test_news_synthesis_raises_when_research_empty(example_portfolio, example_news) -> None:
    state = cast(
        GraphState,
        {
            "portfolio": example_portfolio,
            "news_focus": None,
            "market_data": None,
            "news_research_text": None,
        },
    )
    with (
        patch("port.agents.news.invoke_structured", return_value=example_news),
        pytest.raises(
            RuntimeError,
            match="refusing to synthesize without real tool-gathered news data",
        ),
    ):
        news_synthesis_node(state)


# ── risk ──────────────────────────────────────────────────────────────────────


def test_risk_node(example_portfolio, example_news, example_risk) -> None:
    state = cast(
        GraphState,
        {
            "portfolio": example_portfolio,
            "news_focus": None,
            "news_review": example_news,
            "news_research_text": None,
            "market_data": None,
            "downstream_context": None,
        },
    )
    with (
        patch(
            "port.agents.risk.run_analysis",
            return_value={"risk_review": example_risk.model_dump(mode="json")},
        ),
        patch("port.agents.risk.invoke_structured", return_value=example_risk),
    ):
        result = risk_node(state)
    r = result["risk_results"][0]
    assert r.summary == example_risk.summary
    assert r.factor_loadings
    assert r.worst_scenario is not None
    assert 1 <= r.risk_score <= 10


# ── regime ────────────────────────────────────────────────────────────────────


def test_regime_node(example_portfolio, example_news, example_regime) -> None:
    state = cast(
        GraphState,
        {
            "portfolio": example_portfolio,
            "news_focus": None,
            "news_review": example_news,
            "news_research_text": None,
            "market_data": None,
            "downstream_context": None,
        },
    )
    with (
        patch(
            "port.agents.regime.run_analysis",
            return_value={"regime_review": example_regime.model_dump(mode="json")},
        ),
        patch("port.agents.regime.invoke_structured", return_value=example_regime),
    ):
        result = regime_node(state)
    r = result["regime_results"][0]
    assert r.summary == example_regime.summary
    assert r.current_regime == example_regime.current_regime


# ── theme ─────────────────────────────────────────────────────────────────────


def test_theme_node(example_portfolio, example_news, example_theme) -> None:
    state = cast(
        GraphState,
        {
            "portfolio": example_portfolio,
            "news_focus": None,
            "news_review": example_news,
            "news_research_text": None,
            "market_data": None,
            "downstream_context": None,
        },
    )
    with patch("port.agents.theme.invoke_structured", return_value=example_theme):
        result = theme_node(state)
    assert result == {"theme_results": [example_theme]}


# ── validation ────────────────────────────────────────────────────────────────


def test_build_validation_human_message(
    example_portfolio, example_news, example_risk, example_regime, example_theme
) -> None:
    msg = build_validation_human_message(
        example_portfolio,
        example_news,
        [example_risk],
        [example_regime],
        [example_theme],
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
    with patch("port.agents.validation.invoke_structured", return_value=example_validation):
        result = validation_node(state)
    assert result["validation_review"] == example_validation
    assert result["validation_needs_more"] is False
    assert result["validation_missing_inputs"] == []
    assert result["validation_retry_count"] == 0


def test_validation_node_requests_missing_inputs(example_portfolio, example_news) -> None:
    state = cast(
        GraphState,
        {
            "portfolio": example_portfolio,
            "requested_locale": "en",
            "news_focus": None,
            "market_data": None,
            "news_research_text": None,
            "news_research_query_count": None,
            "news_review": example_news,
            "downstream_context": None,
            "risk_results": [],
            "regime_results": [],
            "theme_results": [],
            "validation_review": None,
            "validation_needs_more": False,
            "validation_missing_inputs": [],
            "validation_request_note": None,
            "validation_retry_count": 0,
            "manager_review": None,
        },
    )
    result = validation_node(state)
    assert result["validation_review"] is None
    assert result["validation_needs_more"] is True
    assert set(result["validation_missing_inputs"]) == {"risk", "regime", "theme"}
    assert result["validation_retry_count"] == 1


# ── manager ───────────────────────────────────────────────────────────────────


def test_manager_prompt_requires_actionable_decision_contract() -> None:
    prompt = MANAGER_SYSTEM_PROMPT.lower()

    assert "portfolio_stance" in prompt
    assert "risk_addressed" in prompt
    assert "supporting_evidence" in prompt
    assert "revisit_trigger" in prompt
    assert "qualitative" in prompt
    assert "deterministic" in prompt
    assert "do not invent exact target weights" in prompt
    assert "do not invent exact trim percentages" in prompt
    assert "size_guidance" in prompt
    assert "qualitative only" in prompt
    assert "do not invent optimization outputs" in prompt
    assert "scenario_losses" in prompt
    assert "worst_scenario" in prompt
    assert "concentration_top5_pct" in prompt
    assert "marginal_risk_by_ticker" in prompt
    assert "factor_risk_contribution" in prompt
    assert "factor_loadings" in prompt
    assert "historical_outcome" in prompt
    assert "never present qualitative llm judgment as mathematical sizing" in prompt


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
    with patch("port.agents.manager.invoke_structured", return_value=example_manager_review):
        result = manager_node(state)
    assert result == {"manager_review": example_manager_review}
