from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from arena.models import (
    ArenaConfig,
    LedgerEntry,
    MarketSnapshot,
    PortfolioState,
    RoundRecord,
    Trade,
)

T = TypeVar("T", bound=BaseModel)

AGENTS = ("baseline", "advisor_enabled")


def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def date_stamp(day: date | None = None) -> str:
    """The canonical one-round-per-day id, e.g. 20260607."""
    return (day or datetime.now(UTC).date()).strftime("%Y%m%d")


def local_date_stamp(timezone: str, now: datetime | None = None) -> str:
    """Today's round id in the competition's trading timezone (one round per local day)."""
    from zoneinfo import ZoneInfo

    moment = now or datetime.now(UTC)
    return moment.astimezone(ZoneInfo(timezone)).strftime("%Y%m%d")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_model(path: Path, model: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_config(path: Path) -> ArenaConfig:
    return ArenaConfig.model_validate(read_json(path))


def run_dir(root: Path, run_id: str) -> Path:
    return root / "runs" / run_id


def init_run(root: Path, config: ArenaConfig, initial_states: dict[str, PortfolioState]) -> Path:
    rid = f"{utc_stamp()}-{config.run_name}"
    path = run_dir(root, rid)
    write_model(path / "config.json", config)
    for agent_id, state in initial_states.items():
        save_state(path, agent_id, state)
    created_at = utc_stamp()
    write_json(
        path / "metadata.json",
        {
            "run_id": rid,
            "run_name": config.run_name,
            "created_at": created_at,
            "status": "active",
            "last_round_date": None,
            "active_round_id": None,
            "agent_status": {
                agent_id: {
                    "status": "not_started",
                    "round_id": None,
                    "updated_at": created_at,
                }
                for agent_id in AGENTS
            },
            "errors": [],
        },
    )
    return path


def load_metadata(path: Path) -> dict[str, Any]:
    return read_json(path / "metadata.json")


def update_metadata(path: Path, **changes: Any) -> dict[str, Any]:
    meta = load_metadata(path)
    meta.update(changes)
    write_json(path / "metadata.json", meta)
    return meta


def latest_state_path(path: Path, agent_id: str) -> Path:
    states = sorted((path / "states" / agent_id).glob("*.json"))
    if not states:
        raise FileNotFoundError(f"No state files found for {agent_id} in {path}")
    return states[-1]


def load_latest_state(path: Path, agent_id: str) -> PortfolioState:
    return PortfolioState.model_validate(read_json(latest_state_path(path, agent_id)))


def save_state(path: Path, agent_id: str, state: PortfolioState) -> Path:
    out = path / "states" / agent_id / f"{state.as_of}.json"
    write_model(out, state)
    return out


def save_round(path: Path, record: RoundRecord) -> Path:
    out = path / "rounds" / f"{record.round_id}.json"
    write_model(out, record)
    return out


def load_initial_snapshot(path: Path) -> MarketSnapshot | None:
    """The market snapshot captured at competition creation, before any round."""
    file = path / "initial-snapshot.json"
    if not file.exists():
        return None
    return MarketSnapshot.model_validate(read_json(file))


def load_rounds(path: Path) -> list[RoundRecord]:
    return [
        RoundRecord.model_validate(read_json(item))
        for item in sorted((path / "rounds").glob("*.json"))
    ]


def load_states(path: Path, agent_id: str) -> list[PortfolioState]:
    return [
        PortfolioState.model_validate(read_json(item))
        for item in sorted((path / "states" / agent_id).glob("*.json"))
    ]


def ledger_path(path: Path, agent_id: str) -> Path:
    return path / "ledgers" / agent_id / "trades.jsonl"


def load_ledger(path: Path, agent_id: str) -> list[LedgerEntry]:
    out = ledger_path(path, agent_id)
    if not out.exists():
        return []
    entries: list[LedgerEntry] = []
    for line in out.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            entries.append(LedgerEntry.model_validate_json(stripped))
    return entries


def append_ledger(path: Path, agent_id: str, day: str, trades: list[Trade]) -> None:
    """Record a day's trades in the per-agent ledger.

    Append-only across days, but idempotent within a day: any prior entries for ``day`` are
    replaced so re-running the same date does not duplicate rows.
    """
    kept = [entry for entry in load_ledger(path, agent_id) if entry.date != day]
    new_entries = [LedgerEntry(date=day, **trade.model_dump()) for trade in trades]
    out = ledger_path(path, agent_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(entry.model_dump(mode="json"), ensure_ascii=False)
        for entry in kept + new_entries
    ]
    out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def load_position_timeline(path: Path, agent_id: str) -> list[dict[str, Any]]:
    """Per-day, per-ticker value / unrealized P&L / weight, derived from state snapshots."""
    timeline: list[dict[str, Any]] = []
    for state in load_states(path, agent_id):
        positions: dict[str, dict[str, float]] = {}
        for ticker, holding in state.holdings.items():
            price = state.last_prices.get(ticker, holding.average_cost)
            mkt_value = holding.quantity * price
            positions[ticker] = {
                "quantity": holding.quantity,
                "price": price,
                "mkt_value": mkt_value,
                "unrealized_pnl": (price - holding.average_cost) * holding.quantity,
                "weight": mkt_value / state.equity if state.equity > 0 else 0.0,
            }
        timeline.append(
            {
                "date": state.as_of,
                "equity": state.equity,
                "cash": state.cash,
                "positions": positions,
            }
        )
    return timeline
