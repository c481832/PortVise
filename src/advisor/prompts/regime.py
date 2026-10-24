"""Regime agent system prompt and review formatting."""

from __future__ import annotations

from functools import cache

from advisor.config import config
from advisor.schemas.regime import RegimeReview


@cache
def regime_system_prompt() -> str:
    g = config.prompts.regime
    return f"""You are a macro strategist. The message includes PYTHON REGIME SIGNALS: a
rule-based state vector (inflation/short rates/long rates/growth/liquidity/vol) and historical
analog portfolio performance across the top similar periods.
Your job is conditional expectation — how this book should behave in that world — not theme
stock-picking and not tail risk (that's the Risk agent).

TASK:
1. SUMMARY — {g.summary_sentence_min}-{g.summary_sentence_max} sentences translating the state
   vector + news into plain English.

2. MISMATCH_DRIVERS — factor-style reasons the portfolio may be wrong for this regime (duration,
   growth tilt, credit beta…). Name tickers where possible.

3. REGIME_APPROPRIATE_TILTS — conceptual tilts (not orders).

CONSTRAINTS:
- Keep current_regime, state_vector, and historical_outcome consistent
  with the PYTHON block (merged in code — still echo them faithfully
  in JSON).
- When historical_outcome shows runner_available=True, reference the top similar periods'
  portfolio returns and drawdowns in your summary and mismatch analysis — these are empirically
  grounded numbers, not estimates.
- Explain mismatch drivers and tilts in plain language; do not contradict the state_vector
  labels.
- Do not forecast the next regime pivot; describe the present mix vs the state vector.
- No specific trade instructions.

FORMAT: Return a RegimeReview JSON object exactly matching the schema."""


def regime_engine_to_text(base: RegimeReview) -> str:
    sv = base.state_vector
    h = base.historical_outcome
    lines = [
        "=== PYTHON REGIME SIGNALS ===",
        "",
        f"current_regime: {base.current_regime}",
        f"state_vector: inflation={sv.inflation_trend}, "
        f"short_rates={sv.short_rates_trend}, long_rates={sv.long_rates_trend}, "
        f"growth={sv.growth_trend}, liquidity={sv.liquidity}, volatility={sv.volatility}",
    ]
    if h.runner_available:
        avg = f"{h.avg_return:+.2%}" if h.avg_return is not None else "n/a"
        dd = f"{h.max_drawdown:+.2%}" if h.max_drawdown is not None else "n/a"
        wr = f"{h.win_rate:.0%}" if h.win_rate is not None else "n/a"
        lines.append(
            f"historical_outcome: runner_available=True, "
            f"analog_periods={h.analog_periods_identified}, "
            f"avg_return={avg}, max_drawdown={dd}, win_rate={wr}"
        )
        for idx, period in enumerate(h.top_similar_periods, start=1):
            ret = f"{period.portfolio_return:+.2%}"
            drawdown = f"{period.max_drawdown:+.2%}"
            lines.append(
                f"analog_{idx}: period={period.period}, forward_window={period.forward_window}, "
                f"portfolio_return={ret}, max_drawdown={drawdown}, "
                f"match_score={period.match_score}"
            )
    else:
        lines.append("historical_outcome: runner_available=False")
    lines.append(h.message)
    return "\n".join(lines)
