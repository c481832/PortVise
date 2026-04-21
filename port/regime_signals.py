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


def _clip_unit(x: float) -> float:
    return max(-1.0, min(1.0, x))


def _state_target(label: str) -> float:
    return {
        "up": 1.0,
        "down": -1.0,
        "accelerating": 1.0,
        "slowing": -1.0,
        "loose": 1.0,
        "tight": -1.0,
        "high": 1.0,
        "low": -1.0,
        "stable": 0.0,
        "neutral": 0.0,
    }.get(label, 0.0)


def _fit_component(signal: float, target: float) -> float:
    signal = _clip_unit(signal)
    if target == 0.0:
        return max(0.0, 1.0 - abs(signal))
    return max(0.0, 1.0 - abs(signal - target) / 2.0)


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _position_regime_exposures(position) -> dict[str, float]:
    text = " ".join(
        [
            position.ticker,
            position.name,
            position.sector,
            position.asset_class,
            position.country,
            position.entry_thesis,
            " ".join(position.tags),
        ]
    ).lower()
    sector = (position.sector or "").strip().lower()
    asset_class = (position.asset_class or "").strip().lower()
    exposure = {
        "inflation": 0.0,
        "rates": 0.0,
        "growth": 0.0,
        "liquidity": 0.0,
        "volatility": 0.0,
    }

    def add(key: str, amount: float) -> None:
        exposure[key] = _clip_unit(exposure[key] + amount)

    if asset_class in {"bond", "fixed income"} or _contains_any(
        text, ("treasury", "duration", "bond", "fixed income", "tlt", "ief")
    ):
        add("rates", -1.0)
        add("volatility", 0.5)

    if sector in {"energy", "materials"} or _contains_any(
        text, ("oil", "gas", "energy", "commodity", "uso", "xom", "cvx")
    ):
        add("inflation", 0.8)
        add("growth", 0.2)
        add("volatility", -0.1)

    if _contains_any(text, ("gold", "bullion", "gld")):
        add("inflation", 0.6)
        add("volatility", 0.7)
        add("growth", -0.2)

    if sector == "financials" or _contains_any(text, ("bank", "financial", "insurance", "jpm")):
        add("rates", 0.6)
        add("growth", 0.2)
        add("volatility", -0.2)

    if sector in {"technology", "consumer discretionary", "industrials"} or _contains_any(
        text, ("ai", "cloud", "software", "semiconductor", "chip", "growth", "asml", "nvda")
    ):
        add("growth", 0.9)
        add("liquidity", 0.8)
        add("volatility", -0.7)

    if sector in {"healthcare", "utilities", "consumer staples", "telecom"} or _contains_any(
        text, ("defensive", "quality", "dividend", "staples", "utility")
    ):
        add("growth", -0.4)
        add("liquidity", -0.2)
        add("volatility", 0.6)

    return exposure


def _series_from_frame(frame: pd.DataFrame, column: str) -> pd.Series:
    data = frame.loc[:, column]
    if isinstance(data, pd.DataFrame):
        return data.iloc[:, 0]
    return data


def _extract_close_frame(
    raw: pd.DataFrame | pd.Series | None, requested: list[str]
) -> pd.DataFrame:
    if raw is None or raw.empty:
        raise RuntimeError("Empirical fit unavailable: failed to load 1y return history.")
    if isinstance(raw, pd.DataFrame) and isinstance(raw.columns, pd.MultiIndex):
        if "Close" not in raw.columns.get_level_values(0):
            raise RuntimeError("Empirical fit unavailable: close prices missing from history.")
        close_slice = raw.xs("Close", axis=1, level=0, drop_level=True)
        close = (
            pd.DataFrame(close_slice)
            if isinstance(close_slice, pd.DataFrame)
            else close_slice.to_frame()
        )
    elif isinstance(raw, pd.Series):
        close = raw.to_frame(name=requested[0])
    else:
        close = pd.DataFrame(raw.copy())
        if len(requested) == 1 and "Close" in close.columns:
            close = close[["Close"]].copy()
            close.columns = pd.Index([requested[0]])
    close.columns = pd.Index([str(c).upper() for c in close.columns])
    return pd.DataFrame(close.sort_index().dropna(how="all"))


def _structural_fit_score(portfolio: Portfolio, sv: RegimeStateVector) -> float:
    total_abs_weight = sum(abs(float(p.weight)) for p in portfolio.positions)
    if total_abs_weight <= 0:
        return 0.5
    aggregate = {
        "inflation": 0.0,
        "rates": 0.0,
        "growth": 0.0,
        "liquidity": 0.0,
        "volatility": 0.0,
    }
    for position in portfolio.positions:
        weight = abs(float(position.weight)) / total_abs_weight
        exposure = _position_regime_exposures(position)
        for key, value in exposure.items():
            aggregate[key] += weight * value

    components = [
        _fit_component(aggregate["inflation"], _state_target(sv.inflation_trend)),
        _fit_component(aggregate["rates"], _state_target(sv.rates_trend)),
        _fit_component(aggregate["growth"], _state_target(sv.growth_trend)),
        _fit_component(aggregate["liquidity"], _state_target(sv.liquidity)),
        _fit_component(aggregate["volatility"], _state_target(sv.volatility)),
    ]
    return sum(components) / len(components)


