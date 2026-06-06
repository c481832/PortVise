from __future__ import annotations

import time
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from port.agents.data import data_node
from port.agents.manager import build_manager_human_message, manager_node
from port.agents.news import _run_planned_news_searches, news_research_node, news_synthesis_node
from port.agents.planner import build_news_focus, planner_node
from port.agents.regime import regime_node
from port.agents.risk import risk_node
from port.agents.theme import theme_node
from port.agents.validation import validation_node
from port.config import config, step_callback
from port.models import (
    MarketData,
    MarketIndicator,
    NewsFocus,
    NewsPlannerResult,
    PositionGoalFocus,
    PositionSearchPlan,
    ValidationReview,
)
from port.prompts import manager_system_prompt
from port.state import GraphState


def _make_full_state(
    example_portfolio, example_news, example_risk, example_regime, example_theme, example_validation
) -> GraphState:
    return cast(
        GraphState,
        {
            "portfolio": example_portfolio,
            "requested_locale": "en",
            "inherited_feedback": [],
            "news_focus": None,
            "market_data": None,
            "news_research_text": None,
            "news_research_query_count": None,
            "news_review": example_news,
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
    )
    with patch("port.agents.planner.invoke_structured", return_value=plan):
        result = planner_node(state)
    assert "news_focus" in result
    nf = result["news_focus"]
    assert nf.portfolio_goal == "Test context note."
    assert "Fed rates outlook 2026" in nf.portfolio_search_queries
    assert nf.position_goals[0].latest_news_query == "latest news for AAPL"


def test_planner_rejects_empty_per_ticker_queries(example_portfolio) -> None:
    state = cast(GraphState, {"portfolio": example_portfolio})
    plan = NewsPlannerResult(
        portfolio_search_queries=["macro only", "macro two", "macro three"],
        position_plans=[PositionSearchPlan(ticker="AAPL", latest_news_query="")],
    )
    with (
        patch("port.agents.planner.invoke_structured", return_value=plan),
        pytest.raises(RuntimeError, match="no latest_news_query"),
    ):
        planner_node(state)


def test_planner_always_builds_search_focus(example_portfolio) -> None:
    """Planner has a single responsibility: search and macro indicator planning."""
    state = cast(GraphState, {"portfolio": example_portfolio})
    fake = NewsPlannerResult(
        portfolio_search_queries=["macro", "macro b", "macro c"],
        position_plans=[
            PositionSearchPlan(
                ticker="AAPL",
                latest_news_query="latest news for AAPL",
            )
        ],
    )
    with patch("port.agents.planner.invoke_structured", return_value=fake):
        result = planner_node(state)
    assert "news_focus" in result


def test_planner_includes_inherited_feedback_as_guidance(example_portfolio) -> None:
    state = cast(
        GraphState,
        {
            "portfolio": example_portfolio,
            "inherited_feedback": [
                {"comment": "Research the strategic upside before recommending a trim."}
            ],
        },
    )
    fake = NewsPlannerResult(
        portfolio_search_queries=["macro", "macro b", "macro c"],
        position_plans=[
            PositionSearchPlan(ticker="AAPL", latest_news_query="latest news for AAPL")
        ],
    )
    with patch("port.agents.planner.invoke_structured", return_value=fake) as invoke:
        planner_node(state)

    human = invoke.call_args.args[1][1].content
    assert "CARRIED-FORWARD USER GUIDANCE" in human
    assert "Research the strategic upside" in human
    assert "not as market evidence" in human




def test_data_node(example_portfolio, example_market_data) -> None:
    snap = example_market_data.positions[0]
    ind = MarketIndicator(
        ticker="SPY",
        label="S&P 500",
        current=500.0,
        prev_close=499.0,
        change_1d_pct=0.1,
        change_1w_pct=0.5,
        change_1m_pct=1.0,
        change_3m_pct=2.0,
        change_1y_pct=3.0,
        week_52_high=510.0,
        week_52_low=400.0,
        pct_from_52w_high=-1.96,
    )

    with (
        patch("port.agents.data.fetch_position_snapshot", return_value=snap) as fetch_snapshot,
        patch("port.agents.data._fetch_indicator", return_value=ind),
    ):
        result = data_node(cast(GraphState, {"portfolio": example_portfolio}))

    assert "market_data" in result
    assert isinstance(result["market_data"], MarketData)
    fetch_snapshot.assert_called_once_with("AAPL", example_portfolio.positions[0].entry_date)


def test_data_node_always_fetches_fixed_macro_basket(
    example_portfolio, example_market_data
) -> None:
    snap = example_market_data.positions[0]

    def fake_indicator(ticker: str, label: str) -> MarketIndicator:
        return MarketIndicator(
            ticker=ticker,
            label=label,
            current=100.0,
            prev_close=99.0,
            change_1d_pct=0.1,
            change_1w_pct=0.5,
            change_1m_pct=1.0,
            change_3m_pct=2.0,
            change_1y_pct=3.0,
            week_52_high=110.0,
            week_52_low=90.0,
            pct_from_52w_high=-9.09,
        )

    fetch_mock = MagicMock(side_effect=fake_indicator)
    with (
        patch("port.agents.data.fetch_position_snapshot", return_value=snap),
        patch("port.agents.data._fetch_indicator", fetch_mock),
    ):
        result = data_node(
            cast(
                GraphState,
                {
                    "portfolio": example_portfolio,
                    "news_focus": NewsFocus(
                        portfolio_goal="",
                        portfolio_search_queries=[],
                        position_goals=[],
                    ),
                },
            )
        )
    expected = set(config.macro.indicator_universe)
    assert fetch_mock.call_count == len(expected)
    tickers_called = {c[0][0] for c in fetch_mock.call_args_list}
    assert tickers_called == expected
    assert result["market_data"].errors == []
    assert {i.ticker for i in result["market_data"].indicators} == expected


def test_data_node_progress_labels_include_fetched_items(
    example_portfolio, example_market_data
) -> None:
    snap = example_market_data.positions[0]

    def fake_indicator(ticker: str, label: str) -> MarketIndicator:
        return MarketIndicator(
            ticker=ticker,
            label=label,
            current=100.0,
            prev_close=99.0,
            change_1d_pct=0.1,
            change_1w_pct=0.5,
            change_1m_pct=1.0,
            change_3m_pct=2.0,
            change_1y_pct=3.0,
            week_52_high=110.0,
            week_52_low=90.0,
            pct_from_52w_high=-9.09,
        )

    step_labels: list[tuple[str, int, str]] = []
    token = step_callback.set(lambda agent, step, label: step_labels.append((agent, step, label)))
    try:
        with (
            patch("port.agents.data.fetch_position_snapshot", return_value=snap),
            patch("port.agents.data._fetch_indicator", side_effect=fake_indicator),
            patch("port.agents.data._fetch_risk_factor_history", side_effect=lambda ticker: ticker),
        ):
            data_node(cast(GraphState, {"portfolio": example_portfolio}))
    finally:
        step_callback.reset(token)

    labels = [label for _agent, _step, label in step_labels]
    assert any("Queued positions: AAPL" in label for label in labels)
    assert any("Fetched position AAPL 1/1" in label for label in labels)
    assert any("GLD (Gold)" in label for label in labels)
    assert any("Fetched macro indicator" in label and "SPY (S&P 500)" in label for label in labels)
    assert any(
        "Fetching risk-factor histories" in label and "UUP (factor: uup)" in label
        for label in labels
    )


def test_data_node_keeps_running_when_a_position_quote_is_missing(
    example_portfolio, example_market_data
) -> None:
    ind = MarketIndicator(
        ticker="SPY",
        label="S&P 500",
        current=500.0,
        prev_close=499.0,
        change_1d_pct=0.1,
        change_1w_pct=0.5,
        change_1m_pct=1.0,
        change_3m_pct=2.0,
        change_1y_pct=3.0,
        week_52_high=510.0,
        week_52_low=400.0,
        pct_from_52w_high=-1.96,
    )
    with (
        patch("port.agents.data.fetch_position_snapshot", return_value=None),
        patch("port.agents.data._fetch_indicator", return_value=ind),
    ):
        result = data_node(cast(GraphState, {"portfolio": example_portfolio}))
    assert result["market_data"].positions == []
    assert "AAPL" in result["market_data"].errors


def test_data_node_raises_when_macro_indicator_fetch_fails(example_portfolio) -> None:
    with (
        patch("port.agents.data.fetch_position_snapshot", return_value=None),
        patch("port.agents.data._fetch_indicator", side_effect=RuntimeError("SPY failed")),
        pytest.raises(RuntimeError, match="SPY failed"),
    ):
        data_node(cast(GraphState, {"portfolio": example_portfolio}))




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


def test_news_research_runs_searches_concurrently_preserving_order(example_portfolio) -> None:
    focus = NewsFocus(
        portfolio_goal="",
        portfolio_search_queries=["macro a", "macro b", "macro c"],
        position_goals=[
            PositionGoalFocus(
                ticker="AAPL",
                goal="Apple",
                latest_news_query="latest news for AAPL",
            ),
        ],
    )
    calls: list[str] = []
    step_labels: list[tuple[str, int, str]] = []

    def fake_search(query: str, *, max_results: int) -> str:
        calls.append(query)
        time.sleep(0.1)
        return f"result for {query} ({max_results})"

    fake_config = SimpleNamespace(
        search=SimpleNamespace(concurrent_requests=4, default_max_results=2)
    )
    t0 = time.monotonic()
    with (
        patch("port.agents.news.config", fake_config),
        patch("port.agents.news._web_finance_news_text", side_effect=fake_search),
    ):
        research, query_count = _run_planned_news_searches(
            example_portfolio,
            focus,
            step_cb=lambda agent, step, label: step_labels.append((agent, step, label)),
        )

    assert query_count == 4
    assert time.monotonic() - t0 < 0.3
    assert set(calls) == {"macro a", "macro b", "macro c", "latest news for AAPL"}
    assert research.split("\n\n---\n\n") == [
        "### Query: macro a\nresult for macro a (2)",
        "### Query: macro b\nresult for macro b (2)",
        "### Query: macro c\nresult for macro c (2)",
        "### Query: latest news for AAPL\nresult for latest news for AAPL (2)",
    ]
    assert step_labels == [
        ("news", 1, "Searching 4 news sources…"),
        ("news", 2, "Combined 4 search result sets…"),
    ]


def test_news_synthesis_node_uses_only_retrieved_news(
    example_portfolio, example_market_data, example_news
) -> None:
    state = cast(
        GraphState,
        {
            "portfolio": example_portfolio,
            "news_focus": None,
            "market_data": example_market_data,
            "news_research_text": "tool blob",
        },
    )
    invoke = MagicMock(return_value=example_news)
    with patch("port.agents.news.invoke_structured", invoke):
        result = news_synthesis_node(state)
    assert result == {"news_review": example_news}
    messages = invoke.call_args.args[1]
    human_content = messages[1].content
    assert "tool blob" in human_content
    assert "=== TOOL-GATHERED RESEARCH ===" in human_content
    assert "=== LIVE MARKET DATA ===" not in human_content


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




def test_risk_node(example_portfolio, example_news, example_risk) -> None:
    state = cast(
        GraphState,
        {
            "portfolio": example_portfolio,
            "news_focus": None,
            "news_review": example_news,
            "news_research_text": None,
            "market_data": None,
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
    assert r.marginal_risk_by_ticker


def test_risk_node_retries_runner_then_raises(example_portfolio, example_news) -> None:
    state = cast(
        GraphState,
        {
            "portfolio": example_portfolio,
            "news_focus": None,
            "news_review": example_news,
            "news_research_text": None,
            "market_data": None,
        },
    )
    runner_calls = {"count": 0}

    def always_fails(_task: str, _payload: dict) -> dict:
        runner_calls["count"] += 1
        raise RuntimeError("yfinance returned empty history")

    with (
        patch("port.agents.risk.run_analysis", side_effect=always_fails),
        patch("port.agents.risk.time.sleep", lambda _s: None),
        pytest.raises(RuntimeError, match="yfinance returned empty history"),
    ):
        risk_node(state)
    assert runner_calls["count"] == 3


def test_risk_node_retries_then_succeeds(example_portfolio, example_news, example_risk) -> None:
    """A transient runner failure on the first attempt must not abort the agent."""
    state = cast(
        GraphState,
        {
            "portfolio": example_portfolio,
            "news_focus": None,
            "news_review": example_news,
            "news_research_text": None,
            "market_data": None,
        },
    )
    runner_calls = {"count": 0}

    def flaky(_task: str, _payload: dict) -> dict:
        runner_calls["count"] += 1
        if runner_calls["count"] < 2:
            raise RuntimeError("transient yfinance hiccup")
        return {"risk_review": example_risk.model_dump(mode="json")}

    with (
        patch("port.agents.risk.run_analysis", side_effect=flaky),
        patch("port.agents.risk.time.sleep", lambda _s: None),
        patch("port.agents.risk.invoke_structured", return_value=example_risk),
    ):
        result = risk_node(state)
    assert runner_calls["count"] == 2
    r = result["risk_results"][0]
    assert r.factor_loadings
    assert r.summary == example_risk.summary




def test_regime_node(example_portfolio, example_news, example_regime) -> None:
    state = cast(
        GraphState,
        {
            "portfolio": example_portfolio,
            "news_focus": None,
            "news_review": example_news,
            "news_research_text": None,
            "market_data": None,
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


def test_regime_node_retries_runner_then_raises(example_portfolio, example_news) -> None:
    state = cast(
        GraphState,
        {
            "portfolio": example_portfolio,
            "news_focus": None,
            "news_review": example_news,
            "news_research_text": None,
            "market_data": None,
        },
    )
    runner_calls = {"count": 0}

    def always_fails(_task: str, _payload: dict) -> dict:
        runner_calls["count"] += 1
        raise RuntimeError("missing indicator ^TNX in market_data")

    with (
        patch("port.agents.regime.run_analysis", side_effect=always_fails),
        patch("port.agents.regime.time.sleep", lambda _s: None),
        pytest.raises(RuntimeError, match="missing indicator"),
    ):
        regime_node(state)
    assert runner_calls["count"] == 3




def test_theme_node(example_portfolio, example_news, example_theme) -> None:
    state = cast(
        GraphState,
        {
            "portfolio": example_portfolio,
            "news_focus": None,
            "news_review": example_news,
            "news_research_text": None,
            "market_data": None,
        },
    )
    with patch("port.agents.theme.invoke_structured", return_value=example_theme):
        result = theme_node(state)
    assert result == {"theme_results": [example_theme]}


def test_theme_node_truncates_news_research(example_portfolio, example_news, example_theme) -> None:
    query = "latest news for AAPL"
    raw_research = f"### Query: {query}\n" + ("x" * 15050)
    state = cast(
        GraphState,
        {
            "portfolio": example_portfolio,
            "news_focus": NewsFocus(
                portfolio_goal="Test context note.",
                portfolio_search_queries=["macro one", "macro two", "macro three"],
                position_goals=[
                    PositionGoalFocus(
                        ticker="AAPL",
                        goal="Strong ecosystem and services growth",
                        latest_news_query=query,
                    )
                ],
            ),
            "news_review": example_news,
            "news_research_text": raw_research,
            "market_data": None,
        },
    )
    captured: dict[str, str] = {}

    def _fake_invoke(_schema, messages, *, agent):
        assert agent == "theme"
        captured["content"] = messages[1].content
        return example_theme

    with patch("port.agents.theme.invoke_structured", side_effect=_fake_invoke):
        result = theme_node(state)

    assert result == {"theme_results": [example_theme]}
    assert "... (truncated)" in captured["content"]
    assert "x" * (config.prompts.theme.research_excerpt_max_chars + 1) not in captured["content"]




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
    result = validation_node(state)
    assert result["validation_review"] == ValidationReview(
        critical_issues=[],
        thesis_breaks=[],
        internal_contradictions=[],
        summary="Completeness check passed: news, risk, regime, and theme outputs are present.",
    )
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




def test_manager_prompt_requires_actionable_decision_contract() -> None:
    prompt = manager_system_prompt().lower()

    assert "portfolio_verdict" in prompt
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
    assert "multi-lens decision policy" in prompt
    assert "downside risk officer" in prompt
    assert "return seeker" in prompt
    assert "macro/regime allocator" in prompt
    assert "theme owner" in prompt
    assert "portfolio constructor" in prompt
    assert "devil's advocate" in prompt
    assert "risk has veto power only" in prompt
    assert "do not automatically reduce, exit, or hedge" in prompt
    assert "when the lenses disagree" in prompt
    assert "do not subordinate every decision to risk" in prompt
    assert "explain the disagreement and the chosen tradeoff" in prompt
    assert "every current holding" in prompt
    assert "required position action" in prompt
    assert "coverage must have its own position-level action" in prompt
    assert "portfolio-level actions are allowed in addition" in prompt
    assert "do not group multiple current holdings" in prompt
    assert "risk-first decision policy" not in prompt
    assert "treat the risk analysis as the primary source" not in prompt


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
    assert "MANAGER COMPACT" in msg
    assert "REQUIRED POSITION ACTION COVERAGE" in msg
    assert "AAPL" in msg
    assert "VALIDATION" not in msg
    assert "Factor loadings" not in msg


def test_build_manager_human_message_includes_inherited_feedback(
    example_portfolio,
    example_news,
    example_risk,
    example_regime,
    example_theme,
    example_validation,
) -> None:
    state = _make_full_state(
        example_portfolio,
        example_news,
        example_risk,
        example_regime,
        example_theme,
        example_validation,
    )
    state["inherited_feedback"] = [
        {"comment": "Compare hedging with reducing the position."}
    ]

    msg = build_manager_human_message(state)

    assert "CARRIED-FORWARD USER GUIDANCE" in msg
    assert "Compare hedging with reducing the position." in msg
    assert "not as market evidence" in msg


def test_build_manager_human_message_limits_risk_details(
    example_portfolio,
    example_news,
    example_risk,
    example_regime,
    example_theme,
    example_validation,
) -> None:
    max_items = config.prompts.manager.top_risks_max
    risk = example_risk.model_copy(
        update={"top_risks": [f"risk item {idx}" for idx in range(max_items + 1)]}
    )
    state = _make_full_state(
        example_portfolio,
        example_news,
        risk,
        example_regime,
        example_theme,
        example_validation,
    )

    msg = build_manager_human_message(state)
    assert f"risk item {max_items - 1}" in msg
    assert f"risk item {max_items}" not in msg


def test_build_manager_human_message_requires_validation(
    example_portfolio, example_news, example_risk, example_regime, example_theme
) -> None:
    state = _make_full_state(
        example_portfolio,
        example_news,
        example_risk,
        example_regime,
        example_theme,
        None,
    )

    with pytest.raises(ValueError, match="manager requires validation_review"):
        build_manager_human_message(state)


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


def test_manager_node_requires_action_for_every_position(
    example_portfolio,
    example_news,
    example_risk,
    example_regime,
    example_theme,
    example_validation,
    example_manager_review,
) -> None:
    msft = example_portfolio.positions[0].model_copy(
        update={
            "ticker": "MSFT",
            "name": "Microsoft",
            "entry_thesis": "Cloud and AI growth",
        }
    )
    portfolio = example_portfolio.model_copy(
        update={"positions": [*example_portfolio.positions, msft]}
    )
    state = _make_full_state(
        portfolio,
        example_news,
        example_risk,
        example_regime,
        example_theme,
        example_validation,
    )

    with (
        patch("port.agents.manager.invoke_structured", return_value=example_manager_review),
        pytest.raises(ValueError, match="missing position-level coverage for: MSFT"),
    ):
        manager_node(state)
