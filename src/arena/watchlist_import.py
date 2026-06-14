"""Parse a user-supplied investment-pool file into normalized ticker symbols."""

from __future__ import annotations

import csv
import io
import re

HEADER_NAMES = {"ticker", "tickers", "symbol", "symbols"}
TICKER_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.-]*$")


def parse_watchlist_file(text: str) -> list[str]:
    """Parse CSV or one-symbol-per-line text into a deduplicated watchlist."""
    cleaned = text.lstrip("\ufeff").strip()
    if not cleaned:
        raise ValueError("Investment pool file is empty.")

    rows = [
        [cell.strip() for cell in row]
        for row in csv.reader(io.StringIO(cleaned))
        if any(cell.strip() for cell in row)
    ]
    if not rows:
        raise ValueError("Investment pool file contains no ticker symbols.")

    header = [cell.lower() for cell in rows[0]]
    ticker_columns = [index for index, name in enumerate(header) if name in HEADER_NAMES]
    if ticker_columns:
        column = ticker_columns[0]
        raw_symbols = [row[column] for row in rows[1:] if len(row) > column]
    elif all(len(row) == 1 for row in rows):
        raw_symbols = [part for row in rows for part in re.split(r"\s+", row[0]) if part]
    elif len(rows) == 1:
        raw_symbols = rows[0]
    else:
        raise ValueError("CSV must include a 'ticker' or 'symbol' column.")

    symbols: list[str] = []
    seen: set[str] = set()
    for raw in raw_symbols:
        symbol = raw.strip().upper()
        if not symbol:
            continue
        if not TICKER_PATTERN.fullmatch(symbol):
            raise ValueError(f"Invalid ticker symbol: {raw!r}.")
        if symbol not in seen:
            symbols.append(symbol)
            seen.add(symbol)

    if not symbols:
        raise ValueError("Investment pool file contains no ticker symbols.")
    return symbols
