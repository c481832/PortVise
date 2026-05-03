"""Risk agent — Python factor/stress engine + LLM interpretation."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from port.agents._base import build_analysis_prompt
from port.config import ReviewStoppedError, invoke_structured, raise_if_review_stopped
from port.config import step_callback as _step_cb
from port.models import RiskReview
from port.prompts import RISK_SYSTEM_PROMPT
from port.risk_engine import format_risk_python_block
from port.runner import run_analysis

if TYPE_CHECKING:
    from port.portfolio import Portfolio
    from port.state import GraphState

log = logging.getLogger(__name__)

_RUNNER_MAX_ATTEMPTS = 3
_RUNNER_BACKOFF_BASE = 1.0
_RUNNER_BACKOFF_MAX = 6.0


def _runner_backoff(attempt: int) -> float:
    return min(_RUNNER_BACKOFF_BASE * (2 ** max(0, attempt - 1)), _RUNNER_BACKOFF_MAX)


def _degraded_risk_review(portfolio: Portfolio, reason: str) -> RiskReview:
    """Concentration-only fallback when the risk engine cannot run.

    Defaults preserve every required field on ``RiskReview`` so the LLM stage and the
    rest of the pipeline (validation, manager) still complete with a usable baseline.
    """
    weights = sorted((abs(float(p.weight)) for p in portfolio.positions), reverse=True)
    top5 = sum(weights[:5])
    notes = [
        "Risk engine unavailable; produced concentration-only baseline. "
        f"Underlying error: {reason}",
    ]
    issues = [f"Top 5 names ≈ {top5 * 100:.0f}% of portfolio"] if top5 > 0 else []
    return RiskReview(
        concentration_top5_pct=round(min(1.0, max(0.0, top5)), 4),
        concentration_issues=issues,
        fragilities=notes,
        risk_score=5,
        summary="",
    )


def _run_risk_engine_with_retry(payload: dict, *, step_cb=None) -> tuple[RiskReview, str | None]:
    """Run the deterministic risk engine with retry; on permanent failure, return a fallback."""
    last_exc: Exception | None = None
    for attempt in range(1, _RUNNER_MAX_ATTEMPTS + 1):
        raise_if_review_stopped()
        try:
            out = run_analysis("risk_analysis", payload)
            return RiskReview.model_validate(out["risk_review"]), None
        except ReviewStoppedError:
            raise
        except Exception as exc:
            last_exc = exc
            if attempt >= _RUNNER_MAX_ATTEMPTS:
                break
            delay = _runner_backoff(attempt)
            log.warning(
                "risk runner attempt %d/%d failed (%s) — retrying in %.1fs",
                attempt,
                _RUNNER_MAX_ATTEMPTS,
                exc,
                delay,
            )
            if step_cb:
                step_cb(
                    "risk",
                    0,
                    f"Risk engine retry {attempt}/{_RUNNER_MAX_ATTEMPTS}…",
                )
            time.sleep(delay)
    log.exception("risk runner exhausted retries; falling back to concentration-only baseline")
    return _degraded_risk_review(payload_portfolio_or_none(payload), str(last_exc)), str(last_exc)


def payload_portfolio_or_none(payload: dict):
    """Best-effort portfolio extraction for the fallback path; never raises."""
    from port.portfolio import Portfolio

    raw = payload.get("portfolio") if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        # Build an empty portfolio so concentration math still works without crashing.
        return Portfolio(name="", positions=[])
    try:
        return Portfolio.model_validate(raw)
    except Exception as exc:
        log.warning("could not re-parse portfolio for risk fallback: %s", exc)
        return Portfolio(name="", positions=[])


def _merge_risk(llm: RiskReview, base: RiskReview) -> RiskReview:
    merged_issues = list(dict.fromkeys([*base.concentration_issues, *llm.concentration_issues]))
    merged_liq = list(dict.fromkeys([*base.liquidity_notes, *llm.liquidity_notes]))
    merged_fragilities = list(dict.fromkeys([*base.fragilities, *llm.fragilities]))
    merged_top_risks = list(dict.fromkeys([*base.top_risks, *llm.top_risks]))
    return llm.model_copy(
        update={
            "factor_loadings": base.factor_loadings,
            "factor_risk_contribution": base.factor_risk_contribution,
            "marginal_risk_by_ticker": base.marginal_risk_by_ticker,
            "scenario_losses": base.scenario_losses,
            "worst_scenario": base.worst_scenario,
            "concentration_top5_pct": base.concentration_top5_pct,
            "hidden_concentration": base.hidden_concentration,
            "risk_score": base.risk_score,
            "concentration_issues": merged_issues,
            "liquidity_notes": merged_liq,
            "fragilities": merged_fragilities,
            "top_risks": merged_top_risks,
        }
    )


def risk_node(state: GraphState) -> dict:
    t0 = time.monotonic()
    log.info("started")
    portfolio = state["portfolio"]
    md = state.get("market_data")
    payload = {
        "portfolio": portfolio.model_dump(mode="json"),
        "market_data": md.model_dump(mode="json") if md else None,
    }
    _cb = _step_cb.get(None)
    base, fallback_reason = _run_risk_engine_with_retry(payload, step_cb=_cb)
    if fallback_reason and _cb:
        _cb(
            "risk",
            0,
            "Risk engine unavailable; using concentration-only baseline",
        )
    content = build_analysis_prompt(state, curated_for="risk")
    content = f"{format_risk_python_block(base)}\n\n{content}"

    if _cb:
        _cb("risk", 0, "Analysing portfolio risk…")

    llm: RiskReview = invoke_structured(  # type: ignore[assignment]
        RiskReview,
        [SystemMessage(content=RISK_SYSTEM_PROMPT), HumanMessage(content=content)],
        agent="risk",
    )
    result = _merge_risk(llm, base)
    log.info(
        "done in %.1fs%s",
        time.monotonic() - t0,
        " (fallback baseline)" if fallback_reason else "",
    )
    return {"risk_results": [result]}
