"""Risk analytics from real return series and historical episodes."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from math import sqrt
from typing import TYPE_CHECKING

import pandas as pd
import yfinance as yf

from port.models import RiskReview, ScenarioLoss, WorstScenario

if TYPE_CHECKING:
    from port.portfolio import Portfolio

log = logging.getLogger(__name__)

_HISTORY_PERIOD = "3y"
_YFINANCE_TIMEOUT_SECONDS = 8
_DOWNLOAD_MAX_ATTEMPTS = 3
_DOWNLOAD_BACKOFF_BASE = 0.75
_DOWNLOAD_BACKOFF_MAX = 4.0


def _download_backoff(attempt: int) -> float:
    return min(_DOWNLOAD_BACKOFF_BASE * (2 ** max(0, attempt - 1)), _DOWNLOAD_BACKOFF_MAX)


_MIN_PRICE_HISTORY_OBS = 90
_MIN_ALIGNED_HISTORY_OBS = 90
_MIN_RETURN_COVERAGE = 0.5
_FACTOR_TICKERS: dict[str, str] = {
    "spy": "SPY",
    "qqq": "QQQ",
    "tlt": "TLT",
    "gld": "GLD",
    "uso": "USO",
    "uup": "UUP",
    "xlf": "XLF",
    "eem": "EEM",
}
_HISTORICAL_SCENARIOS: tuple[tuple[str, str, str], ...] = (
    ("COVID crash", "2020-02-19", "2020-03-23"),
    ("2022 inflation shock", "2022-01-03", "2022-10-14"),
    ("2023 regional bank stress", "2023-03-08", "2023-03-24"),
)


@dataclass
class PreparedHistory:
    returns: pd.DataFrame | None
    portfolio_returns: pd.Series | None
    weights: pd.Series | None
    included_tickers: list[str]
    coverage_ratio: float
    notes: list[str]


def _series_from_frame(frame: pd.DataFrame, column: str) -> pd.Series:
    data = frame.loc[:, column]
    if isinstance(data, pd.DataFrame):
        return data.iloc[:, 0]
    return data


def _series_value(series: pd.Series, key: str) -> float:
    value = series.loc[key]
    if isinstance(value, pd.Series):
        return float(value.iloc[0])
    return float(value)


def _extract_close(raw: pd.DataFrame | pd.Series | None, requested: list[str]) -> pd.DataFrame:
    if raw is None or raw.empty:
        raise RuntimeError("yfinance returned empty history")
    if isinstance(raw, pd.DataFrame) and isinstance(raw.columns, pd.MultiIndex):
        if "Close" not in raw.columns.get_level_values(0):
            raise RuntimeError("close prices missing from yfinance response")
        close_slice = raw.xs("Close", axis=1, level=0, drop_level=True)
        close = (
            pd.DataFrame(close_slice)
            if isinstance(close_slice, pd.DataFrame)
            else close_slice.to_frame()
        )
    elif isinstance(raw, pd.Series):
        close = raw.to_frame(name=requested[0])
    elif len(requested) == 1:
        ticker = requested[0]
        if "Close" in raw.columns:
            close = raw[["Close"]].copy()
            close.columns = pd.Index([ticker])
        else:
            close = pd.DataFrame(raw.copy())
            close.columns = pd.Index([ticker])
    else:
        close = pd.DataFrame(raw.copy())
    close.columns = pd.Index([str(c).upper() for c in close.columns])
    close = close.sort_index().dropna(how="all")
    if close.empty:
        raise RuntimeError("close frame is empty after dropping missing rows")
    return pd.DataFrame(close)


def _download_batch_with_retry(tickers: list[str]) -> pd.DataFrame:
    """Batch yfinance download with retry on transient empty/error responses."""
    last_exc: Exception | None = None
    for attempt in range(1, _DOWNLOAD_MAX_ATTEMPTS + 1):
        try:
            raw = yf.download(
                tickers=tickers,
                period=_HISTORY_PERIOD,
                interval="1d",
                auto_adjust=True,
                progress=False,
                threads=False,
                timeout=_YFINANCE_TIMEOUT_SECONDS,
                group_by="column",
            )
            return _extract_close(raw, tickers)
        except Exception as exc:
            last_exc = exc
            if attempt >= _DOWNLOAD_MAX_ATTEMPTS:
                break
            delay = _download_backoff(attempt)
            log.warning(
                "batch yfinance download attempt %d/%d failed (%s) — retrying in %.1fs",
                attempt,
                _DOWNLOAD_MAX_ATTEMPTS,
                exc,
                delay,
            )
            time.sleep(delay)
    assert last_exc is not None  # exhausted retries
    raise last_exc


def _download_single_with_retry(ticker: str) -> pd.DataFrame | None:
    last_exc: Exception | None = None
    for attempt in range(1, _DOWNLOAD_MAX_ATTEMPTS + 1):
        try:
            single_raw = yf.download(
                tickers=ticker,
                period=_HISTORY_PERIOD,
                interval="1d",
                auto_adjust=True,
                progress=False,
                threads=False,
                timeout=_YFINANCE_TIMEOUT_SECONDS,
                group_by="column",
            )
            return _extract_close(single_raw, [ticker])
        except Exception as exc:
            last_exc = exc
            if attempt >= _DOWNLOAD_MAX_ATTEMPTS:
                break
            time.sleep(_download_backoff(attempt))
    log.warning(
        "failed to download retry history for %s after %d attempts: %s",
        ticker,
        _DOWNLOAD_MAX_ATTEMPTS,
        last_exc,
    )
    return None


def _download_close_frame(tickers: list[str]) -> pd.DataFrame:
    unique = sorted({t.strip().upper() for t in tickers if t and t.strip()})
    if not unique:
        raise ValueError("no tickers supplied")
    close = _download_batch_with_retry(unique)
    missing = [ticker for ticker in unique if ticker not in close.columns]
    if missing:
        log.warning("batch yfinance download missing tickers %s; retrying individually", missing)
        for ticker in missing:
            single_close = _download_single_with_retry(ticker)
            if single_close is not None:
                close[ticker] = _series_from_frame(single_close, ticker)
    return close


def _prepare_history(close: pd.DataFrame, portfolio: Portfolio) -> PreparedHistory:
    tickers = [p.ticker.strip().upper() for p in portfolio.positions]
    if not tickers:
        return PreparedHistory(
            returns=None,
            portfolio_returns=None,
            weights=None,
            included_tickers=[],
            coverage_ratio=0.0,
            notes=["No holdings were provided for return-based risk analysis."],
        )

    weight_map = {p.ticker.strip().upper(): float(p.weight) for p in portfolio.positions}
    total_abs_weight = sum(abs(weight_map[t]) for t in tickers)
    history_counts = {
        ticker: int(_series_from_frame(close, ticker).dropna().shape[0])
        if ticker in close.columns
        else 0
        for ticker in tickers
    }
    eligible = [ticker for ticker in tickers if history_counts[ticker] >= _MIN_PRICE_HISTORY_OBS]
    excluded: list[str] = []
    for ticker in tickers:
        if ticker in eligible:
            continue
        days = history_counts[ticker]
        if days <= 0:
            excluded.append(f"{ticker} (no usable price history)")
        else:
            excluded.append(f"{ticker} ({days} trading days)")

    aligned: pd.DataFrame | None = None
    while eligible:
        candidate = pd.DataFrame(close.loc[:, eligible]).dropna(how="any")
        if len(candidate) >= _MIN_ALIGNED_HISTORY_OBS:
            aligned = candidate
            break
        worst = min(eligible, key=lambda ticker: (history_counts[ticker], abs(weight_map[ticker])))
        eligible.remove(worst)
        excluded.append(
            f"{worst} (insufficient overlap with peers; only {len(candidate)} aligned days)"
        )

    included_abs_weight = sum(abs(weight_map[t]) for t in eligible)
    coverage_ratio = included_abs_weight / total_abs_weight if total_abs_weight > 0 else 0.0
    notes: list[str] = []
    if excluded:
        notes.append(
            "Return-based risk excluded holdings with incomplete history: "
            + ", ".join(excluded[:8])
        )
    if coverage_ratio < 1.0:
        notes.append(f"Return-based risk covers {coverage_ratio:.0%} of invested portfolio weight.")
    if not eligible or aligned is None:
        notes.append("History coverage is too thin for factor and stress estimates.")
        return PreparedHistory(
            returns=None,
            portfolio_returns=None,
            weights=None,
            included_tickers=[],
            coverage_ratio=coverage_ratio,
            notes=notes,
        )

    returns = pd.DataFrame(aligned.pct_change()).dropna(how="any")
    if returns.empty:
        notes.append("Aligned price history produced no daily returns after cleanup.")
        return PreparedHistory(
            returns=None,
            portfolio_returns=None,
            weights=None,
            included_tickers=eligible,
            coverage_ratio=coverage_ratio,
            notes=notes,
        )

    raw_weights = pd.Series({ticker: weight_map[ticker] for ticker in eligible}, dtype=float)
    abs_weight = float(raw_weights.abs().sum())
    if abs_weight <= 0:
        notes.append("Included holdings have zero total weight; using structural-only risk output.")
        return PreparedHistory(
            returns=None,
            portfolio_returns=None,
            weights=None,
            included_tickers=eligible,
            coverage_ratio=coverage_ratio,
            notes=notes,
        )

    if coverage_ratio < _MIN_RETURN_COVERAGE:
        notes.append(
            f"Coverage is below {_MIN_RETURN_COVERAGE:.0%}; "
            "factor and stress outputs represent the covered subset only."
        )

    weights = raw_weights / abs_weight
    portfolio_returns = returns.mul(weights, axis=1).sum(axis=1)
    return PreparedHistory(
        returns=returns,
        portfolio_returns=portfolio_returns,
        weights=weights,
        included_tickers=eligible,
        coverage_ratio=coverage_ratio,
        notes=notes,
    )


def _beta(portfolio_returns: pd.Series, factor_returns: pd.Series) -> float:
    joined = pd.concat([portfolio_returns, factor_returns], axis=1).dropna(how="any")
    if len(joined) < 40:
        return 0.0
    p = joined.iloc[:, 0]
    f = joined.iloc[:, 1]
    f_var = float(f.var())
    if f_var <= 0:
        return 0.0
    return float(p.cov(f) / f_var)


def _factor_outputs(
    close: pd.DataFrame, portfolio_returns: pd.Series
) -> tuple[dict[str, float], dict[str, float]]:
    factor_columns = [ticker for ticker in _FACTOR_TICKERS.values() if ticker in close.columns]
    if not factor_columns:
        return {}, {}
    all_returns = pd.DataFrame(close.loc[:, factor_columns].pct_change()).dropna(how="any")
    if all_returns.empty:
        return {}, {}
    loadings: dict[str, float] = {}
    raw_contrib: dict[str, float] = {}
    for name, ticker in _FACTOR_TICKERS.items():
        if ticker not in all_returns.columns:
            continue
        factor_series = _series_from_frame(all_returns, ticker)
        b = _beta(portfolio_returns, factor_series)
        key = f"beta_{name}"
        loadings[key] = round(b, 4)
        variance = float(factor_series.to_numpy(dtype=float).var(ddof=1))
        raw_contrib[key] = abs(b) * variance
    denom = sum(raw_contrib.values())
    if denom <= 0:
        contrib = dict.fromkeys(loadings, 0.0)
    else:
        contrib = {k: round(v / denom, 4) for k, v in raw_contrib.items()}
    return loadings, contrib


def _marginal_risk(returns: pd.DataFrame, weights: pd.Series) -> dict[str, float]:
    cov = returns.cov()
    ordered = [str(t) for t in weights.index]
    weights = weights.reindex(ordered)
    mw_raw = cov.dot(weights)
    mw = mw_raw if isinstance(mw_raw, pd.Series) else pd.Series(mw_raw, index=ordered, dtype=float)
    port_var = float(weights.to_numpy(dtype=float) @ mw.to_numpy(dtype=float))
    if port_var <= 0:
        raise RuntimeError("portfolio variance is non-positive")
    signed = {
        t: float(_series_value(weights, t) * _series_value(mw, t) / port_var) for t in ordered
    }
    total = sum(abs(v) for v in signed.values())
    if total <= 0:
        return dict.fromkeys(ordered, 0.0)
    return {t: round(abs(v) / total, 4) for t, v in signed.items()}


def _top5_concentration(portfolio: Portfolio) -> float:
    ws = sorted((abs(p.weight) for p in portfolio.positions), reverse=True)
    return sum(ws[:5])


def _cluster_overlap(returns: pd.DataFrame) -> list[str]:
    corr = returns.corr()
    out: list[str] = []
    cols = list(corr.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1 :]:
            c = float(corr.loc[a, b])
            if c >= 0.8:
                out.append(f"{a}/{b} correlation {c:.2f}")
    return out[:8]


def _stress_scenarios(
    returns: pd.DataFrame,
    portfolio_returns: pd.Series,
    portfolio: Portfolio,
    included_tickers: list[str],
    weights: pd.Series,
) -> tuple[list[ScenarioLoss], WorstScenario | None]:
    def _most_affected_positions(slice_pos: pd.DataFrame) -> list[str]:
        if slice_pos.empty:
            return _top_tickers_by_weight(portfolio, 4, limit_to=included_tickers)
        contribution: dict[str, float] = {}
        for ticker in included_tickers:
            t = ticker.upper()
            if t not in slice_pos.columns:
                continue
            position_returns = _series_from_frame(slice_pos, t)
            growth = float((1.0 + position_returns.to_numpy(dtype=float)).prod() - 1.0)
            contribution[t] = abs(_series_value(weights, t) * growth)
        ranked = sorted(contribution, key=lambda t: contribution[t], reverse=True)
        return (
            ranked[:4]
            if ranked
            else _top_tickers_by_weight(portfolio, 4, limit_to=included_tickers)
        )

    def _fallback_windows() -> list[ScenarioLoss]:
        scenarios: list[ScenarioLoss] = []
        window_specs = (
            (10, "Worst 2-week window (available history)"),
            (21, "Worst 1-month window (available history)"),
            (63, "Worst 1-quarter window (available history)"),
        )
        for window, label in window_specs:
            if len(portfolio_returns) < window:
                continue
            rolling_growth = (
                (1.0 + portfolio_returns).rolling(window).apply(lambda x: float(x.prod()))
            )
            rolling_loss = rolling_growth - 1.0
            worst_end = rolling_loss.idxmin()
            if pd.isna(worst_end) or not isinstance(worst_end, pd.Timestamp):
                continue
            worst_loss_pct = float(rolling_loss.loc[worst_end]) * 100.0
            end_loc = portfolio_returns.index.get_loc(worst_end)
            if not isinstance(end_loc, int):
                continue
            start_loc = end_loc - window + 1
            if start_loc < 0:
                continue
            worst_start = portfolio_returns.index[start_loc]
            slice_pos = returns.loc[worst_start:worst_end]
            scenarios.append(
                ScenarioLoss(
                    scenario=label,
                    estimated_portfolio_loss_pct=round(worst_loss_pct, 4),
                    most_affected_positions=_most_affected_positions(slice_pos),
                    scenario_kind="historical",
                )
            )
        return scenarios

    scenarios: list[ScenarioLoss] = []
    for label, start, end in _HISTORICAL_SCENARIOS:
        slice_port = portfolio_returns.loc[start:end]
        if slice_port.empty:
            continue
        pnl = float((1.0 + slice_port).prod() - 1.0) * 100.0
        slice_pos = returns.loc[start:end]
        scenarios.append(
            ScenarioLoss(
                scenario=label,
                estimated_portfolio_loss_pct=round(pnl, 4),
                most_affected_positions=_most_affected_positions(slice_pos),
                scenario_kind="historical",
            )
        )
    if not scenarios:
        log.warning(
            "historical stress windows outside available history; "
            "using worst available rolling windows"
        )
        scenarios = _fallback_windows()
    if not scenarios:
        raise RuntimeError("no stress scenarios could be computed from available data")
    worst = min(scenarios, key=lambda s: s.estimated_portfolio_loss_pct)
    return scenarios, WorstScenario(
        name=worst.scenario,
        estimated_portfolio_loss_pct=worst.estimated_portfolio_loss_pct,
    )


def _top_tickers_by_weight(
    portfolio: Portfolio, n: int, *, limit_to: list[str] | None = None
) -> list[str]:
    allowed = {ticker.upper() for ticker in limit_to} if limit_to else None
    ranked = sorted(
        (p for p in portfolio.positions if allowed is None or p.ticker.upper() in allowed),
        key=lambda p: abs(p.weight),
        reverse=True,
    )
    if not ranked and limit_to:
        ranked = sorted(portfolio.positions, key=lambda p: abs(p.weight), reverse=True)
    return [p.ticker.upper() for p in ranked[:n]]


def _concentration_score(top5_weight: float) -> int:
    """0-100 where higher means more concentrated."""
    return max(0, min(100, int(round(top5_weight * 100))))


def _risk_score(portfolio_returns: pd.Series | None, top5: float) -> int:
    concentration_component = min(1.0, top5)
    if portfolio_returns is None or portfolio_returns.empty:
        raw = 2.0 + 5.0 * concentration_component
        return max(1, min(10, int(round(raw))))
    ann_vol = float(portfolio_returns.to_numpy(dtype=float).std(ddof=1)) * sqrt(252.0)
    vol_component = min(1.0, ann_vol / 0.45)
    raw = 1.0 + 9.0 * (0.65 * vol_component + 0.35 * concentration_component)
    return max(1, min(10, int(round(raw))))


def compute_risk_review_base(portfolio: Portfolio, _md=None) -> RiskReview:
    all_tickers = [p.ticker.upper() for p in portfolio.positions] + list(_FACTOR_TICKERS.values())
    close = _download_close_frame(all_tickers)
    prepared = _prepare_history(close, portfolio)
    top5 = _top5_concentration(portfolio)
    concentration_score = _concentration_score(top5)
    if prepared.returns is None or prepared.portfolio_returns is None or prepared.weights is None:
        detail = "; ".join(prepared.notes) if prepared.notes else "no aligned return history"
        raise RuntimeError(f"Risk analysis unavailable: {detail}")

    loadings, fr_contrib = _factor_outputs(close, prepared.portfolio_returns)
    marginal = _marginal_risk(prepared.returns, prepared.weights)
    scenarios, worst = _stress_scenarios(
        prepared.returns,
        prepared.portfolio_returns,
        portfolio,
        prepared.included_tickers,
        prepared.weights,
    )
    clusters = _cluster_overlap(prepared.returns)
    rs = _risk_score(prepared.portfolio_returns, top5)
    fragilities = list(prepared.notes)

    return RiskReview(
        factor_loadings=loadings,
        factor_risk_contribution=fr_contrib,
        marginal_risk_by_ticker=marginal,
        exposure_links=[],
        concentration_issues=(
            [
                f"Top 5 names ≈ {top5 * 100:.0f}% of portfolio",
                f"Concentration score: {concentration_score}/100",
            ]
            if top5 > 0.55
            else [f"Concentration score: {concentration_score}/100"]
        ),
        concentration_top5_pct=round(top5, 4),
        # Liquidity notes come from the LLM interpretation step, not from the
        # deterministic engine which has no ADV/float data yet.
        liquidity_notes=[],
        scenario_losses=scenarios,
        top_risks=[],
        worst_scenario=worst,
        hidden_concentration=clusters,
        fragilities=fragilities,
        risk_score=rs,
        summary="",
    )


def format_risk_python_block(base: RiskReview) -> str:
    lines = [
        "=== PYTHON RISK ENGINE (authoritative numbers — add interpretation only) ===",
        "",
        "factor_loadings (real-data betas): "
        + ", ".join(f"{k}={v:.2f}" for k, v in sorted(base.factor_loadings.items())),
        "marginal_risk_by_ticker (sums to 1): "
        + ", ".join(f"{k}={v:.2f}" for k, v in sorted(base.marginal_risk_by_ticker.items())[:12]),
        f"concentration_top5_pct: {base.concentration_top5_pct:.2f}",
        (
            next(
                (x for x in base.concentration_issues if x.startswith("Concentration score:")),
                "Concentration score: n/a",
            )
        ),
        f"worst_scenario (engine): {base.worst_scenario.name if base.worst_scenario else 'n/a'} "
        f"({base.worst_scenario.estimated_portfolio_loss_pct:.2f}%)"
        if base.worst_scenario
        else "worst_scenario: n/a",
    ]
    if base.hidden_concentration:
        lines.append("hidden_concentration: " + "; ".join(base.hidden_concentration))
    if base.fragilities:
        lines.append("engine_caveats: " + "; ".join(base.fragilities))
    return "\n".join(lines)
