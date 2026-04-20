"""Rule-based macro regime state from live indicator snapshots."""

from __future__ import annotations

from math import sqrt
from typing import TYPE_CHECKING

import pandas as pd
import yfinance as yf

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
        raise RuntimeError("market_data indicators are required for regime inference")
    t = ticker.upper()
    for row in md.indicators:
        if row.ticker.upper() == t:
            return row
    raise RuntimeError(f"required indicator {ticker} missing from market_data")


def _clip_trend(x: float, up: float, down: float) -> str:
    if x > up:
        return "up"
    if x < down:
        return "down"
    return "stable"


def infer_state_vector(md: MarketData | None) -> RegimeStateVector:
    """Map Yahoo macro rows (GLD, USO, ^TNX, EEM, EFA, SPY, QQQ, XLF, ^VIX) into a coarse state vector."""
    if not md or not md.indicators:
        raise RuntimeError("market_data indicators are required for regime inference")
    tnx = _ind_by_ticker(md, "^TNX")
    spy = _ind_by_ticker(md, "SPY")
    eem = _ind_by_ticker(md, "EEM")
    xlf = _ind_by_ticker(md, "XLF")
    gld = _ind_by_ticker(md, "GLD")
    uso = _ind_by_ticker(md, "USO")
    vix = _ind_by_ticker(md, "^VIX")
    tnx_1m = float(tnx.change_1m_pct)
    if tnx_1m > 0.5:
        rates_literal = "up"
    elif tnx_1m < -0.5:
        rates_literal = "down"
    else:
        rates_literal = "stable"

    spy_1m = float(spy.change_1m_pct)
    eem_1m = float(eem.change_1m_pct)
    if spy_1m > 0.5 and eem_1m > 0.0:
        growth = "accelerating"
    elif spy_1m < -0.5 or eem_1m < -0.5:
        growth = "slowing"
    else:
        growth = "stable"

    gld_1m = float(gld.change_1m_pct)
    uso_1m = float(uso.change_1m_pct)
    infl = _clip_trend((gld_1m + uso_1m) / 2.0, up=0.5, down=-0.5)
    inflation_trend = infl  # type: ignore[assignment]

    xlf_1m = float(xlf.change_1m_pct)
    if eem_1m < spy_1m - 1.0 and xlf_1m < 0.0:
        liquidity: str = "tight"
    elif eem_1m > 0.0 and xlf_1m > 0.0:
        liquidity = "loose"
    else:
        liquidity = "neutral"

    vix_level = float(vix.current)
    vix_1m = float(vix.change_1m_pct)
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
    return (
        f"infl_{sv.inflation_trend}_rates_{sv.rates_trend}_growth_{sv.growth_trend}_"
        f"liq_{sv.liquidity}_vol_{sv.volatility}"
    )


def regime_id_from_state_vector(sv: RegimeStateVector) -> str:
    """Stable regime identifier from the rule-based state vector (used by the analysis runner)."""
    return _regime_label(sv)


def _confidence_from_signals(md: MarketData | None, sv: RegimeStateVector) -> int:
    if not md or not md.indicators:
        raise RuntimeError("market_data indicators are required to score regime confidence")
    required = {"^TNX", "SPY", "EEM", "XLF", "GLD", "USO", "^VIX"}
    present = {row.ticker.upper() for row in md.indicators}
    coverage = len(required & present) / len(required)
    magnitude = sum(abs(float(row.change_1m_pct)) for row in md.indicators) / max(1, len(md.indicators))
    normalized_magnitude = min(1.0, magnitude / 6.0)
    stress_bonus = 0.1 if sv.volatility == "high" else 0.0
    raw = coverage * 0.7 + normalized_magnitude * 0.3 + stress_bonus
    return max(1, min(10, int(round(raw * 10.0))))


def _portfolio_fit(portfolio: Portfolio, _sv: RegimeStateVector) -> int:
    tickers = sorted({p.ticker.upper() for p in portfolio.positions} | {"SPY"})
    raw = yf.download(
        tickers=tickers,
        period="1y",
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="column",
    )
    if raw.empty:
        raise RuntimeError("failed to load 1y return history for portfolio fit scoring")
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"].copy()
    else:
        close = raw.to_frame(name=tickers[0]) if isinstance(raw, pd.Series) else raw.copy()
    close.columns = [str(c).upper() for c in close.columns]
    if "SPY" not in close.columns:
        raise RuntimeError("SPY history is required for portfolio fit scoring")
    pos_cols = [p.ticker.upper() for p in portfolio.positions]
    missing = [t for t in pos_cols if t not in close.columns]
    if missing:
        raise RuntimeError(f"missing return history for: {', '.join(sorted(set(missing)))}")
    aligned = close[pos_cols + ["SPY"]].dropna(how="any")
    if len(aligned) < 120:
        raise RuntimeError("insufficient aligned history to score portfolio fit")
    ret = aligned.pct_change().dropna(how="any")
    weights = pd.Series({p.ticker.upper(): float(p.weight) for p in portfolio.positions})
    port = ret[pos_cols].mul(weights, axis=1).sum(axis=1)
    spy = ret["SPY"]
    corr = float(port.corr(spy))
    tracking = float((port - spy).std()) * sqrt(252.0)
    raw_score = 6.0 + 2.0 * corr - 3.0 * min(1.0, tracking / 0.3)
    return max(1, min(10, int(round(raw_score))))


def compute_regime_review_base(portfolio: Portfolio, md: MarketData | None) -> RegimeReview:
    sv = infer_state_vector(md)
    label = _regime_label(sv)
    conf = _confidence_from_signals(md, sv)
    fit = _portfolio_fit(portfolio, sv)
    hist = HistoricalRegimeOutcome(
        runner_available=False,
        message="Historical analog matching is computed in the regime runner task.",
        analog_periods_identified=0,
        avg_return=None,
        max_drawdown=None,
        win_rate=None,
    )
    return RegimeReview(
        current_regime=label,
        state_vector=sv,
        regime_confidence=conf,
        portfolio_fit_score=fit,
        historical_outcome=hist,
        mismatch_drivers=[],
        mismatches=[],
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
        f"current_regime (id): {base.current_regime}",
        f"state_vector: inflation={sv.inflation_trend}, rates={sv.rates_trend}, "
        f"growth={sv.growth_trend}, liquidity={sv.liquidity}, volatility={sv.volatility}",
        f"regime_confidence (1–10): {base.regime_confidence}",
        f"portfolio_fit_score (1–10): {base.portfolio_fit_score}",
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
    else:
        lines.append("historical_outcome: runner_available=False")
    lines += [
        h.message,
        "",
        "Explain mismatches and tilts in plain language; do not contradict the state_vector labels.",
    ]
    return "\n".join(lines)
