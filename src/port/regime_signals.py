"""Macro regime signals from live indicators plus historical analog outcomes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from port.models import (
    HistoricalRegimeOutcome,
    RegimeReview,
    RegimeStateVector,
)

if TYPE_CHECKING:
    from port.models import MarketData
    from port.portfolio import Portfolio


def _ind_by_ticker(md: MarketData | None, ticker: str):
    if not md or not md.indicators:
        return None
    t = ticker.upper()
    for row in md.indicators:
        if row.ticker.upper() == t:
            return row
    return None


def _clip_trend(x: float, up: float, down: float) -> str:
    if x > up:
        return "up"
    if x < down:
        return "down"
    return "stable"


def infer_state_vector(md: MarketData | None) -> RegimeStateVector:
    """Map Yahoo macro rows into a coarse state vector with neutral defaults for gaps."""
    tnx = _ind_by_ticker(md, "^TNX")
    spy = _ind_by_ticker(md, "SPY")
    eem = _ind_by_ticker(md, "EEM")
    xlf = _ind_by_ticker(md, "XLF")
    gld = _ind_by_ticker(md, "GLD")
    uso = _ind_by_ticker(md, "USO")
    vix = _ind_by_ticker(md, "^VIX")
    tnx_1m = float(tnx.change_1m_pct) if tnx is not None else 0.0
    if tnx_1m > 0.5:
        rates_literal = "up"
    elif tnx_1m < -0.5:
        rates_literal = "down"
    else:
        rates_literal = "stable"

    spy_1m = float(spy.change_1m_pct) if spy is not None else 0.0
    eem_1m = float(eem.change_1m_pct) if eem is not None else 0.0
    if spy_1m > 0.5 and eem_1m > 0.0:
        growth = "accelerating"
    elif spy_1m < -0.5 or eem_1m < -0.5:
        growth = "slowing"
    else:
        growth = "stable"

    gld_1m = float(gld.change_1m_pct) if gld is not None else 0.0
    uso_1m = float(uso.change_1m_pct) if uso is not None else 0.0
    infl = _clip_trend((gld_1m + uso_1m) / 2.0, up=0.5, down=-0.5)
    inflation_trend = infl  # type: ignore[assignment]

    xlf_1m = float(xlf.change_1m_pct) if xlf is not None else 0.0
    if eem_1m < spy_1m - 1.0 and xlf_1m < 0.0:
        liquidity: str = "tight"
    elif eem_1m > 0.0 and xlf_1m > 0.0:
        liquidity = "loose"
    else:
        liquidity = "neutral"

    vix_level = float(vix.current) if vix is not None else 16.0
    vix_1m = float(vix.change_1m_pct) if vix is not None else 0.0
    if vix_level >= 20.0 or vix_1m > 10.0 or abs(uso_1m) >= 6.0 or eem_1m <= -3.0:
        vol: str = "high"
    else:
        vol = "low"

    return RegimeStateVector(
        inflation_trend=inflation_trend,  # type: ignore[arg-type]
        rates_trend=rates_literal,  # type: ignore[arg-type]
        growth_trend=growth,  # type: ignore[arg-type]
        liquidity=liquidity,  # type: ignore[arg-type]
        volatility=vol,  # type: ignore[arg-type]
    )


def _regime_label(sv: RegimeStateVector) -> str:
    inflation = {
        "up": "rising inflation",
        "down": "cooling inflation",
        "stable": "stable inflation",
    }[sv.inflation_trend]
    rates = {
        "up": "rising rates",
        "down": "falling rates",
        "stable": "stable rates",
    }[sv.rates_trend]
    growth = {
        "accelerating": "accelerating growth",
        "slowing": "slowing growth",
        "stable": "stable growth",
    }[sv.growth_trend]
    liquidity = {
        "tight": "tight liquidity",
        "neutral": "neutral liquidity",
        "loose": "loose liquidity",
    }[sv.liquidity]
    volatility = {
        "high": "high volatility",
        "low": "low volatility",
    }[sv.volatility]
    return f"{inflation}, {rates}, {growth}, {liquidity}, {volatility}"


def compute_regime_review_base(portfolio: Portfolio, md: MarketData | None) -> RegimeReview:
    _ = portfolio
    sv = infer_state_vector(md)
    label = _regime_label(sv)
    hist = HistoricalRegimeOutcome(
        runner_available=False,
        message="Historical analog matching has not been run yet for this review.",
        analog_periods_identified=0,
        avg_return=None,
        max_drawdown=None,
        win_rate=None,
        top_similar_periods=[],
    )
    return RegimeReview(
        current_regime=label,
        state_vector=sv,
        historical_outcome=hist,
        mismatch_drivers=[],
        regime_appropriate_tilts=[],
        exposure_links=[],
        summary="",
    )


def format_regime_python_block(base: RegimeReview) -> str:
    sv = base.state_vector
    h = base.historical_outcome
    lines = [
        "=== PYTHON REGIME SIGNALS (authoritative — you refine wording only in summary/tilts) ===",
        "",
        f"current_regime: {base.current_regime}",
        f"state_vector: inflation={sv.inflation_trend}, rates={sv.rates_trend}, "
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
    lines += [
        h.message,
        "",
        "Explain mismatch drivers and tilts in plain language; "
        "do not contradict the state_vector labels.",
    ]
    return "\n".join(lines)