def _empirical_fit_score(portfolio: Portfolio) -> tuple[float | None, list[str]]:
    tickers = sorted({p.ticker.upper() for p in portfolio.positions} | {"SPY"})
    if tickers == ["SPY"]:
        return None, ["Portfolio fit uses structural exposures because no holdings were provided."]
    raw = yf.download(
        tickers=tickers,
        period="1y",
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="column",
    )
    try:
        close = _extract_close_frame(raw, tickers)
    except RuntimeError as exc:
        return None, [str(exc)]
    if "SPY" not in close.columns:
        return None, ["Empirical fit unavailable: SPY history is missing."]

    pos_cols = [p.ticker.upper() for p in portfolio.positions]
    weight_map = {p.ticker.upper(): float(p.weight) for p in portfolio.positions}
    total_abs_weight = sum(abs(weight_map[t]) for t in pos_cols)
    eligible = []
    excluded: list[str] = []
    history_counts = {
        ticker: int(_series_from_frame(close, ticker).dropna().shape[0])
        if ticker in close.columns
        else 0
        for ticker in pos_cols
    }
    for ticker in pos_cols:
        count = history_counts[ticker]
        if count >= 120:
            eligible.append(ticker)
        elif count <= 0:
            excluded.append(f"{ticker} (no return history)")
        else:
            excluded.append(f"{ticker} ({count} trading days)")

    aligned: pd.DataFrame | None = None
    while eligible:
        candidate = pd.DataFrame(close.loc[:, eligible + ["SPY"]]).dropna(how="any")
        if len(candidate) >= 120:
            aligned = candidate
            break
        worst = min(eligible, key=lambda ticker: (history_counts[ticker], abs(weight_map[ticker])))
        eligible.remove(worst)
        excluded.append(
            f"{worst} (insufficient overlap with peers; only {len(candidate)} aligned days)"
        )

    covered_abs_weight = sum(abs(weight_map[t]) for t in eligible)
    coverage_ratio = covered_abs_weight / total_abs_weight if total_abs_weight > 0 else 0.0
    notes: list[str] = []
    if excluded:
        notes.append(
            "Empirical fit excludes holdings with incomplete history: " + ", ".join(excluded[:8])
        )
    if coverage_ratio < 1.0:
        notes.append(f"Empirical fit uses {coverage_ratio:.0%} of invested portfolio weight.")
    if not eligible or aligned is None or coverage_ratio < 0.5:
        notes.append(
            "Portfolio fit leans on structural exposure heuristics because "
            "price-history coverage is thin."
        )
        return None, notes

    returns = pd.DataFrame(aligned.pct_change()).dropna(how="any")
    if returns.empty:
        notes.append("Empirical fit returned no aligned daily returns after cleanup.")
        return None, notes

    weights = pd.Series({ticker: weight_map[ticker] for ticker in eligible}, dtype=float)
    abs_weight = float(weights.abs().sum())
    if abs_weight <= 0:
        notes.append(
            "Empirical fit fell back to structural exposures because included weight is zero."
        )
        return None, notes
    weights = weights / abs_weight
    portfolio_returns = returns[eligible].mul(weights, axis=1).sum(axis=1)
    spy = _series_from_frame(returns, "SPY")
    corr = float(portfolio_returns.corr(spy))
    tracking = float((portfolio_returns - spy).std()) * sqrt(252.0)
    corr_component = max(0.0, min(1.0, (corr + 1.0) / 2.0))
    tracking_component = max(0.0, 1.0 - min(1.0, tracking / 0.3))
    score = 0.6 * corr_component + 0.4 * tracking_component
    return score, notes


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
    return (
        f"infl_{sv.inflation_trend}_rates_{sv.rates_trend}_growth_{sv.growth_trend}_"
        f"liq_{sv.liquidity}_vol_{sv.volatility}"
    )


def regime_id_from_state_vector(sv: RegimeStateVector) -> str:
    """Stable regime identifier from the rule-based state vector (used by the analysis runner)."""
    return _regime_label(sv)


def _confidence_from_signals(md: MarketData | None, sv: RegimeStateVector) -> int:
    required = {"^TNX", "SPY", "EEM", "XLF", "GLD", "USO", "^VIX"}
    present = {row.ticker.upper() for row in md.indicators} if md and md.indicators else set()
    coverage = len(required & present) / len(required)
    magnitude = (
        sum(abs(float(row.change_1m_pct)) for row in md.indicators) / max(1, len(md.indicators))
        if md and md.indicators
        else 0.0
    )
    normalized_magnitude = min(1.0, magnitude / 6.0)
    stress_bonus = 0.1 if sv.volatility == "high" else 0.0
    raw = coverage * 0.7 + normalized_magnitude * 0.3 + stress_bonus
    return max(1, min(10, int(round(raw * 10.0))))


def compute_regime_review_base(portfolio: Portfolio, md: MarketData | None) -> RegimeReview:
    sv = infer_state_vector(md)
    label = _regime_label(sv)
    conf = _confidence_from_signals(md, sv)
    structural_fit = _structural_fit_score(portfolio, sv)
    empirical_fit, fit_notes = _empirical_fit_score(portfolio)
    fit_value = (
        structural_fit if empirical_fit is None else 0.7 * structural_fit + 0.3 * empirical_fit
    )
    fit = max(1, min(10, int(round(1.0 + 9.0 * fit_value))))
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
        fit_notes=fit_notes,
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
    if base.fit_notes:
        lines.append("fit_notes: " + "; ".join(base.fit_notes))
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
        "Explain mismatches and tilts in plain language; "
        "do not contradict the state_vector labels.",
    ]
    return "\n".join(lines)
