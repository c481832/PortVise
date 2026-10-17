from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from arena.schemas import (
    ArenaConfig,
    LedgerEntry,
    MarketSnapshot,
    PortfolioState,
    RoundRecord,
    Trade,
)

T = TypeVar("T", bound=BaseModel)

ARENA_ROOT = Path(__file__).resolve().parent
AGENTS = ("baseline", "advisor_enabled")


def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def local_date_stamp(timezone: str, now: datetime | None = None) -> str:
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


def load_run_config(path: Path) -> ArenaConfig:
    return load_config(path / "config.json")


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


def state_path(path: Path, agent_id: str, as_of: str) -> Path:
    return path / "states" / agent_id / f"{as_of}.json"


def load_state(path: Path, agent_id: str, as_of: str) -> PortfolioState:
    return PortfolioState.model_validate(read_json(state_path(path, agent_id, as_of)))


def save_state(path: Path, agent_id: str, state: PortfolioState) -> Path:
    out = state_path(path, agent_id, state.as_of)
    write_model(out, state)
    return out


def round_path(path: Path, round_id: str) -> Path:
    return path / "rounds" / f"{round_id}.json"


def load_round(path: Path, round_id: str) -> RoundRecord | None:
    file = round_path(path, round_id)
    if not file.exists():
        return None
    return RoundRecord.model_validate(read_json(file))


def save_round(path: Path, record: RoundRecord) -> Path:
    out = round_path(path, record.round_id)
    write_model(out, record)
    return out


def save_initial_snapshot(path: Path, snapshot: MarketSnapshot) -> None:
    write_model(path / "initial-snapshot.json", snapshot)


def load_initial_snapshot(path: Path) -> MarketSnapshot | None:
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
    kept = [entry for entry in load_ledger(path, agent_id) if entry.date != day]
    new_entries = [
        LedgerEntry(
            date=day,
            ticker=trade.ticker,
            side=trade.side,
            quantity=trade.quantity,
            price=trade.price,
            transaction_cost=trade.transaction_cost,
            realized_pnl=trade.realized_pnl,
            cash_after=trade.cash_after,
        )
        for trade in trades
    ]
    out = ledger_path(path, agent_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(entry.model_dump(mode="json"), ensure_ascii=False)
        for entry in kept + new_entries
    ]
    out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
