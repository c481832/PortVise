"""Shared Yahoo Finance snapshot fetch for position quotes and the data agent.

Failures propagate — no silent ``None`` returns. Callers decide whether a missing snapshot
should fail the review.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from typing import cast

import pandas as pd
import yfinance as yf

from port._retry import with_retry
from port.config import config
from port.models import PositionSnapshot, TickerProfile
from port.yfinance_compat import suppress_yfinance_pandas4_warnings

log = logging.getLogger(__name__)
_SAFE_PATH_RE = re.compile(r"[^A-Za-z0-9_.-]+")


class _EmptyHistory(RuntimeError):
    pass


class TruncatedHistory(RuntimeError):
    """Yahoo served a short window in place of the full history.

    Distinct from ``_EmptyHistory`` because it is *not* retryable: the truncation is
    server-side and stable across requests (every range parameter returns the same short
    window), so backoff only adds latency before the same failure. Callers pass this as
    ``stop_on`` so it propagates on the first attempt.
    """


def _profile_text(value: object) -> str:
    text = str(value or "").strip()
    return text if text and text.lower() != "none" else ""


def _safe_pct(new: float, old: float) -> float:
    if not old or old != old or new != new:
        raise ValueError(f"degenerate inputs for pct change: new={new!r} old={old!r}")
    return round((new - old) / old * 100, 2)


def _safe_ticker_path(ticker: str) -> str:
    return _SAFE_PATH_RE.sub("_", ticker.strip().upper()).strip("_") or "UNKNOWN"


def _market_data_dir(kind: str) -> Path:
    root = Path(config.market.local_data_dir).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    path = root / kind
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_price_history(kind: str, ticker: str, hist) -> None:
    if hist is None or hist.empty:
        return
    path = _market_data_dir(kind) / f"{_safe_ticker_path(ticker)}.csv"
    # Yahoo intermittently serves a truncated window (a few weeks) instead of the full history
    # for some symbols, notably the ^TNX/^TYX yield indices. That response is not an error, so
    # without this check it would overwrite years of saved closes and only surface much later
    # as "insufficient historical windows" in the regime analog matcher. TruncatedHistory is
    # non-retryable; callers pass it as with_retry's stop_on so it fails fast.
    if path.exists():
        saved_rows = sum(1 for _ in path.open()) - 1
        # Yahoo's row count drifts by a row or two between fetches as boundary rows come and
        # go, so only a material shortfall counts as truncation; observed drift is <= 2 rows
        # against a tolerance of 1%, while a truncated response loses well over 99%.
        tolerance = max(10, int(saved_rows * 0.01))
        if len(hist) < saved_rows - tolerance:
            raise TruncatedHistory(
                f"{ticker} returned {len(hist)} rows, far fewer than the {saved_rows} "
                f"already saved (tolerance {tolerance})"
            )
    hist.to_csv(path)


def _market_history_roots() -> tuple[Path, ...]:
    return (
        _market_data_dir("positions"),
        _market_data_dir("indicators"),
        _market_data_dir("risk_factors"),
    )


def _normalise_saved_history_index(index: pd.Index, *, ticker: str, path: Path) -> pd.DatetimeIndex:
    parsed = pd.DatetimeIndex(pd.to_datetime(index, errors="coerce", utc=True))
    if parsed.isna().any():
        raise RuntimeError(f"saved price history for {ticker} has invalid dates: {path}")
    return parsed.tz_convert(None).normalize()  # pyright: ignore[reportAttributeAccessIssue]


def _load_saved_close(ticker: str) -> pd.Series | None:
    filename = f"{_safe_ticker_path(ticker)}.csv"
    for root in _market_history_roots():
        path = root / filename
        if not path.exists():
            continue
        raw = pd.read_csv(path, index_col=0)
        if "Close" not in raw.columns:
            raise RuntimeError(f"saved price history for {ticker} is missing Close: {path}")
        close = pd.Series(
            pd.to_numeric(raw["Close"], errors="coerce"),
            index=raw.index,
            name="Close",
        ).dropna()
        close.index = _normalise_saved_history_index(close.index, ticker=ticker, path=path)
        close = close.groupby(level=0).last().sort_index()
        if not close.empty:
            close.name = ticker.upper()
            return close
    return None


def _period_cutoff(index: pd.Index, period: str) -> pd.Timestamp:
    match = re.fullmatch(r"(\d+)(d|mo|y)", period.strip().lower())
    if match is None:
        raise ValueError(f"unsupported saved-history period: {period!r}")
    count = int(match.group(1))
    unit = match.group(2)
    end = cast(pd.Timestamp, pd.Timestamp(str(index.max())))
    if unit == "d":
        return end - pd.DateOffset(days=count)
    if unit == "mo":
        return end - pd.DateOffset(months=count)
    return end - pd.DateOffset(years=count)


def load_saved_close_frame(
    tickers: list[str],
    *,
    purpose: str,
    period: str | None = None,
    allow_missing: bool = False,
) -> pd.DataFrame:
    unique = sorted({t.strip().upper() for t in tickers if t and t.strip()})
    if not unique:
        raise ValueError("no tickers supplied")
    series: dict[str, pd.Series] = {}
    missing: list[str] = []
    for ticker in unique:
        close = _load_saved_close(ticker)
        if close is None:
            missing.append(ticker)
            continue
        series[ticker] = close
    if missing and not allow_missing:
        raise RuntimeError(
            f"{purpose} requires first-step market history; missing saved price history for: "
            + ", ".join(missing)
        )
    if not series:
        raise RuntimeError(
            f"{purpose} requires first-step market history; no saved price history found for: "
            + ", ".join(unique)
        )
    close_frame = pd.DataFrame(series).sort_index().dropna(how="all")
    if close_frame.empty:
        raise RuntimeError(f"{purpose} saved price history produced an empty close frame")
    if period is None or period.strip().lower() == "max":
        return close_frame
    filtered = close_frame.loc[close_frame.index >= _period_cutoff(close_frame.index, period)]
    filtered = filtered.dropna(how="all")
    if filtered.empty:
        raise RuntimeError(
            f"{purpose} saved price history has no rows in requested period {period!r}"
        )
    return pd.DataFrame(filtered)


def _save_corporate_actions(ticker: str, hist) -> None:
    if hist is None or hist.empty:
        return
    path = _market_data_dir("corporate_actions") / f"{_safe_ticker_path(ticker)}.csv"
    hist.to_csv(path)


def _corporate_actions_from_history(hist) -> tuple[float, float]:
    if hist.empty:
        return 0.0, 1.0
    dividend = 0.0
    split = 1.0
    for _, row in hist.iterrows():
        cash = float(row.get("Dividends", 0.0) or 0.0)
        if cash:
            dividend += cash * split
        ratio = float(row.get("Stock Splits", 0.0) or 0.0)
        if ratio:
            split *= ratio
    return round(dividend, 6), round(split, 6)


def fetch_corporate_actions(
    ticker: str,
    start: date,
    *,
    timeout: float | None,
) -> tuple[float, float]:
    """Return cumulative dividends and split ratio from ``start`` through today."""
    history_kwargs = {
        "start": start.isoformat(),
        "interval": "1d",
        "actions": True,
        "auto_adjust": False,
    }
    if timeout is not None:
        history_kwargs["timeout"] = timeout

    max_attempts = config.market.fetch_max_attempts
    base_seconds = config.market.fetch_backoff_base_seconds
    cap_seconds = config.market.fetch_backoff_max_seconds

    def attempt() -> tuple[float, float]:
        with suppress_yfinance_pandas4_warnings():
            hist = yf.Ticker(ticker).history(**history_kwargs)
        if hist.empty:
            # Yahoo returns an empty frame (not an error) on transient failures such as
            # a cold-session cookie/crumb rejection; treat it as retryable, not as
            # "no corporate actions".
            raise _EmptyHistory(f"{ticker} returned no history rows since {start.isoformat()}")
        _save_corporate_actions(ticker, hist)
        return _corporate_actions_from_history(hist)

    def on_attempt(att: int, exc: Exception, delay: float) -> None:
        log.warning(
            "corporate actions fetch failed for %s attempt=%d/%d err=%s — retrying in %.1fs",
            ticker,
            att,
            max_attempts,
            exc,
            delay,
        )

    return with_retry(
        attempt,
        attempts=max_attempts,
        base=base_seconds,
        cap=cap_seconds,
        on_attempt=on_attempt,
    )


def _fetch_position_history(ticker: str):
    """Yahoo Finance daily history with retry on transient errors."""
    max_attempts = config.market.fetch_max_attempts
    base_seconds = config.market.fetch_backoff_base_seconds
    cap_seconds = config.market.fetch_backoff_max_seconds

    def attempt():
        with suppress_yfinance_pandas4_warnings():
            hist = yf.Ticker(ticker).history(
                period=config.market.price_history_period,
                interval="1d",
                auto_adjust=True,
            )
        if hist.empty or len(hist) < 2:
            raise _EmptyHistory(f"{ticker} returned <2 rows")
        save_price_history("positions", ticker, hist)
        return hist

    def on_attempt(att: int, exc: Exception, delay: float) -> None:
        level = log.info if isinstance(exc, _EmptyHistory) else log.warning
        level(
            "position history fetch failed for %s attempt=%d/%d err=%s — retrying in %.1fs",
            ticker,
            att,
            max_attempts,
            exc,
            delay,
        )

    return with_retry(
        attempt,
        attempts=max_attempts,
        base=base_seconds,
        cap=cap_seconds,
        on_attempt=on_attempt,
        stop_on=TruncatedHistory,
    )


def fetch_ticker_profile(ticker: str) -> TickerProfile:
    """Fetch basic issuer metadata from Yahoo Finance."""
    max_attempts = config.market.fetch_max_attempts
    base_seconds = config.market.fetch_backoff_base_seconds
    cap_seconds = config.market.fetch_backoff_max_seconds

    def attempt() -> TickerProfile:
        yf_ticker = yf.Ticker(ticker)
        info = yf_ticker.get_info()
        if not isinstance(info, dict):
            raise RuntimeError(f"{ticker} returned no profile metadata")
        name = (
            _profile_text(info.get("shortName"))
            or _profile_text(info.get("longName"))
            or _profile_text(info.get("displayName"))
            or _profile_text(info.get("symbol"))
        )
        return TickerProfile(
            ticker=ticker.strip().upper(),
            name=name,
            sector=_profile_text(info.get("sector")),
            industry=_profile_text(info.get("industry")),
        )

    def on_attempt(att: int, exc: Exception, delay: float) -> None:
        log.warning(
            "profile fetch failed for %s attempt=%d/%d err=%s — retrying in %.1fs",
            ticker,
            att,
            max_attempts,
            exc,
            delay,
        )

    return with_retry(
        attempt,
        attempts=max_attempts,
        base=base_seconds,
        cap=cap_seconds,
        on_attempt=on_attempt,
    )


def fetch_position_snapshot(
    ticker: str,
    actions_start: date | None,
) -> PositionSnapshot:
    """Load configured daily history and build a PositionSnapshot. Raises on failure."""
    hist = _fetch_position_history(ticker)

    close = hist["Close"]
    n = len(close)
    current = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])
    price_1w = float(close.iloc[max(-6, -n)])
    price_1m = float(close.iloc[max(-22, -n)])
    price_3m = float(close.iloc[max(-66, -n)])
    idx_1y = max(0, n - 252)
    price_1y = float(close.iloc[idx_1y])
    trailing_year = hist.tail(min(252, n))
    week_52_high = float(trailing_year["High"].max())  # type: ignore[arg-type]
    week_52_low = float(trailing_year["Low"].min())  # type: ignore[arg-type]

    if actions_start is None:
        raise ValueError(
            "fetch_position_snapshot requires explicit actions_start (None disallowed)"
        )
    dividend, split = fetch_corporate_actions(ticker, actions_start, timeout=None)

    return PositionSnapshot(
        ticker=ticker,
        current_price=round(current, 2),
        prev_close=round(prev_close, 2),
        change_1d_pct=_safe_pct(current, prev_close),
        change_1w_pct=_safe_pct(current, price_1w),
        change_1m_pct=_safe_pct(current, price_1m),
        change_3m_pct=_safe_pct(current, price_3m),
        change_1y_pct=_safe_pct(current, price_1y),
        week_52_high=round(week_52_high, 2),
        week_52_low=round(week_52_low, 2),
        pct_from_52w_high=_safe_pct(current, week_52_high),
        dividend=dividend,
        split=split,
    )
