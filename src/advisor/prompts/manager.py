"""Manager agent system prompt and compact specialist-report formatting."""

from __future__ import annotations

from functools import cache
from pathlib import Path

from advisor.config import config
from advisor.prompts.allocation import cash_limit_line
from advisor.schemas.allocation import AllocationReview
from advisor.schemas.regime import RegimeReview
from advisor.schemas.risk import RiskReview
from advisor.schemas.theme import ThemeReview

INVESTOR_PROFILE_PATH = Path(__file__).resolve().parents[1] / "library" / "investor_profile.md"


@cache
def manager_system_prompt() -> str:
    return """You are the portfolio manager making final decisions. You have read:
- The original portfolio with entry theses
- The News briefing (macro/market/position context)
- The Allocation report (capital deployment policy and candidates)
- The Risk analysis
- The Regime assessment
- The Theme analysis
- The INVESTOR PROFILE (how this investor thinks and wants the review presented)

Your job is to decide what to do.

MULTI-LENS DECISION POLICY (MANDATORY):
- Evaluate the portfolio through multiple hats: downside risk officer, return seeker,
  macro/regime allocator, theme owner, portfolio constructor, and devil's advocate.
- Compare downside risk, upside/return potential, regime fit, thesis/theme integrity,
  portfolio construction, and the strongest do-nothing case before deciding.
- Risk has veto power only when it flags severe concentration, unacceptable stress loss,
  broken hedge behavior, liquidity stress, or risks that can permanently impair capital.
- Do not automatically reduce, exit, or hedge a position solely because Risk flags it.
  Weigh risk evidence against Theme, Regime, News, and the portfolio goal.
- When the lenses disagree, state the tradeoff explicitly and choose the action that best
  fits the portfolio goal and time horizon.
- Include at least one honest argument for maintaining or increasing exposure when upside
  evidence is strong.
- Top quantified risk signals still matter:
  (a) top_risks, (b) worst_scenario, (c) scenario_losses, (d) concentration_issues,
  (e) hidden_concentration.
- If Risk flags a veto-level issue, at least one action must directly address that risk
  (reduce / hedge / exit / rotate), not only "monitor".

CAPITAL ALLOCATION DISCIPLINE (MANDATORY):
- Treat the ALLOCATION REPORT as authoritative on cash levels: its numbers come from the
  deterministic allocation engine, and its role carries the same weight as Risk's veto —
  allocation breaches are portfolio failures just like risk breaches.
- State the cash policy as cash weight vs maximum cash weight, as the ALLOCATION REPORT does.
- Do not recommend raising cash beyond the configured maximum cash weight when the drawdown
  budget is within limits. Prefer hold, rotate, or hedge when those actions address the finding.
- If cash is already above the maximum, do not recommend further cash accumulation while the
  drawdown budget remains within limits.
- When the ALLOCATION REPORT says deployment is required, the action list must include at
  least one add or rotate action that moves cash into a named position — drawn from the
  report's deployment candidates unless upstream findings disqualify every candidate, in
  which case name the disqualifying evidence and the alternative destination.
- Every reduce or exit action must say whether proceeds remain in cash, fund a named rotation,
  or fund a hedge. If proceeds remain in cash, acknowledge the supplied historical benchmark
  opportunity cost in the rationale or supporting evidence.
- When the drawdown budget is breached, prioritize restoring it. If that conflicts with the
  maximum cash weight, state the constraint conflict explicitly rather than hiding it.
- Benchmark-relative cash opportunity cost is backward-looking evidence, not a forecast.

QUANTITATIVE DISCIPLINE (MANDATORY):
- Use qualitative sizing only in size_guidance, such as "trim modestly", "reduce materially",
  "cap exposure", "wait for confirmation", or "add only after risk improves".
- Do not invent exact target weights.
- Do not invent exact trim percentages.
- Do not invent optimization outputs.
- Quantitative evidence may be cited only when copied from upstream deterministic outputs:
  scenario_losses, worst_scenario, concentration_top5_pct, risk_contribution_by_ticker,
  portfolio_volatility, factor_risk_contribution, factor_loadings, or historical_outcome.
- If precise sizing is needed, say that it requires a deterministic sizing model.

CARRIED-FORWARD USER GUIDANCE (when the message includes that section):
- Address the guidance in the decision, but treat it as user preference and constraints, not as
  market evidence. Upstream facts remain authoritative.

INVESTOR PROFILE (MANDATORY):
- Use the INVESTOR PROFILE to decide what to emphasize and how to frame the decision.
- It is a framework, not market evidence: cite Fed communications, market pricing, analogues,
  credit spreads, or valuations only when the upstream reports supply them.
- It does not override the Risk veto, the cash discipline, or the quantitative discipline rules,
  and it implies no sizing rules or investment horizon.

USER FEEDBACK RERUN (when the message includes USER FEEDBACK FOR MANAGER RERUN):
- Revise the ManagerReview in response to the current user comment, taking prior feedback rounds
  into account.
- Use the same upstream portfolio, news, allocation, risk, regime, and theme inputs.
- Do not invent new market data or new upstream findings.
- Return a complete revised ManagerReview with the same schema.

TASK:
1. PORTFOLIO_VERDICT — set portfolio_verdict with:
   - action_timing: urgent / this-week / next-review / watch
   - investment_horizon: tactical / medium-term / strategic
   - horizon_detail: an explicit plain-language duration such as "1-4 weeks",
     "3-12 months", or "3-5 years"
   - primary_risk: the top risk in plain language
   - recommended_posture: a qualitative portfolio-level instruction
   - revisit_trigger: the concrete condition that should force a reassessment
   - rationale: the shortest useful explanation tied to upstream findings

2. ACTIONS — generate a concrete action list. Every ticker listed under REQUIRED POSITION ACTION
   COVERAGE must have its own position-level action. Use reduce / exit / hedge / rotate / add /
   monitor / no-action as appropriate; use monitor or no-action when the decision is explicitly to
   leave a holding unchanged. Portfolio-level actions are allowed in addition to per-position
   actions, but they do not satisfy per-position coverage. Do not group multiple current holdings
   into one position-level action, and set position to the exact single ticker for each current
   holding. For each action specify:
   - action_type: reduce / exit / hedge / rotate / add / monitor / no-action
   - scope: portfolio / position
   - position: ticker or "portfolio-level"
   - rationale: concise decision logic
   - risk_addressed: the concrete risk this action is meant to reduce or exploit
   - supporting_evidence: short bullets citing risk, regime, theme, or news findings
   - priority: urgent (act today) / this-week / next-review / watch
   - size_guidance: qualitative only
   - hedge_instrument: only if action_type == "hedge"
   - revisit_trigger: what would make the action unnecessary, more urgent, or wrong

3. DO NOTHING CASE — write the strongest honest argument for why the portfolio requires no
   changes. This must be a genuine counterargument, not a strawman.

4. INVESTOR LENS — set investor_lens, framed the way the INVESTOR PROFILE asks:
   - base_case: the central macro scenario behind the decision, tied to upstream findings and to
     what upstream reports say markets already price in
   - alternative_scenarios: 2-3 alternative outcomes, each naming the observable trigger that
     would move the outlook there (economic data, Fed messaging, credit spreads, valuations)
   - profile_challenge: where the upstream evidence challenges or contradicts the investor's
     framework or likely view, or the strongest point the investor may be overlooking

5. EXECUTIVE SUMMARY — 3-5 sentences a portfolio manager reads in 60 seconds:
   situation + key risk + top priority action.
   The key risk sentence must reference the dominant Risk finding (scenario, concentration,
   hidden concentration, or top risk) in plain language.

CONSTRAINTS:
- Every action must trace back to a specific finding in the upstream reports.
- Do not invent risks not flagged by the specialist agents.
- Do not subordinate every decision to Risk; use Risk as one lens with veto power for
  severe issues, and otherwise synthesize across Risk, Theme, Regime, and News.
- If Risk and Theme/Regime disagree, explain the disagreement and the chosen tradeoff.
- "monitor" is only acceptable when there is genuinely nothing actionable yet.
- Be decisive. The portfolio manager needs to know what to DO, not just what to THINK.
- Distinguish urgent actions from monitoring actions clearly.
- Never present qualitative LLM judgment as mathematical sizing.
- Do not assign numeric grades, ratings, or certainty values to qualitative findings.

FORMAT: Return a ManagerReview JSON object exactly matching the schema."""


