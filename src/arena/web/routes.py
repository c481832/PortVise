from __future__ import annotations

import asyncio
import json
import logging
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from arena.config import config
from arena.data_import import parse_positions_csv
from arena.leaderboard import build_leaderboard, compute_cumulative_return
from arena.portfolio import holding_views
from arena.run_store import (
    AGENTS,
    ARENA_ROOT,
    load_initial_snapshot,
    load_ledger,
    load_metadata,
    load_rounds,
    load_run_config,
    load_states,
    local_date_stamp,
    read_json,
    run_dir,
)
from arena.scheduler import (
    MAX_ROUND_ATTEMPTS,
    create_competition,
    discard_lock,
    is_due,
    lock_for,
    run_round_for,
    trade_moment,
)
from arena.schemas import ArenaConfig, RoundRecord
from arena.web.api_schemas import (
    ArenaDefaults,
    CompetitionSummary,
    ParseCsvRequest,
    ParseCsvResponse,
)

log = logging.getLogger(__name__)

UI_DIR = Path(__file__).resolve().parent / "ui"

router = APIRouter()


def require_run_dir(run_id: str) -> Path:
    # run_id is a single directory name under runs/; reject anything that could
    # escape it (path separators, "..", absolute paths) before touching the disk.
    runs_root = (ARENA_ROOT / "runs").resolve()
    path = run_dir(ARENA_ROOT, run_id).resolve()
    if path.parent != runs_root:
        raise HTTPException(status_code=404, detail=f"Unknown competition {run_id!r}")
    if not (path / "config.json").exists():
        raise HTTPException(status_code=404, detail=f"Unknown competition {run_id!r}")
    return path


def require_agent(agent: str) -> str:
    if agent not in AGENTS:
        raise HTTPException(status_code=404, detail=f"Unknown agent {agent!r}")
    return agent


@router.get("/api/defaults", response_model=ArenaDefaults)
def get_defaults() -> ArenaDefaults:
    return ArenaDefaults(
        starting_cash=config.starting_cash,
        transaction_cost_bps=config.transaction_cost_bps,
        max_position_weight=config.max_position_weight,
        max_holdings=config.max_holdings,
        cash_return_annual_pct=config.cash_return_annual_pct,
        min_trade_value=config.min_trade_value,
        min_cash_weight=config.min_cash_weight,
        benchmark=config.default_benchmark,
        trade_time=config.trade_time,
        timezone=config.timezone,
        corporate_actions=config.corporate_actions_mode,
        advisor_timeout_seconds=config.advisor_timeout_seconds,
    )


