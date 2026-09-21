"""Allocation agent — deterministic capital-allocation math + LLM deployment narrative.

Runs after the validation gate, so every upstream input it needs (market data, risk
worst scenario, news) is guaranteed present; missing inputs fail the review loudly.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from port.agents.base import build_analysis_prompt
from port.config import config
from port.llm.context import step_callback as _step_cb
from port.llm.structured import invoke_structured
from port.models.allocation import AllocationReview
from port.prompts import allocation_system_prompt

if TYPE_CHECKING:
    from port.state import GraphState

log = logging.getLogger(__name__)


def compute_allocation_base(state: GraphState) -> AllocationReview:
    """Compute the deterministic capital-allocation fields from config, portfolio, and risk."""
    portfolio = state["portfolio"]
    settings = config.capital_allocation
    cash_weight = portfolio.cash_weight
    allocated_capital = 1.0 - cash_weight
    max_cash_weight = 1.0 - settings.min_allocated_capital
    allocation_status = (
        "within minimum" if allocated_capital >= settings.min_allocated_capital else "below minimum"
    )
    required_deployment_pct = max(0.0, cash_weight - max_cash_weight)

    market_data = state["market_data"]
    if market_data is None:
        raise ValueError("allocation requires market_data before computing capital allocation")
    benchmark = next(
        (item for item in market_data.indicators if item.ticker == portfolio.benchmark),
        None,
    )
    if benchmark is None:
        raise ValueError(
            f"allocation requires market data for benchmark {portfolio.benchmark}"
        )
    benchmark_return_1y_pct = benchmark.change_1y_pct
    cash_opportunity_cost_pct = cash_weight * (
        benchmark.change_1y_pct - settings.cash_yield_annual_pct
    )

    risk_results = state["risk_results"]
    if not risk_results:
        raise ValueError("allocation requires a risk review before computing capital allocation")
    worst = risk_results[-1].worst_scenario
    if worst is None:
        raise ValueError(
            "allocation requires a deterministic worst scenario before computing capital allocation"
        )
    drawdown_budget_pct = settings.max_drawdown * 100.0
    worst_scenario_loss_pct = abs(min(0.0, worst.estimated_portfolio_loss_pct))
    drawdown_budget_breached = worst_scenario_loss_pct > drawdown_budget_pct
    deployment_required = (
        allocation_status == "below minimum" and not drawdown_budget_breached
    )

    return AllocationReview(
        cash_weight=cash_weight,
        allocated_capital=allocated_capital,
        min_allocated_capital=settings.min_allocated_capital,
        max_cash_weight=max_cash_weight,
        allocation_status=allocation_status,
        required_deployment_pct=required_deployment_pct,
        cash_yield_annual_pct=settings.cash_yield_annual_pct,
        benchmark_return_1y_pct=benchmark_return_1y_pct,
        cash_opportunity_cost_pct=cash_opportunity_cost_pct,
        drawdown_budget_pct=drawdown_budget_pct,
        worst_scenario_loss_pct=worst_scenario_loss_pct,
        drawdown_budget_breached=drawdown_budget_breached,
        deployment_required=deployment_required,
    )


def format_allocation_python_block(base: AllocationReview, *, benchmark: str) -> str:
    budget_status = "budget breached" if base.drawdown_budget_breached else "within budget"
    return "\n".join(
        [
            "=== PYTHON CAPITAL ALLOCATION ENGINE (DETERMINISTIC) ===",
            f"Allocated capital: {base.allocated_capital:.1%}",
            f"Cash weight: {base.cash_weight:.1%}",
            f"Minimum allocated capital: {base.min_allocated_capital:.1%}",
            f"Maximum cash weight: {base.max_cash_weight:.1%}",
            f"Allocation status: {base.allocation_status}",
            f"Required deployment to restore minimum: {base.required_deployment_pct:.1%} of portfolio",
            f"Assumed annual cash yield: {base.cash_yield_annual_pct:.2f}%",
            f"One-year {benchmark} return: {base.benchmark_return_1y_pct:+.2f}%",
            (
                "Historical one-year cash opportunity cost: "
                f"{base.cash_opportunity_cost_pct:+.2f}% of portfolio"
            ),
            f"Maximum drawdown budget: {base.drawdown_budget_pct:.1f}%",
            f"Worst deterministic scenario loss: {base.worst_scenario_loss_pct:.2f}%",
            f"Drawdown budget status: {budget_status}",
            f"Deployment required: {'yes' if base.deployment_required else 'no'}",
            "Benchmark comparisons are historical opportunity-cost evidence, not return forecasts.",
        ]
    )


def _merge_allocation(llm: AllocationReview, base: AllocationReview) -> AllocationReview:
    """Keep Python allocation math; LLM supplies narrative fields."""
    return llm.model_copy(
        update={
            "cash_weight": base.cash_weight,
            "allocated_capital": base.allocated_capital,
            "min_allocated_capital": base.min_allocated_capital,
            "max_cash_weight": base.max_cash_weight,
            "allocation_status": base.allocation_status,
            "required_deployment_pct": base.required_deployment_pct,
            "cash_yield_annual_pct": base.cash_yield_annual_pct,
            "benchmark_return_1y_pct": base.benchmark_return_1y_pct,
            "cash_opportunity_cost_pct": base.cash_opportunity_cost_pct,
            "drawdown_budget_pct": base.drawdown_budget_pct,
            "worst_scenario_loss_pct": base.worst_scenario_loss_pct,
            "drawdown_budget_breached": base.drawdown_budget_breached,
            "deployment_required": base.deployment_required,
        }
    )


def allocation_node(state: GraphState) -> dict:
    t0 = time.monotonic()
    log.info("started")
    _cb = _step_cb.get(None)
    if _cb:
        _cb("allocation", 0, "Computing capital allocation constraints…")
    base = compute_allocation_base(state)
    if _cb:
        _cb("allocation", 1, "Building allocation prompt…")
    if state["news_review"] is None:
        raise ValueError("allocation requires news_review before assessing deployment")
    content = build_analysis_prompt(state, portfolio_prefix="Portfolio to allocate")
    content = (
        f"{format_allocation_python_block(base, benchmark=state['portfolio'].benchmark)}"
        f"\n\n{content}"
    )

    if _cb:
        _cb("allocation", 2, "Assessing cash deployment options…")

    llm: AllocationReview = invoke_structured(  # type: ignore[assignment]
        AllocationReview,
        [SystemMessage(content=allocation_system_prompt()), HumanMessage(content=content)],
        agent="allocation",
        max_tokens=config.llm.structured_max_tokens,
        temperature=config.llm.structured_temperature,
    )
    if _cb:
        _cb("allocation", 3, "Merging allocation math with deployment narrative…")
    result = _merge_allocation(llm, base)
    log.info("done in %.1fs", time.monotonic() - t0)
    return {"allocation_results": [result]}
