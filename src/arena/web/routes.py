"""HTTP + SSE routes for the arena GUI backend."""

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

import port.config as port_config
from arena.csv_import import parse_positions_csv
from arena.data import fetch_market_snapshot
from arena.leaderboard import build_leaderboard
from arena.models import ArenaConfig
from arena.portfolio import holding_views, initial_state
from arena.scheduler import (
    MAX_ROUND_ATTEMPTS,
    discard_lock,
    is_due,
    load_run_config,
    lock_for,
    run_round_for,
)
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
                agent_status={
                    agent_id: _agent_run_status(
                        agent_id=agent_id,
                        latest=load_latest_state(entry, agent_id),
                        rounds=rounds,
                        meta=meta,
                    )
                    for agent_id in AGENTS
                },
            )
        )
    return summaries


@router.delete("/api/competitions/{run_id}")
async def delete_competition(run_id: str) -> dict[str, str]:
    path = _require_run_dir(run_id)
    lock = lock_for(run_id)
    if lock.locked():
        raise HTTPException(status_code=409, detail="Cannot delete while a round is running.")
    async with lock:
        await asyncio.to_thread(shutil.rmtree, path)
    discard_lock(run_id)
    return {"status": "deleted", "run_id": run_id}


def _next_trade_moment(config: ArenaConfig, now: datetime, *, skip_today: bool) -> datetime:
    """The next market-weekday trade_time in the competition's timezone."""
    local = now.astimezone(ZoneInfo(config.timezone))
    hour, minute = (int(part) for part in config.trade_time.split(":"))
    candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if skip_today or candidate <= local:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def _round_status(
    config: ArenaConfig, meta: dict[str, Any], now: datetime | None = None
) -> dict[str, Any]:
    """What the engine is doing about today's round, phrased for the GUI status strip."""
    now = now or datetime.now(UTC)
    local = now.astimezone(ZoneInfo(config.timezone))
    today = local.strftime("%Y%m%d")
    statuses: dict[str, Any] = meta.get("agent_status") or {}
    status: dict[str, Any] = {
        "phase": "scheduled",
        "round_id": today,
        "market_open_today": local.weekday() < 5,
        "trade_time": config.trade_time,
        "timezone": config.timezone,
        "running_agent": None,
        "completed_at": None,
        "attempts": None,
        "max_attempts": MAX_ROUND_ATTEMPTS,
        "next_attempt_at": None,
        "next_run_at": None,
        "last_error": None,
    }

    if meta.get("active_round_id") == today:
        running = [
            agent
            for agent, entry in statuses.items()
            if (entry or {}).get("status") in ("pending", "running")
        ]
        if running:
            status["phase"] = "running"
            status["running_agent"] = next(
                (a for a in running if statuses[a].get("status") == "running"), running[0]
            )
            return status

    if meta.get("last_round_date") == today:
        status["phase"] = "complete"
        completed_at_values = [
            value
            for entry in statuses.values()
            if isinstance(entry, dict)
            if isinstance(value := entry.get("updated_at"), str)
        ]
        status["completed_at"] = max(completed_at_values, default=None)
        status["next_run_at"] = _next_trade_moment(config, now, skip_today=True).isoformat()
        return status

    attempt = meta.get("round_attempt") or {}
    if attempt.get("round_id") == today:
        status["attempts"] = attempt.get("attempts", 0)
        status["last_error"] = (meta.get("errors") or [None])[-1]
        if status["attempts"] >= MAX_ROUND_ATTEMPTS:
            status["phase"] = "failed"
            status["next_run_at"] = _next_trade_moment(config, now, skip_today=True).isoformat()
        else:
            status["phase"] = "retrying"
            status["next_attempt_at"] = attempt.get("next_attempt_at")
        return status

    if is_due(now, config, meta.get("last_round_date")):
        status["phase"] = "due"
        return status

    status["next_run_at"] = _next_trade_moment(config, now, skip_today=False).isoformat()
    return status


@router.get("/api/competitions/{run_id}")
def get_competition(run_id: str) -> dict[str, Any]:
    path = _require_run_dir(run_id)
    rounds = load_rounds(path)
    meta = load_metadata(path)
    config = load_run_config(path)
    agents: dict[str, Any] = {}
    equity_series: dict[str, list[dict[str, Any]]] = {}
    for agent_id in AGENTS:
        latest = load_latest_state(path, agent_id)
        views = holding_views(latest, latest.last_prices)
        agents[agent_id] = {
            "state": latest.model_dump(mode="json"),
            "holdings": [h.model_dump(mode="json") for h in views],
            "run_status": _agent_run_status(
                agent_id=agent_id,
                latest=latest,
                rounds=rounds,
                meta=meta,
            ),
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
        "config": config.model_dump(mode="json"),
        "metadata": meta,
        "rounds": len(rounds),
        "round_status": _round_status(config, meta),
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


def _agent_run_status(
    *,
    agent_id: str,
    latest: Any,
    rounds: list[Any],
    meta: dict[str, Any],
) -> dict[str, Any]:
    completed_round = rounds[-1].round_id if rounds else None
    latest_state_date = latest.as_of
    stored = dict((meta.get("agent_status") or {}).get(agent_id) or {})
    state_ahead_of_record = (
        not latest_state_date.endswith("-initial")
        and completed_round is not None
        and latest_state_date != completed_round
    )
    if stored:
        status = stored.get("status", "unknown")
        round_id = stored.get("round_id")
    elif completed_round and latest_state_date == completed_round:
        status = "complete"
        round_id = completed_round
    elif latest_state_date.endswith("-initial"):
        status = "not_started"
        round_id = None
    else:
        status = "partial"
        round_id = latest_state_date
        state_ahead_of_record = True
    return {
        "status": status,
        "round_id": round_id,
        "updated_at": stored.get("updated_at"),
        "message": stored.get("message"),
        "latest_state_date": latest_state_date,
        "last_completed_round": completed_round,
        "state_ahead_of_record": state_ahead_of_record,
    }


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