@router.post("/api/positions/parse-csv", response_model=ParseCsvResponse)
def parse_csv(request: ParseCsvRequest) -> ParseCsvResponse:
    try:
        positions = parse_positions_csv(request.csv_text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ParseCsvResponse(positions=positions)


@router.post("/api/competitions")
def post_competition(config: ArenaConfig) -> dict[str, str]:
    try:
        path = create_competition(ARENA_ROOT, config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"run_id": path.name}


@router.get("/api/competitions", response_model=list[CompetitionSummary])
def list_competitions() -> list[CompetitionSummary]:
    runs = ARENA_ROOT / "runs"
    if not runs.exists():
        return []
    summaries: list[CompetitionSummary] = []
    for entry in sorted(runs.iterdir(), reverse=True):
        if not (entry / "metadata.json").exists():
            continue
        meta = load_metadata(entry)
        rounds = load_rounds(entry)
        standings = {
            agent_id: compute_cumulative_return([s.equity for s in load_states(entry, agent_id)])
            for agent_id in AGENTS
        }
        summaries.append(
            CompetitionSummary(
                run_id=entry.name,
                run_name=meta["run_name"],
                status=meta["status"],
                rounds=len(rounds),
                last_round_date=meta["last_round_date"],
                standings=standings,
                agent_status={
                    agent_id: agent_run_status(agent_id, rounds, meta) for agent_id in AGENTS
                },
            )
        )
    return summaries


@router.delete("/api/competitions/{run_id}")
async def delete_competition(run_id: str) -> dict[str, str]:
    path = require_run_dir(run_id)
    lock = lock_for(run_id)
    if lock.locked():
        raise HTTPException(status_code=409, detail="Cannot delete while a round is running.")
    async with lock:
        await asyncio.to_thread(shutil.rmtree, path)
    discard_lock(run_id)
    return {"status": "deleted", "run_id": run_id}


def next_trade_moment(config: ArenaConfig, now: datetime, *, skip_today: bool) -> datetime:
    local = now.astimezone(ZoneInfo(config.timezone))
    candidate = trade_moment(config, local)
    if skip_today or candidate <= local:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def round_status(
    config: ArenaConfig, meta: dict[str, Any], now: datetime | None = None
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    local = now.astimezone(ZoneInfo(config.timezone))
    today = local_date_stamp(config.timezone, now)
    statuses: dict[str, dict[str, Any]] = meta["agent_status"]
    status: dict[str, Any] = {
        "phase": "scheduled",
        "market_open_today": local.weekday() < 5,
        "running_agent": None,
        "completed_at": None,
        "attempts": None,
        "max_attempts": MAX_ROUND_ATTEMPTS,
        "next_attempt_at": None,
        "next_run_at": None,
        "last_error": None,
    }

    if meta["active_round_id"] == today:
        running = [
            agent for agent, entry in statuses.items() if entry["status"] in ("pending", "running")
        ]
        if running:
            status["phase"] = "running"
            status["running_agent"] = next(
                (a for a in running if statuses[a]["status"] == "running"), running[0]
            )
            return status

    if meta["last_round_date"] == today:
        status["phase"] = "complete"
        status["completed_at"] = max(entry["updated_at"] for entry in statuses.values())
        status["next_run_at"] = next_trade_moment(config, now, skip_today=True).isoformat()
        return status

    attempt = meta.get("round_attempt") or {}
    if attempt.get("round_id") == today:
        status["attempts"] = attempt["attempts"]
        status["last_error"] = (meta["errors"] or [None])[-1]
        if status["attempts"] >= MAX_ROUND_ATTEMPTS:
            status["phase"] = "failed"
            status["next_run_at"] = next_trade_moment(config, now, skip_today=True).isoformat()
        else:
            status["phase"] = "retrying"
            status["next_attempt_at"] = attempt["next_attempt_at"]
        return status

    if is_due(now, config, meta["last_round_date"]):
        status["phase"] = "due"
        return status

    status["next_run_at"] = next_trade_moment(config, now, skip_today=False).isoformat()
    return status


@router.get("/api/competitions/{run_id}")
def get_competition(run_id: str) -> dict[str, Any]:
    path = require_run_dir(run_id)
    rounds = load_rounds(path)
    meta = load_metadata(path)
    config = load_run_config(path)
    initial = load_initial_snapshot(path)
    states_by_agent = {agent_id: load_states(path, agent_id) for agent_id in AGENTS}
    agents: dict[str, Any] = {}
    equity_series: dict[str, list[dict[str, Any]]] = {}
    for agent_id, states in states_by_agent.items():
        latest = states[-1]
        views = holding_views(latest, latest.last_prices)
        agents[agent_id] = {
            "state": latest.model_dump(mode="json"),
            "holdings": [h.model_dump(mode="json") for h in views],
            "run_status": agent_run_status(agent_id, rounds, meta),
        }
        equity_series[agent_id] = [{"date": s.as_of, "equity": s.equity} for s in states]
    # Anchor the benchmark at competition creation so it lines up with the agent equity
    # series, which starts at the pre-round initial state.
    benchmark_series: list[dict[str, Any]] = []
    if initial is not None and initial.benchmark_price is not None:
        benchmark_series.append({"date": initial.as_of, "price": initial.benchmark_price})
    benchmark_series += [
        {"date": r.round_id, "price": r.snapshot.benchmark_price}
        for r in rounds
        if r.snapshot.benchmark_price is not None
    ]
    return {
        "run_id": run_id,
        "config": config.model_dump(mode="json"),
        "metadata": meta,
        "rounds": len(rounds),
        "round_status": round_status(config, meta),
        "agents": agents,
        "leaderboard": [
            row.model_dump(mode="json")
            for row in build_leaderboard(rounds, states_by_agent, initial)
        ],
        "equity_series": equity_series,
        "benchmark_series": benchmark_series,
        "advisor_insight": advisor_insight(path),
    }


@router.get("/api/competitions/{run_id}/agents/{agent}/ledger")
def get_ledger(run_id: str, agent: str) -> dict[str, Any]:
    path = require_run_dir(run_id)
    agent = require_agent(agent)
    return {"trades": [entry.model_dump(mode="json") for entry in load_ledger(path, agent)]}


@router.get("/api/competitions/{run_id}/run-round")
async def run_round_stream(run_id: str) -> EventSourceResponse:
    require_run_dir(run_id)
    lock = lock_for(run_id)

    async def event_source():
        if lock.locked():
            yield {"data": json.dumps({"type": "error", "error": "A round is already running."})}
            return
        async with lock:
            queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
            loop = asyncio.get_running_loop()

            def progress(event: dict) -> None:
                loop.call_soon_threadsafe(queue.put_nowait, {"type": "progress", **event})

            async def worker() -> None:
                try:
                    await asyncio.to_thread(
                        run_round_for, ARENA_ROOT, run_id, progress_callback=progress
                    )
                    loop.call_soon_threadsafe(queue.put_nowait, {"type": "done"})
                except Exception as exc:  # surface to the client, then close the stream
                    log.exception("manual round failed for %s", run_id)
                    loop.call_soon_threadsafe(
                        queue.put_nowait, {"type": "error", "error": str(exc)}
                    )
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, None)

            task = asyncio.create_task(worker())
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield {"data": json.dumps(item)}
            await task

    return EventSourceResponse(event_source())


def agent_run_status(
    agent_id: str, rounds: list[RoundRecord], meta: dict[str, Any]
) -> dict[str, Any]:
    return {
        "status": meta["agent_status"][agent_id]["status"],
        "last_completed_round": rounds[-1].round_id if rounds else None,
    }


def advisor_insight(path: Path) -> dict[str, Any] | None:
    advisor_root = path / "advisor"
    if not advisor_root.exists():
        return None
    rounds = sorted(d for d in advisor_root.iterdir() if d.is_dir())
    if not rounds:
        return None
    result_file = rounds[-1] / "advisor-result.json"
    if not result_file.exists():
        return None
    result = read_json(result_file)
    manager = result.get("manager_review") or {}
    risk = result.get("risk_review") or {}
    return {
        "as_of": rounds[-1].name,
        "executive_summary": manager.get("executive_summary"),
        "portfolio_verdict": manager.get("portfolio_verdict"),
        "top_risks": (risk.get("top_risks") or [])[:5],
    }
