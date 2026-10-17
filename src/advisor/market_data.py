from __future__ import annotations

import logging
import re
import warnings
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf
from pandas.errors import Pandas4Warning

from advisor.config import config
from advisor.llm.retry import with_retry
from advisor.schemas.market import MarketIndicator, PositionSnapshot, TickerProfile

warnings.filterwarnings(
    "ignore",
    message=r"Timestamp\.utcnow is deprecated.*",
    category=Pandas4Warning,
    module=r"yfinance\.scrapers\.history",
)

log = logging.getLogger(__name__)
SAFE_PATH_RE = re.compile(r"[^A-Za-z0-9_.-]+")
HISTORY_KINDS = ("positions", "indicators", "risk_factors")


def profile_text(value: object) -> str:
    text = str(value or "").strip()
    return text if text and text.lower() != "none" else ""


def history_path(kind: str, ticker: str) -> Path:
    name = SAFE_PATH_RE.sub("_", ticker.strip().upper()).strip("_") or "UNKNOWN"
    return Path(config.market.local_data_dir).expanduser() / kind / f"{name}.csv"


def save_price_history(kind: str, ticker: str, hist) -> None:
    path = history_path(kind, ticker)
    path.parent.mkdir(parents=True, exist_ok=True)
    hist.to_csv(path)


def daily_series(hist: pd.DataFrame, column: str) -> pd.Series:
    if column not in hist.columns:
        raise RuntimeError(f"price history is missing {column!r}")
    series = pd.Series(pd.to_numeric(hist[column], errors="coerce")).dropna()
    index = pd.to_datetime(series.index, utc=True).tz_convert(None)
    series.index = index.normalize()  # pyright: ignore[reportAttributeAccessIssue]
    return series.groupby(level=0).last()


def load_saved_close_frame(
    tickers: list[str],
    *,
    purpose: str,
    allow_missing: bool,
) -> pd.DataFrame:
    unique = sorted({(t or "").strip().upper() for t in tickers if t and t.strip()})
    if not unique:
        raise ValueError("no tickers supplied")
    series: dict[str, pd.Series] = {}
    for ticker in unique:
        paths = [history_path(kind, ticker) for kind in HISTORY_KINDS]
        existing = [p for p in paths if p.exists()]
        if not existing:
            continue
        # A ticker can be saved under several kinds; older runs must not shadow this one.
        path = max(existing, key=lambda p: p.stat().st_mtime)
        hist = pd.read_csv(path, index_col=0)
        if "Adj Close" not in hist.columns:
            raise RuntimeError(f"saved price history for {ticker} is missing 'Adj Close': {path}")
        close = daily_series(hist, "Adj Close")
        if close.empty:
            raise RuntimeError(f"saved price history for {ticker} is empty: {path}")
        series[ticker] = close
    missing = [t for t in unique if t not in series]
    if missing and (not series or not allow_missing):
        raise RuntimeError(
            f"{purpose} requires first-step market history; missing saved price history for: "
            + ", ".join(missing)
        )
    return pd.DataFrame(series).sort_index()


def with_market_retry[T](label: str, ticker: str, attempt: Callable[[], T]) -> T:
    return with_retry(
        attempt,
        label=f"{label} for {ticker}",
        attempts=config.market.fetch_max_attempts,
        delay=config.market.fetch_backoff_base_seconds,
        retry_on=Exception,
    )


def fetch_close_since(ticker: str, start: date) -> pd.Series:
    def attempt() -> pd.Series:
        hist = yf.Ticker(ticker).history(
            start=start.isoformat(),
            interval="1d",
            auto_adjust=False,
        )
        close = daily_series(hist, "Adj Close")
        if close.empty:
            raise RuntimeError(f"{ticker} returned no usable closes since {start.isoformat()}")
        return close.rename(ticker.upper())

    return with_market_retry("close-since fetch", ticker, attempt)


def fetch_corporate_actions(
    ticker: str,
    start: date,
    *,
    timeout: float | None,
) -> tuple[float, float]:
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


def fetch_history_moves(kind: str, ticker: str, period: str, interval: str) -> dict[str, float]:
    def attempt():
        hist = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
        hist = hist.dropna(subset=["Close", "Adj Close", "High", "Low"])
        if len(hist) < 2:
            raise RuntimeError(f"{ticker} returned <2 complete price rows")
        save_price_history(kind, ticker, hist)
        return hist

    hist = with_market_retry(f"{kind} history fetch", ticker, attempt)
    raw = hist["Close"]
    adj = hist["Adj Close"]
    current = float(raw.iloc[-1])
    adj_current = float(adj.iloc[-1])
    week_52_high = float(hist["High"].tail(252).max())  # type: ignore[arg-type]

    def change_pct(days: int) -> float:
        base = float(adj.iloc[-1 - min(days, len(adj) - 1)])
        return round((adj_current / base - 1) * 100, 2)

    return {
        "current": round(current, 2),
        "change_1d_pct": change_pct(1),
        "change_1w_pct": change_pct(5),
        "change_1m_pct": change_pct(config.macro.change_window_days - 1),
        "change_3m_pct": change_pct(65),
        "change_1y_pct": change_pct(251),
        "week_52_high": round(week_52_high, 2),
        "pct_from_52w_high": round((current / week_52_high - 1) * 100, 2),
    }


def fetch_indicator(ticker: str, label: str) -> MarketIndicator:
    moves = fetch_history_moves(
        "indicators",
        ticker,
        config.macro.lookback_period,
        config.macro.interval,
    )
    return MarketIndicator(ticker=ticker, label=label, **moves)


def fetch_risk_factor_history(ticker: str) -> str:
    fetch_history_moves("risk_factors", ticker, config.market.price_history_period, "1d")
    return ticker


def fetch_ticker_profile(ticker: str) -> TickerProfile:
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
        )

    return with_market_retry("profile fetch", ticker, attempt)


def fetch_position_snapshot(ticker: str, actions_start: date) -> PositionSnapshot:
    moves = fetch_history_moves("positions", ticker, config.market.price_history_period, "1d")
    dividend, split = fetch_corporate_actions(ticker, actions_start, timeout=None)
    return PositionSnapshot(
        ticker=ticker,
        current_price=moves.pop("current"),
        dividend=dividend,
        split=split,
        **moves,
    )