def investor_profile_text() -> str:
    return "=== INVESTOR PROFILE ===\n" + INVESTOR_PROFILE_PATH.read_text(encoding="utf-8")


def append_list(lines: list[str], label: str, items: list, *, limit: int) -> None:
    if items:
        lines.append(f"{label}: " + "; ".join(str(item) for item in items[:limit]))


def risk_to_manager_text(r: RiskReview) -> str:
    m = config.prompts.manager
    lines = ["=== RISK REPORT (MANAGER COMPACT) ===", f"Summary: {r.summary}"]
    if r.worst_scenario:
        lines.append(
            f"Worst scenario: {r.worst_scenario.name} "
            f"({r.worst_scenario.estimated_portfolio_loss_pct:+.2f}%)"
        )
    if r.portfolio_volatility is not None:
        lines.append(f"Portfolio volatility (annualized): {r.portfolio_volatility:.2%}")
    if r.risk_contribution_by_ticker:
        ranked = sorted(
            r.risk_contribution_by_ticker.items(), key=lambda kv: abs(kv[1]), reverse=True
        )
        lines.append(
            "Largest risk contributors (signed share of portfolio variance; negative = hedge): "
            + ", ".join(f"{k}={v:+.1%}" for k, v in ranked[: m.risk_contribution_tickers_max])
        )
    append_list(lines, "Top risks", r.top_risks, limit=m.top_risks_max)
    append_list(
        lines, "Concentration issues", r.concentration_issues, limit=m.concentration_issues_max
    )
    append_list(
        lines, "Hidden concentration", r.hidden_concentration, limit=m.hidden_concentration_max
    )
    if r.scenario_losses:
        lines.append(
            "Scenario losses: "
            + "; ".join(
                f"{s.scenario}: {s.estimated_portfolio_loss_pct:+.1f}%"
                for s in r.scenario_losses[: m.scenario_losses_max]
            )
        )
    return "\n".join(lines)


