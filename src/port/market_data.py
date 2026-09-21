"""Shared Yahoo Finance fetch, persistence, and snapshot construction.

Failures propagate — no silent ``None`` returns. Callers decide whether a missing snapshot
should fail the review.
"""

from __future__ import annotations

import logging
import re
import warnings
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import cast

import pandas as pd
import yfinance as yf
from pandas.errors import Pandas4Warning

from port.config import config
from port.llm.retry import with_retry
from port.models.market import MarketIndicator, PositionSnapshot, TickerProfile

# yfinance still calls Timestamp.utcnow in scrapers.history; pandas 3 emits Pandas4Warning.
warnings.filterwarnings(
    "ignore",
    message=r"Timestamp\.utcnow is deprecated.*",
    category=Pandas4Warning,
    module=r"yfinance\.scrapers\.history",
)

log = logging.getLogger(__name__)
SAFE_PATH_RE = re.compile(r"[^A-Za-z0-9_.-]+")
HISTORY_KINDS = ("positions", "indicators", "risk_factors")
MARKET_RETRY_STOP_ON = (TypeError, KeyError, AttributeError)


def profile_text(value: object) -> str:
    text = str(value or "").strip()
    return text if text and text.lower() != "none" else ""


def safe_ticker_path(ticker: str) -> str:
    return SAFE_PATH_RE.sub("_", ticker.strip().upper()).strip("_") or "UNKNOWN"


def market_data_dir(kind: str) -> Path:
    root = Path(config.market.local_data_dir).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    path = root / kind
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_price_history(kind: str, ticker: str, hist) -> None:
    if hist is None or hist.empty:
        raise RuntimeError(f"{ticker} has no price history to save under {kind}")
    path = market_data_dir(kind) / f"{safe_ticker_path(ticker)}.csv"
    hist.to_csv(path)


def load_saved_close(ticker: str) -> pd.Series | None:
    filename = f"{safe_ticker_path(ticker)}.csv"
    found: list[pd.Series] = []
    for kind in HISTORY_KINDS:
        path = market_data_dir(kind) / filename
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
        parsed = pd.DatetimeIndex(pd.to_datetime(close.index, errors="coerce", utc=True))
        if parsed.isna().any():
            raise RuntimeError(f"saved price history for {ticker} has invalid dates: {path}")
        close.index = parsed.tz_convert(None).normalize()  # pyright: ignore[reportAttributeAccessIssue]
        close = close.groupby(level=0).last().sort_index()
        if close.empty:
            raise RuntimeError(f"saved price history for {ticker} is empty: {path}")
        close.name = ticker.upper()
        found.append(close)
    if not found:
        return None
    found.sort(key=lambda series: (len(series), series.index.max()), reverse=True)
    return found[0]


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
        close = load_saved_close(ticker)
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
    match = re.fullmatch(r"(\d+)(d|mo|y)", period.strip().lower())
    if match is None:
        raise ValueError(f"unsupported saved-history period: {period!r}")
    count = int(match.group(1))
    unit = match.group(2)
    end = cast(pd.Timestamp, pd.Timestamp(str(close_frame.index.max())))
    if unit == "d":
        cutoff = end - pd.DateOffset(days=count)
    elif unit == "mo":
        cutoff = end - pd.DateOffset(months=count)
    else:
        cutoff = end - pd.DateOffset(years=count)
    filtered = close_frame.loc[close_frame.index >= cutoff]
    filtered = filtered.dropna(how="all")
    if filtered.empty:
        raise RuntimeError(
            f"{purpose} saved price history has no rows in requested period {period!r}"
        )
    return pd.DataFrame(filtered)


