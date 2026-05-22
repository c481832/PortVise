from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from arena.models import ArenaConfig, PortfolioState, RoundRecord

T = TypeVar("T", bound=BaseModel)

AGENTS = ("baseline", "advisor_enabled")


def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


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
    write_json(path / "metadata.json", {"run_id": rid, "created_at": utc_stamp()})
    return path


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
