from __future__ import annotations

import csv
import io
from datetime import date

from arena.schemas import ArenaPosition

REQUIRED_COLUMNS = (
    "ticker",
    "name",
    "sector",
    "quantity",
    "entry_date",
    "entry_price",
    "entry_thesis",
)


def parse_positions_csv(text: str) -> list[ArenaPosition]:
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("CSV is empty; expected a header row.")

    header = [name.strip() for name in reader.fieldnames]
    missing = [col for col in REQUIRED_COLUMNS if col not in header]
    if missing:
        raise ValueError(
            "CSV is missing required column(s): "
            + ", ".join(missing)
            + f". Expected columns: {', '.join(REQUIRED_COLUMNS)}."
        )

    positions: list[ArenaPosition] = []
    for line_no, row in enumerate(reader, start=2):
        positions.append(parse_row(row, line_no))
    if not positions:
        raise ValueError("CSV has a header but no position rows.")
    return positions


def parse_row(row: dict[str, str], line_no: int) -> ArenaPosition:
    try:
        return ArenaPosition(
            ticker=require_column(row, "ticker", line_no),
            name=require_column(row, "name", line_no),
            sector=require_column(row, "sector", line_no),
            quantity=parse_float_column(row, "quantity", line_no),
            entry_date=date.fromisoformat(require_column(row, "entry_date", line_no)),
            entry_price=parse_float_column(row, "entry_price", line_no),
            entry_thesis=(row.get("entry_thesis") or "").strip(),
        )
    except ValueError as exc:
        raise ValueError(f"CSV row {line_no}: {exc}") from exc


def require_column(row: dict[str, str], column: str, line_no: int) -> str:
    value = (row.get(column) or "").strip()
    if not value:
        raise ValueError(f"missing value for {column!r}")
    return value


def parse_float_column(row: dict[str, str], column: str, line_no: int) -> float:
    raw = require_column(row, column, line_no)
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{column!r} must be a number, got {raw!r}") from exc
