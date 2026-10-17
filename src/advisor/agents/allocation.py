from __future__ import annotations

import logging
import time

from langchain_core.messages import HumanMessage, SystemMessage

from advisor.agents.base import build_analysis_prompt
from advisor.config import config
from advisor.llm.context import report_step
from advisor.llm.structured import invoke_structured
from advisor.prompts import allocation_system_prompt
from advisor.prompts.allocation import allocation_engine_to_text
from advisor.schemas.allocation import AllocationReview
from advisor.schemas.state import GraphState

log = logging.getLogger(__name__)


def run_allocation_engine(state: GraphState) -> AllocationReview:
    portfolio = state["portfolio"]
    settings = config.capital_allocation
    cash_weight = portfolio.cash_weight
    allocated_capital = 1.0 - cash_weight
    max_cash_weight = 1.0 - settings.min_allocated_capital
    required_deployment_pct = max(0.0, cash_weight - max_cash_weight)

    market_data = state["market_data"]
    if market_data is None:
        raise ValueError("allocation requires market_data before computing capital allocation")
    benchmark = next(
        (item for item in market_data.indicators if item.ticker == portfolio.benchmark),
        None,
    )
    if benchmark is None:
        raise ValueError(f"allocation requires market data for benchmark {portfolio.benchmark}")
    benchmark_return_1y_pct = benchmark.change_1y_pct
    cash_opportunity_cost_pct = cash_weight * (
        benchmark.change_1y_pct - settings.cash_yield_annual_pct
    )

    risk = state["risk_review"]
    if risk is None:
        raise ValueError("allocation requires a risk review before computing capital allocation")
    worst = risk.worst_scenario
    if worst is None:
        raise ValueError(
            "allocation requires a deterministic worst scenario before computing capital allocation"
        )
    drawdown_budget_pct = settings.max_drawdown * 100.0
    worst_scenario_loss_pct = abs(min(0.0, worst.estimated_portfolio_loss_pct))
    drawdown_budget_breached = worst_scenario_loss_pct > drawdown_budget_pct
    deployment_required = required_deployment_pct > 0.0 and not drawdown_budget_breached

    return AllocationReview(
        cash_weight=cash_weight,
        allocated_capital=allocated_capital,
        min_allocated_capital=settings.min_allocated_capital,
        max_cash_weight=max_cash_weight,
        required_deployment_pct=required_deployment_pct,
        cash_yield_annual_pct=settings.cash_yield_annual_pct,
        benchmark_return_1y_pct=benchmark_return_1y_pct,
        cash_opportunity_cost_pct=cash_opportunity_cost_pct,
        drawdown_budget_pct=drawdown_budget_pct,
        worst_scenario_loss_pct=worst_scenario_loss_pct,
        drawdown_budget_breached=drawdown_budget_breached,
        deployment_required=deployment_required,
    )


def merge_allocation_review(llm: AllocationReview, base: AllocationReview) -> AllocationReview:
    return llm.model_copy(
        update={
            "cash_weight": base.cash_weight,
            "allocated_capital": base.allocated_capital,
            "min_allocated_capital": base.min_allocated_capital,
            "max_cash_weight": base.max_cash_weight,
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
    report_step("allocation", 0, "Computing capital allocation constraints…")
    base = run_allocation_engine(state)
    report_step("allocation", 1, "Building allocation prompt…")
    if state["news_review"] is None:
        raise ValueError("allocation requires news_review before assessing deployment")
    content = build_analysis_prompt(state)
    content = (
        f"{allocation_engine_to_text(base, benchmark=state['portfolio'].benchmark)}\n\n{content}"
    )

    report_step("allocation", 2, "Assessing cash deployment options…")

    llm: AllocationReview = invoke_structured(  # type: ignore[assignment]
        AllocationReview,
        [SystemMessage(content=allocation_system_prompt()), HumanMessage(content=content)],
        agent="allocation",
        max_tokens=config.llm.structured_max_tokens,
        temperature=config.llm.structured_temperature,
        use_agent_model=True,
    )
    report_step("allocation", 3, "Merging allocation math with deployment narrative…")
    result = merge_allocation_review(llm, base)
    log.info("done in %.1fs", time.monotonic() - t0)
    return {"allocation_review": result}