def with_market_retry[T](label: str, ticker: str, attempt: Callable[[], T]) -> T:
    max_attempts = config.market.fetch_max_attempts

    def on_attempt(att: int, exc: Exception, delay: float) -> None:
        log.warning(
            "%s failed for %s attempt=%d/%d err=%s — retrying in %.1fs",
            label,
            ticker,
            att,
            max_attempts,
            exc,
            delay,
        )

    return with_retry(
        attempt,
        attempts=max_attempts,
        base=config.market.fetch_backoff_base_seconds,
        cap=config.market.fetch_backoff_max_seconds,
        on_attempt=on_attempt,
        stop_on=MARKET_RETRY_STOP_ON,
    )


def fetch_close_since(ticker: str, start: date) -> pd.Series:
    """Fresh daily close series for ``ticker`` from ``start`` through today."""

    def attempt() -> pd.Series:
        hist = yf.Ticker(ticker).history(
            start=start.isoformat(),
            interval="1d",
            auto_adjust=True,
        )
        if hist.empty or "Close" not in hist.columns:
            raise RuntimeError(f"{ticker} returned no close history since {start.isoformat()}")
        close = pd.Series(
            pd.to_numeric(hist["Close"], errors="coerce"),
            index=hist.index,
            name=ticker.upper(),
        ).dropna()
        if close.empty:
            raise RuntimeError(f"{ticker} returned no usable closes since {start.isoformat()}")
        parsed = pd.DatetimeIndex(pd.to_datetime(close.index, errors="coerce", utc=True))
        if parsed.isna().any():
            raise RuntimeError(f"{ticker} close history has invalid dates since {start.isoformat()}")
        close.index = parsed.tz_convert(None).normalize()  # pyright: ignore[reportAttributeAccessIssue]
        close = close.groupby(level=0).last().sort_index()
        close.name = ticker.upper()
        return pd.Series(close)

    return with_market_retry("close-since fetch", ticker, attempt)


def fetch_corporate_actions(
    ticker: str,
    start: date,
    *,
    timeout: float | None,
) -> tuple[float, float]:
    """Return cumulative dividends and split ratio from ``start`` through today.

    Uses unadjusted bars so Yahoo's Dividends / Stock Splits columns are cash and ratio
    events, not already baked into Close. Price % moves use auto_adjust=True instead.
    """
    history_kwargs = {
        "start": start.isoformat(),
        "interval": "1d",
        "actions": True,
        "auto_adjust": False,
    }
    if timeout is not None:
        history_kwargs["timeout"] = timeout

    def attempt() -> tuple[float, float]:
        hist = yf.Ticker(ticker).history(**history_kwargs)
        if hist.empty:
            # Yahoo returns an empty frame (not an error) on transient failures such as
            # a cold-session cookie/crumb rejection; treat it as retryable, not as
            # "no corporate actions".
            raise RuntimeError(f"{ticker} returned no history rows since {start.isoformat()}")
        save_price_history("corporate_actions", ticker, hist)
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

    return with_market_retry("corporate actions fetch", ticker, attempt)


def fetch_price_history(kind: str, ticker: str, period: str, interval: str):
    """Yahoo Finance history with retry; persist complete OHLC rows. Raises on failure.

    auto_adjust=True so Close is split/dividend adjusted and return windows are comparable.
    """

    def attempt():
        hist = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
        hist = hist.dropna(subset=["Close", "High", "Low"])
        if hist.empty or len(hist) < 2:
            raise RuntimeError(f"{ticker} returned <2 complete price rows")
        save_price_history(kind, ticker, hist)
        return hist

    return with_market_retry(f"{kind} history fetch", ticker, attempt)


