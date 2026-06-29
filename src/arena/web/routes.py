"""HTTP + SSE routes for the arena GUI backend."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

import port.config as port_config
from arena.csv_import import parse_positions_csv
from arena.data import fetch_market_snapshot
from arena.leaderboard import build_leaderboard
from arena.portfolio import holding_views, initial_state
from arena.scheduler import run_round_for
from arena.state import (
    AGENTS,
    init_run,
    load_initial_snapshot,
    load_latest_state,
    load_ledger,
    load_metadata,
    load_position_timeline,
    load_rounds,
    load_states,
    local_date_stamp,
    read_json,
    run_dir,
    write_json,
)
from arena.watchlist_import import parse_watchlist_file
from arena.web.api_models import (
    ArenaDefaults,
    CompetitionSummary,
    CreateCompetitionRequest,
    ParseCsvRequest,
    ParseCsvResponse,
    ParseWatchlistResponse,
)

log = logging.getLogger(__name__)

ARENA_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"

router = APIRouter()

# One lock per competition so a manual run and the scheduler can't trade it concurrently.
_run_locks: dict[str, asyncio.Lock] = {}


def _lock_for(run_id: str) -> asyncio.Lock:
    return _run_locks.setdefault(run_id, asyncio.Lock())


def _require_run_dir(run_id: str) -> Path:
    # run_id is a single directory name under runs/; reject anything that could
    # escape it (path separators, "..", absolute paths) before touching the disk.
    runs_root = (ARENA_ROOT / "runs").resolve()
    path = run_dir(ARENA_ROOT, run_id).resolve()
    if path.parent != runs_root:
        raise HTTPException(status_code=404, detail=f"Unknown competition {run_id!r}")
    if not (path / "config.json").exists():
        raise HTTPException(status_code=404, detail=f"Unknown competition {run_id!r}")
    return path


def _require_agent(agent: str) -> str:
    if agent not in AGENTS:
        raise HTTPException(status_code=404, detail=f"Unknown agent {agent!r}")
    return agent


@router.get("/api/defaults", response_model=ArenaDefaults)
def get_defaults() -> ArenaDefaults:
    arena = port_config.config.arena
    return ArenaDefaults(
        starting_cash=arena.starting_cash,
        transaction_cost_bps=arena.transaction_cost_bps,
        max_position_weight=arena.max_position_weight,
        max_holdings=arena.max_holdings,
        cash_return_annual_pct=arena.cash_return_annual_pct,
        min_trade_value=arena.min_trade_value,
        min_cash_weight=arena.min_cash_weight,
        benchmark=arena.default_benchmark,
        trade_time=arena.trade_time,
        timezone=arena.timezone,
        corporate_actions=arena.corporate_actions_mode,
        advisor_timeout_seconds=arena.advisor_timeout_seconds,
    )


@router.post("/api/positions/parse-csv", response_model=ParseCsvResponse)
def parse_csv(request: ParseCsvRequest) -> ParseCsvResponse:
    try:
        positions = parse_positions_csv(request.csv_text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ParseCsvResponse(positions=positions)


@router.post("/api/watchlist/parse-file", response_model=ParseWatchlistResponse)
def parse_watchlist(request: ParseCsvRequest) -> ParseWatchlistResponse:
    try:
        watchlist = parse_watchlist_file(request.csv_text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ParseWatchlistResponse(watchlist=watchlist)


@router.post("/api/competitions")
def create_competition(request: CreateCompetitionRequest) -> dict[str, str]:
    try:
        config = request.to_arena_config()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    snapshot = fetch_market_snapshot(
        config.watchlist, benchmark=config.benchmark, include_web_news=False
    )
    missing = [p.ticker for p in config.positions if p.ticker not in snapshot.prices]
    if missing:
        raise HTTPException(
            status_code=422,
            detail="Cannot create competition; missing prices for " + ", ".join(missing),
        )

    as_of = f"{local_date_stamp(config.timezone)}-initial"
    states = {
        agent_id: initial_state(config, snapshot.prices, agent_id=agent_id, as_of=as_of)
        for agent_id in AGENTS
    }
    path = init_run(ARENA_ROOT, config, states)
    write_json(path / "initial-snapshot.json", snapshot.model_dump(mode="json"))
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
            agent_id: _cumulative_return(load_states(entry, agent_id)) for agent_id in AGENTS
        }
        summaries.append(
            CompetitionSummary(
                run_id=entry.name,
                run_name=meta.get("run_name", entry.name),
                status=meta.get("status", "active"),
                rounds=len(rounds),
                last_round_date=meta.get("last_round_date"),
                standings=standings,
            )
        )
    return summaries


@router.delete("/api/competitions/{run_id}")
def delete_competition(run_id: str) -> dict[str, str]:
    path = _require_run_dir(run_id)
    lock = _run_locks.get(run_id)
    if lock is not None and lock.locked():
        raise HTTPException(status_code=409, detail="Cannot delete while a round is running.")
    shutil.rmtree(path)
    _run_locks.pop(run_id, None)
    return {"status": "deleted", "run_id": run_id}


@router.get("/api/competitions/{run_id}")
def get_competition(run_id: str) -> dict[str, Any]:
    path = _require_run_dir(run_id)
    rounds = load_rounds(path)
    agents: dict[str, Any] = {}
    equity_series: dict[str, list[dict[str, Any]]] = {}
    for agent_id in AGENTS:
        latest = load_latest_state(path, agent_id)
        views = holding_views(latest, latest.last_prices)
        agents[agent_id] = {
            "state": latest.model_dump(mode="json"),
            "holdings": [h.model_dump(mode="json") for h in views],
        }
        equity_series[agent_id] = [
            {"date": s.as_of, "equity": s.equity} for s in load_states(path, agent_id)
        ]
    # Anchor the benchmark at competition creation so it lines up with the agent equity
    # series, which starts at the pre-round initial state.
    initial = load_initial_snapshot(path)
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
        "config": read_json(path / "config.json"),
        "metadata": load_metadata(path),
        "rounds": len(rounds),
        "agents": agents,
        "leaderboard": [row.model_dump(mode="json") for row in build_leaderboard(path)],
        "equity_series": equity_series,
        "benchmark_series": benchmark_series,
        "advisor_insight": _advisor_insight(path),
    }


@router.get("/api/competitions/{run_id}/agents/{agent}/ledger")
def get_ledger(run_id: str, agent: str) -> dict[str, Any]:
    path = _require_run_dir(run_id)
    agent = _require_agent(agent)
    return {"trades": [entry.model_dump(mode="json") for entry in load_ledger(path, agent)]}


@router.get("/api/competitions/{run_id}/agents/{agent}/positions")
def get_positions(run_id: str, agent: str) -> dict[str, Any]:
    path = _require_run_dir(run_id)
    agent = _require_agent(agent)
    return {"timeline": load_position_timeline(path, agent)}


@router.get("/api/competitions/{run_id}/run-round")
async def run_round_stream(run_id: str) -> EventSourceResponse:
    _require_run_dir(run_id)
    lock = _lock_for(run_id)

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
                    record = await asyncio.to_thread(
                        run_round_for, ARENA_ROOT, run_id, progress=progress
                    )
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        {"type": "done", "record": record.model_dump(mode="json")},
                    )
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


def _cumulative_return(states: list[Any]) -> float:
    values = [s.equity for s in states]
    if len(values) < 2 or values[0] <= 0:
        return 0.0
    return values[-1] / values[0] - 1.0


def _advisor_insight(path: Path) -> dict[str, Any] | None:
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
