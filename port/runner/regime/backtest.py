"""Historical analog matching from real market history."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from math import sqrt
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
import yfinance as yf

if TYPE_CHECKING:
    from port.models import MarketData
    from port.portfolio import Portfolio

log = logging.getLogger(__name__)


_MACRO_ORDER = ("rates", "equity", "em", "gold", "oil", "financials")
_MACRO_TICKERS: dict[str, str] = {
    "rates": "^TNX",
    "equity": "SPY",
    "em": "EEM",
    "gold": "GLD",
    "oil": "USO",
    "financials": "XLF",
}
_LOOKBACK_DAYS = 21
_FORWARD_DAYS = 21
_MIN_ANALOG_GAP_DAYS = 21
_DOWNLOAD_MAX_ATTEMPTS = 3
_DOWNLOAD_BACKOFF_BASE = 0.75
_DOWNLOAD_BACKOFF_MAX = 4.0


def _download_backoff(attempt: int) -> float:
    return min(_DOWNLOAD_BACKOFF_BASE * (2 ** max(0, attempt - 1)), _DOWNLOAD_BACKOFF_MAX)


def _indicator_1m(md: MarketData | None, ticker: str) -> float:
    if not md or not md.indicators:
        raise RuntimeError("market_data.indicators is required for regime analog matching")
    wanted = ticker.upper()
    for row in md.indicators:
        if row.ticker.upper() == wanted:
            return float(row.change_1m_pct) / 100.0
    raise RuntimeError(f"missing indicator {ticker} in market_data")


def _current_macro_vector(md: MarketData | None) -> dict[str, float]:
    return {
        "rates": _indicator_1m(md, "^TNX"),
        "equity": _indicator_1m(md, "SPY"),
        "em": _indicator_1m(md, "EEM"),
        "gold": _indicator_1m(md, "GLD"),
        "oil": _indicator_1m(md, "USO"),
        "financials": _indicator_1m(md, "XLF"),
    }


def _distance(lhs: dict[str, float], rhs: dict[str, float]) -> float:
    sq = 0.0
    for key in _MACRO_ORDER:
        diff = lhs.get(key, 0.0) - rhs.get(key, 0.0)
        sq += diff * diff
    return sqrt(sq)


def _as_timestamp(value: object) -> pd.Timestamp | None:
    if isinstance(value, pd.Timestamp):
        return value
    if isinstance(value, (datetime, date, str, int, float)):
        timestamp = pd.Timestamp(value)
        return None if pd.isna(timestamp) else cast(pd.Timestamp, timestamp)
    return None


def _extract_close_frame(raw: pd.DataFrame | pd.Series | None, tickers: list[str]) -> pd.DataFrame:
    if raw is None or raw.empty:
        raise RuntimeError("yfinance returned no data for analog matching")
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
        close = raw.to_frame(name=tickers[0])
    else:
        close = pd.DataFrame(raw.copy())
    close.columns = pd.Index([str(c).upper() for c in close.columns])
    close = close.sort_index().dropna(how="all")
    if close.empty:
        raise RuntimeError("price history empty after cleanup")
    return close


def _download_batch_with_retry(tickers: list[str], period: str) -> pd.DataFrame:
    """Batch yfinance download with retry; returns empty DataFrame if all attempts fail."""
    last_exc: Exception | None = None
    for attempt in range(1, _DOWNLOAD_MAX_ATTEMPTS + 1):
        try:
            raw = yf.download(
                tickers=tickers,
                period=period,
                interval="1d",
                auto_adjust=True,
                progress=False,
                threads=True,
                group_by="column",
            )
            return _extract_close_frame(raw, tickers)
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
    log.warning(
        "batch yfinance download exhausted retries (%s); falling back to per-ticker fetches",
        last_exc,
    )
    return pd.DataFrame()


def _download_single_with_retry(ticker: str, period: str) -> pd.DataFrame | None:
    last_exc: Exception | None = None
    for attempt in range(1, _DOWNLOAD_MAX_ATTEMPTS + 1):
        try:
            single_raw = yf.download(
                tickers=ticker,
                period=period,
                interval="1d",
                auto_adjust=True,
                progress=False,
                threads=False,
                group_by="column",
            )
            return _extract_close_frame(single_raw, [ticker])
        except Exception as exc:
            last_exc = exc
            if attempt >= _DOWNLOAD_MAX_ATTEMPTS:
                break
            time.sleep(_download_backoff(attempt))
    log.warning(
        "yfinance retry failed for %s after %d attempts (%s); dropping from analog matching",
        ticker,
        _DOWNLOAD_MAX_ATTEMPTS,
        last_exc,
    )
    return None


def _download_close(tickers: list[str], period: str) -> pd.DataFrame:
    if not tickers:
        raise RuntimeError("no portfolio holdings available for analog matching")
    unique = sorted({t.upper() for t in tickers})
    close = _download_batch_with_retry(unique, period)

    missing = [t for t in unique if t not in close.columns]
    for ticker in missing:
        single_close = _download_single_with_retry(ticker, period)
        if single_close is not None and ticker in single_close.columns:
            close = (
                single_close[[ticker]]
                if close.empty
                else close.join(single_close[[ticker]], how="outer")
            )

    if close.empty:
        raise RuntimeError("yfinance returned no usable data for analog matching")
    cleaned = close.sort_index().dropna(how="all")
    return cast(pd.DataFrame, cleaned)


def _portfolio_max_drawdown(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    path = (1.0 + returns).cumprod()
    drawdown = path / path.cummax() - 1.0
    return float(drawdown.min())


def find_similar_periods(
    md: MarketData | None, portfolio: Portfolio, top_n: int = 3
) -> list[dict[str, Any]]:
    current = _current_macro_vector(md)
    macro_close = _download_close(list(_MACRO_TICKERS.values()), period="10y")
    macro_window = macro_close.pct_change(periods=_LOOKBACK_DAYS).dropna(how="any")

    pos_tickers = [p.ticker.upper() for p in portfolio.positions]
    pos_close = _download_close(pos_tickers, period="10y")
    missing_positions = sorted({t for t in pos_tickers if t not in pos_close.columns})
    available_tickers = [t for t in pos_tickers if t in pos_close.columns]
    if not available_tickers:
        raise RuntimeError(
            "missing portfolio history for analog matching: " + ", ".join(missing_positions)
        )
    if missing_positions:
        log.warning(
            "analog matching missing history for %s; continuing with %d/%d positions",
            ", ".join(missing_positions),
            len(available_tickers),
            len(pos_tickers),
        )
    pos_close = pos_close[available_tickers].dropna(how="any")
    pos_window = pos_close.pct_change(periods=_LOOKBACK_DAYS).dropna(how="any")
    pos_daily = pos_close.pct_change().dropna(how="any")
    raw_weights = {
        p.ticker.upper(): float(p.weight)
        for p in portfolio.positions
        if p.ticker.upper() in available_tickers
    }
    weight_total = sum(abs(w) for w in raw_weights.values())
    if weight_total <= 0.0:
        raise RuntimeError(
            "remaining holdings have zero total weight after dropping missing history"
        )
    weights = pd.Series({t: w / weight_total for t, w in raw_weights.items()})
    common_dates = macro_window.index.intersection(pos_window.index)
    if len(common_dates) < 120:
        raise RuntimeError("insufficient historical windows for analog matching")

    rows: list[tuple[pd.Timestamp, dict[str, Any]]] = []
    for match_date in common_dates:
        macro_row = macro_window.loc[match_date]
        vector = {
            key: float(macro_row[ticker])
            for key, ticker in _MACRO_TICKERS.items()
            if ticker in macro_row.index
        }
        if len(vector) != len(_MACRO_ORDER):
            continue
        d = _distance(current, vector)
        score = max(0.0, 1.0 - min(1.0, d))
        idx = pos_close.index.get_indexer([match_date])[0]
        if idx < _LOOKBACK_DAYS:
            continue
        start = pos_close.index[idx - _LOOKBACK_DAYS]
        forward_start_idx = pos_daily.index.searchsorted(match_date, side="right")
        forward_end_idx = forward_start_idx + _FORWARD_DAYS
        if forward_end_idx > len(pos_daily):
            continue
        forward_slice = pos_daily.iloc[forward_start_idx:forward_end_idx]
        if forward_slice.empty:
            continue
        portfolio_daily = forward_slice.mul(weights, axis=1).sum(axis=1)
        portfolio_return = float((1.0 + portfolio_daily).prod() - 1.0)
        portfolio_drawdown = _portfolio_max_drawdown(portfolio_daily)
        forward_start = forward_slice.index[0]
        forward_end = forward_slice.index[-1]
        start_ts = _as_timestamp(start)
        end_ts = _as_timestamp(match_date)
        forward_start_ts = _as_timestamp(forward_start)
        forward_end_ts = _as_timestamp(forward_end)
        if start_ts is None or end_ts is None or forward_start_ts is None or forward_end_ts is None:
            continue
        period_label = f"{start_ts.date()} to {end_ts.date()}"
        forward_window = f"{forward_start_ts.date()} to {forward_end_ts.date()}"
        rows.append(
            (
                match_date,
                {
                    "period": period_label,
                    "forward_window": forward_window,
                    "forward_horizon_days": _FORWARD_DAYS,
                    "distance": round(d, 4),
                    "match_score": round(score, 4),
                    "forward_return": round(portfolio_return, 4),
                    "forward_max_drawdown": round(portfolio_drawdown, 4),
                },
            )
        )
    if not rows:
        raise RuntimeError("no valid analog windows found")
    rows.sort(key=lambda item: (item[1]["distance"], -item[1]["match_score"]))
    selected: list[dict[str, Any]] = []
    selected_dates: list[pd.Timestamp] = []
    for match_date, row in rows:
        if any(abs((match_date - prior).days) < _MIN_ANALOG_GAP_DAYS for prior in selected_dates):
            continue
        selected.append(row)
        selected_dates.append(match_date)
        if len(selected) >= max(1, top_n):
            break
    return selected if selected else [rows[0][1]]


def portfolio_performance(analogs: list[dict[str, Any]]) -> dict[str, Any]:
    if not analogs:
        return {
            "available": False,
            "message": "No historical analogs available for this regime.",
            "avg_return": None,
            "win_rate": None,
            "max_drawdown_proxy": None,
        }
    returns = [float(x["forward_return"]) for x in analogs]
    drawdowns = [float(x["forward_max_drawdown"]) for x in analogs if "forward_max_drawdown" in x]
    optimistic = max(returns)
    pessimistic = min(returns)
    # Largest-magnitude outcome (sign preserved) — informational for the log message only.
    extreme = max(returns, key=abs)
    wins = sum(1 for x in returns if x > 0.0)
    horizon = int(analogs[0].get("forward_horizon_days", _FORWARD_DAYS))
    forward_window = str(analogs[0].get("forward_window", "n/a"))
    return {
        "available": True,
        "message": (
            f"Closest analog setup: {analogs[0]['period']} "
            f"(distance={analogs[0]['distance']:.4f}). "
            f"Forward {horizon}-trading-day window: {forward_window}. "
            f"Optimistic={optimistic:+.2%}, pessimistic={pessimistic:+.2%}, "
            f"extreme={extreme:+.2%}."
        ),
        "avg_return": round(sum(returns) / len(returns), 4),
        "win_rate": round(wins / len(returns), 4),
        "max_drawdown_proxy": round(min(drawdowns), 4) if drawdowns else round(pessimistic, 4),
    }