def history_moves(hist, month_window_days: int) -> dict[str, float]:
    close = hist["Close"]
    n = len(close)
    current = float(close.iloc[-1])
    trailing_year = hist.tail(min(252, n))
    week_52_high = float(trailing_year["High"].max())  # type: ignore[arg-type]
    week_52_low = float(trailing_year["Low"].min())  # type: ignore[arg-type]
    return {
        "current": round(current, 2),
        "prev_close": round(float(close.iloc[-2]), 2),
        "change_1d_pct": round(float(close.pct_change(periods=1).iloc[-1]) * 100, 2),
        "change_1w_pct": round(float(close.pct_change(periods=min(5, n - 1)).iloc[-1]) * 100, 2),
        "change_1m_pct": round(
            float(close.pct_change(periods=min(month_window_days - 1, n - 1)).iloc[-1]) * 100, 2
        ),
        "change_3m_pct": round(float(close.pct_change(periods=min(65, n - 1)).iloc[-1]) * 100, 2),
        "change_1y_pct": round(float(close.pct_change(periods=min(251, n - 1)).iloc[-1]) * 100, 2),
        "week_52_high": round(week_52_high, 2),
        "week_52_low": round(week_52_low, 2),
        "pct_from_52w_high": round((current / week_52_high - 1) * 100, 2),
    }


def fetch_history_moves(kind: str, ticker: str, period: str, interval: str) -> dict[str, float]:
    hist = fetch_price_history(kind, ticker, period, interval)
    return history_moves(hist, month_window_days=config.macro.change_window_days)


def fetch_indicator(ticker: str, label: str) -> MarketIndicator:
    moves = fetch_history_moves(
        "indicators",
        ticker,
        config.macro.lookback_period,
        config.macro.interval,
    )
    return MarketIndicator(
        ticker=ticker,
        label=label,
        current=moves["current"],
        prev_close=moves["prev_close"],
        change_1d_pct=moves["change_1d_pct"],
        change_1w_pct=moves["change_1w_pct"],
        change_1m_pct=moves["change_1m_pct"],
        change_3m_pct=moves["change_3m_pct"],
        change_1y_pct=moves["change_1y_pct"],
        week_52_high=moves["week_52_high"],
        week_52_low=moves["week_52_low"],
        pct_from_52w_high=moves["pct_from_52w_high"],
    )


def fetch_risk_factor_history(ticker: str) -> str:
    fetch_price_history(
        "risk_factors",
        ticker,
        config.market.price_history_period,
        "1d",
    )
    return ticker


def fetch_ticker_profile(ticker: str) -> TickerProfile:
    """Fetch basic issuer metadata from Yahoo Finance."""

    def attempt() -> TickerProfile:
        yf_ticker = yf.Ticker(ticker)
        info = yf_ticker.get_info()
        if not isinstance(info, dict):
            raise RuntimeError(f"{ticker} returned no profile metadata")
        name = (
            profile_text(info.get("shortName"))
            or profile_text(info.get("longName"))
            or profile_text(info.get("displayName"))
            or profile_text(info.get("symbol"))
        )
        return TickerProfile(
            ticker=ticker.strip().upper(),
            name=name,
            sector=profile_text(info.get("sector")),
            industry=profile_text(info.get("industry")),
        )

    return with_market_retry("profile fetch", ticker, attempt)


def fetch_position_snapshot(
    ticker: str,
    actions_start: date | None,
) -> PositionSnapshot:
    """Load configured daily history and build a PositionSnapshot. Raises on failure."""
    moves = fetch_history_moves(
        "positions",
        ticker,
        config.market.price_history_period,
        "1d",
    )

    if actions_start is None:
        raise ValueError(
            "fetch_position_snapshot requires explicit actions_start (None disallowed)"
        )
    dividend, split = fetch_corporate_actions(ticker, actions_start, timeout=None)

    return PositionSnapshot(
        ticker=ticker,
        current_price=moves["current"],
        prev_close=moves["prev_close"],
        change_1d_pct=moves["change_1d_pct"],
        change_1w_pct=moves["change_1w_pct"],
        change_1m_pct=moves["change_1m_pct"],
        change_3m_pct=moves["change_3m_pct"],
        change_1y_pct=moves["change_1y_pct"],
        week_52_high=moves["week_52_high"],
        week_52_low=moves["week_52_low"],
        pct_from_52w_high=moves["pct_from_52w_high"],
        dividend=dividend,
        split=split,
    )