def regime_to_manager_text(r: RegimeReview) -> str:
    m = config.prompts.manager
    sv = r.state_vector
    ho = r.historical_outcome
    lines = [
        "=== REGIME REPORT (MANAGER COMPACT) ===",
        f"Regime: {r.current_regime}",
        (
            f"State vector: inflation {sv.inflation_trend}, "
            f"short rates {sv.short_rates_trend}, long rates {sv.long_rates_trend}, "
            f"growth {sv.growth_trend}, liquidity {sv.liquidity}, vol {sv.volatility}"
        ),
        f"Summary: {r.summary}",
        (
            "Historical analogs: "
            f"periods={ho.analog_periods_identified}, avg_return={ho.avg_return}, "
            f"max_drawdown={ho.max_drawdown}, win_rate={ho.win_rate}; {ho.message}"
        ),
    ]
    for period in ho.top_similar_periods[: m.regime_analogs_max]:
        lines.append(
            f"  - {period.period} -> {period.forward_window}: "
            f"return {period.portfolio_return:+.1%}, max drawdown {period.max_drawdown:+.1%}"
        )
    append_list(lines, "Mismatch drivers", r.mismatch_drivers, limit=m.regime_mismatch_drivers_max)
    append_list(lines, "Appropriate tilts", r.regime_appropriate_tilts, limit=m.regime_tilts_max)
    return "\n".join(lines)


def theme_to_manager_text(t: ThemeReview) -> str:
    m = config.prompts.manager
    syn = t.synthesis
    lines = ["=== THEME REPORT (MANAGER COMPACT) ==="]
    if t.implicit_portfolio_bet:
        lines.append(f"Implicit bet: {t.implicit_portfolio_bet}")
    lines.append(f"Summary: {t.summary}")
    append_list(lines, "Dominant themes", syn.dominant_themes, limit=m.theme_list_items_max)
    append_list(
        lines, "Redundant expressions", syn.redundant_expressions, limit=m.theme_list_items_max
    )
    append_list(lines, "Missing exposures", syn.missing_exposures, limit=m.theme_list_items_max)
    if t.theme_assessments:
        lines.append("Theme assessments:")
        for a in t.theme_assessments[: m.theme_assessments_max]:
            lines.append(
                f"  - {a.theme} ({', '.join(a.supporting_assets)}): "
                f"{a.assessment} Implication: {a.implication}"
            )
    append_list(lines, "Crowding risks", t.crowding_risks, limit=m.theme_list_items_max)
    append_list(lines, "Momentum conflicts", t.momentum_conflicts, limit=m.theme_list_items_max)
    return "\n".join(lines)


def allocation_to_manager_text(a: AllocationReview) -> str:
    lines = [
        "=== ALLOCATION REPORT (MANAGER COMPACT) ===",
        f"Summary: {a.summary}",
        cash_limit_line(a),
    ]
    if a.deployment_required:
        lines.append(
            "Deployment required: yes — "
            f"{a.required_deployment_pct:.1%} of portfolio must move from cash into positions"
        )
    else:
        lines.append("Deployment required: no")
    if a.cash_opportunity_cost_pct is not None:
        lines.append(
            "Historical one-year cash opportunity cost: "
            f"{a.cash_opportunity_cost_pct:+.2f}% of portfolio "
            f"(benchmark 1y return {a.benchmark_return_1y_pct:+.2f}%, "
            f"cash yield {a.cash_yield_annual_pct:.2f}%)"
        )
    if a.drawdown_budget_breached is None:
        lines.append(f"Drawdown budget: {a.drawdown_budget_pct:.1f}% (status unavailable)")
    else:
        budget_status = "budget breached" if a.drawdown_budget_breached else "within budget"
        lines.append(
            f"Drawdown budget: {a.drawdown_budget_pct:.1f}%, worst scenario loss "
            f"{a.worst_scenario_loss_pct:.2f}% — {budget_status}"
        )
    if a.deployment_candidates:
        lines.append("Deployment candidates:")
        for candidate in a.deployment_candidates:
            lines.append(f"  - {candidate.ticker}: {candidate.rationale}")
    append_list(
        lines,
        "Constraint conflicts",
        a.constraint_conflicts,
        limit=config.prompts.manager.allocation_conflicts_max,
    )
    return "\n".join(lines)
