"""Risk agent system prompt and review formatting."""

from __future__ import annotations

from functools import cache

from advisor.config import config
from advisor.schemas.portfolio import Portfolio
from advisor.schemas.risk import RiskReview


@cache
def risk_system_prompt() -> str:
    r = config.prompts.risk
    return f"""You are a quantitative risk officer. The user message includes PYTHON RISK
ENGINE output (factor betas, risk contribution by factor and ticker, scenario P&L, clusters)
plus News context.
Your job: interpret where this portfolio breaks — do not recompute the numeric engine block.

TASK:
1. TOP RISKS — {r.top_risks_min}-{r.top_risks_max} ranked bullets naming the dominant failure modes
   (rates shock, factor crowding, single-name dominance, etc.). Cite tickers.

2. FRAGILITIES — non-obvious ways diversified-looking lines converge in stress (name tickers).

3. CONCENTRATION — add colour beyond the engine if the news flow highlights a new crowding risk.

CONSTRAINTS:
- The PYTHON RISK ENGINE numbers are authoritative and are merged in code. Do NOT echo or
  recompute them: omit factor_loadings, factor_risk_contribution, risk_contribution_by_ticker,
  volatility_contribution_by_ticker, portfolio_volatility, scenario_losses, worst_scenario,
  concentration_top5_pct, and hidden_concentration entirely.
  Cite their values in your prose, but do not put them in the JSON.
- Every qualitative point must name specific tickers. No generic warnings.
- Do NOT duplicate Regime timing calls or Theme narratives — stay in factor + stress + structure.
- Do NOT recommend trades — that is the Manager's role.

FORMAT: Return a RiskReview JSON object containing ONLY these narrative fields: summary,
top_risks, concentration_issues. Use these exact
field names. For concentration_issues, add only new colour beyond the engine's base entries (an
empty list is fine)."""


def format_signed_shares(values: dict[str, float]) -> str:
    ranked = sorted(values.items(), key=lambda kv: abs(kv[1]), reverse=True)
    return ", ".join(f"{k}={v:+.1%}" for k, v in ranked)


def format_risk_to_weight(base: RiskReview, portfolio: Portfolio) -> str:
    weights = {
        p.ticker: abs(p.weight)
        for p in portfolio.positions
        if p.ticker in base.risk_contribution_by_ticker
    }
    covered = sum(weights.values())
    ratios = {
        t: share / (weights[t] / covered) for t, share in base.risk_contribution_by_ticker.items()
    }
    ranked = sorted(ratios.items(), key=lambda kv: kv[1], reverse=True)
    return ", ".join(f"{k}={v:.2f}x" for k, v in ranked)


def risk_engine_to_text(base: RiskReview, portfolio: Portfolio) -> str:
    volatility = (
        f"{base.portfolio_volatility:.2%}" if base.portfolio_volatility is not None else "n/a"
    )
    lines = [
        "=== PYTHON RISK ENGINE ===",
        "",
        "factor_loadings (joint-regression betas at actual weights; *_vs_market are tilts "
        "net of the market): "
        + ", ".join(f"{k}={v:+.3f}" for k, v in base.factor_loadings.items()),
        "factor_risk_contribution (signed share of portfolio variance; sums to 100% with "
        "idiosyncratic): " + format_signed_shares(base.factor_risk_contribution),
        f"portfolio_volatility (annualized, cash lowers it): {volatility}",
        "risk_contribution_by_ticker (signed share of portfolio variance; negative = hedge): "
        + format_signed_shares(base.risk_contribution_by_ticker),
        "risk-to-weight (share of risk / share of invested weight; >1 = carries more risk than "
        "its capital): " + format_risk_to_weight(base, portfolio),
        f"concentration_top5_pct: {base.concentration_top5_pct:.2f}",
        f"worst_scenario (engine): {base.worst_scenario.name if base.worst_scenario else 'n/a'} "
        f"({base.worst_scenario.estimated_portfolio_loss_pct:.2f}%)"
        if base.worst_scenario
        else "worst_scenario: n/a",
    ]
    if base.hidden_concentration:
        lines.append("hidden_concentration: " + "; ".join(base.hidden_concentration))
    if base.top_risks:
        lines.append("coverage notes (engine): " + "; ".join(base.top_risks))
    return "\n".join(lines)
