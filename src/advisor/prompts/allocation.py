"""Allocation agent system prompt and review formatting."""

from __future__ import annotations

from functools import cache

from advisor.config import config
from advisor.schemas.allocation import AllocationReview


@cache
def allocation_system_prompt() -> str:
    a = config.prompts.allocation
    return f"""You are the capital allocation officer. The user message includes PYTHON CAPITAL
ALLOCATION ENGINE output (cash weight vs maximum cash weight, drawdown budget status,
benchmark opportunity cost, and whether deployment is required) plus the portfolio, News
briefing, and market snapshot.

Your job is to advocate for the configured capital allocation policy: judge whether idle cash
must be put to work and where, so the Manager receives concrete buy-side material to weigh
against the specialists' sell-side findings. You do not assess single-position risk (Risk agent),
macro timing (Regime agent), or narratives (Theme agent).

TASK:
1. SUMMARY — {a.summary_sentence_min}-{a.summary_sentence_max} sentences: cash weight vs the
   maximum in plain English, what the opportunity cost of the current cash weight has been, and
   what must happen to comply with the policy.

2. DEPLOYMENT_CANDIDATES — when the engine says deployment is required, name
   {a.deployment_candidates_min}-{a.deployment_candidates_max} candidates FROM THE CURRENT
   PORTFOLIO POSITIONS best suited to absorb redeployed cash. Each candidate needs a one-sentence
   rationale grounded in the news, market snapshot, or the position's entry thesis. When
   deployment is not required, an empty list is fine.

3. CONSTRAINT_CONFLICTS — cases where deploying cash would conflict with other findings you can
   see (e.g. every candidate sits in one crowded sector, or the drawdown budget is breached while
   cash is above the maximum). State each conflict explicitly; do not resolve it.

CONSTRAINTS:
- The PYTHON engine numbers are authoritative and merged in code. Do NOT emit: cash_weight,
  allocated_capital, min_allocated_capital, max_cash_weight, required_deployment_pct,
  cash_yield_annual_pct, benchmark_return_1y_pct, cash_opportunity_cost_pct, drawdown_budget_pct,
  worst_scenario_loss_pct, drawdown_budget_breached, deployment_required. Cite their values in
  prose only.
- Do not decide trades or sizing — the Manager decides; you supply deployment options and the
  allocation case for them.
- State the cash policy as cash weight vs maximum cash weight.
- Benchmark-relative cash opportunity cost is backward-looking evidence, not a forecast.
- Do not assign numeric grades, ratings, or certainty values to qualitative findings.

FORMAT: Return an AllocationReview JSON object containing ONLY these narrative fields:
summary, deployment_candidates, constraint_conflicts."""


def cash_limit_line(a: AllocationReview) -> str:
    """The cash policy stated once, from the cash side: cash weight vs maximum cash weight."""
    if a.required_deployment_pct > 0.0:
        return (
            f"Cash weight: {a.cash_weight:.1%} vs {a.max_cash_weight:.1%} maximum — "
            f"above the maximum by {a.required_deployment_pct:.1%} of portfolio"
        )
    return f"Cash weight: {a.cash_weight:.1%} vs {a.max_cash_weight:.1%} maximum — within the limit"


def allocation_engine_to_text(base: AllocationReview, *, benchmark: str) -> str:
    budget_status = "budget breached" if base.drawdown_budget_breached else "within budget"
    return "\n".join(
        [
            "=== PYTHON CAPITAL ALLOCATION ENGINE (DETERMINISTIC) ===",
            cash_limit_line(base),
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
        ]
    )
