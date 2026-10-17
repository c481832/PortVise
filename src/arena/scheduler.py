from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from arena.agents import run_advisor_enabled_agent, run_baseline_agent
from arena.market_data import fetch_market_snapshot
from arena.portfolio import apply_decision, initial_state
from arena.run_store import (
    AGENTS,
    append_ledger,
    init_run,
    load_metadata,
    load_round,
    load_run_config,
    load_state,
    local_date_stamp,
    run_dir,
    save_initial_snapshot,
    save_round,
    save_state,
    update_metadata,
    utc_stamp,
)
from arena.schemas import AgentRoundResult, ArenaConfig, PortfolioState, RoundRecord

log = logging.getLogger(__name__)

ProgressCallback = Callable[[dict], None]

SCHEDULER_POLL_SECONDS = 30.0

# After a failed round: retry after 5, 10, then 20 minutes, then give up until the next day.
MAX_ROUND_ATTEMPTS = 4
RETRY_BASE_DELAY_SECONDS = 300.0

run_locks: dict[str, asyncio.Lock] = {}


def lock_for(run_id: str) -> asyncio.Lock:
    return run_locks.setdefault(run_id, asyncio.Lock())


def discard_lock(run_id: str) -> None:
    run_locks.pop(run_id, None)


def emit_progress(progress_callback: ProgressCallback | None, **event: object) -> None:
    if progress_callback is not None:
        progress_callback(dict(event))


def create_competition(root: Path, config: ArenaConfig) -> Path:
    snapshot = fetch_market_snapshot(
        config.watchlist, benchmark=config.benchmark, include_web_news=False
    )
    missing = [p.ticker for p in config.positions if p.ticker not in snapshot.prices]
    if missing:
        raise ValueError("Cannot create competition; missing prices for " + ", ".join(missing))
    as_of = f"{local_date_stamp(config.timezone)}-initial"
    states = {
        agent_id: initial_state(config, snapshot.prices, agent_id=agent_id, as_of=as_of)
        for agent_id in AGENTS
    }
    path = init_run(root, config, states)
    save_initial_snapshot(path, snapshot)
    return path


def load_start_state(path: Path, agent_id: str) -> PortfolioState:
    round_files = sorted((path / "rounds").glob("*.json"))
    if round_files:
        return load_state(path, agent_id, round_files[-1].stem)
    initial_states = sorted((path / "states" / agent_id).glob("*-initial.json"))
    if not initial_states:
        raise FileNotFoundError(f"No initial state for {agent_id} in {path}")
    return load_state(path, agent_id, initial_states[-1].stem)


def set_agent_status(
    path: Path,
    *,
    round_id: str,
    agent_id: str,
    status: str,
    message: str | None = None,
) -> None:
    meta = load_metadata(path)
    statuses = dict(meta.get("agent_status") or {})
    entry = {
        "status": status,
        "round_id": round_id,
        "updated_at": utc_stamp(),
    }
    if message:
        entry["message"] = message
    statuses[agent_id] = entry
    update_metadata(path, active_round_id=round_id, agent_status=statuses)


def set_round_complete(path: Path, round_id: str) -> None:
    now = utc_stamp()
    update_metadata(
        path,
        last_round_date=round_id,
        active_round_id=None,
        agent_status={
            agent_id: {"status": "complete", "round_id": round_id, "updated_at": now}
            for agent_id in AGENTS
        },
    )


def run_round_for(
    root: Path, run_id: str, *, progress_callback: ProgressCallback | None = None
) -> RoundRecord:
    path = run_dir(root, run_id)
    config = load_run_config(path)
    round_id = current_trading_round_id(config)
    started_at = datetime.now(UTC)
    existing = load_round(path, round_id)
    if existing is not None:
        if load_metadata(path).get("last_round_date") != round_id:
            set_round_complete(path, round_id)
        emit_progress(
            progress_callback, stage="done", message="Round already complete", round_id=round_id
        )
        return existing

    emit_progress(progress_callback, stage="snapshot", message="Fetching market snapshot")
    snapshot = fetch_market_snapshot(
        config.watchlist, benchmark=config.benchmark, include_web_news=True
    )

    results: dict[str, AgentRoundResult] = {}
    current_agent: str | None = None

    try:
        set_agent_status(path, round_id=round_id, agent_id="baseline", status="pending")
        set_agent_status(path, round_id=round_id, agent_id="advisor_enabled", status="pending")

        emit_progress(progress_callback, stage="baseline", message="Baseline agent trading")
        current_agent = "baseline"
        set_agent_status(path, round_id=round_id, agent_id=current_agent, status="running")
        baseline_state = load_start_state(path, "baseline")
        baseline_decision = run_baseline_agent(config, baseline_state, snapshot)
        next_baseline, baseline_trades = apply_decision(
            baseline_state, baseline_decision, snapshot.prices, config, as_of=round_id
        )
        results["baseline"] = AgentRoundResult(
            agent_id="baseline",
            decision=baseline_decision,
            trades=baseline_trades,
            state=next_baseline,
        )
        set_agent_status(path, round_id=round_id, agent_id=current_agent, status="complete")

        emit_progress(
            progress_callback, stage="advisor", message="Advisor agent running PortVise review"
        )
        current_agent = "advisor_enabled"
        set_agent_status(path, round_id=round_id, agent_id=current_agent, status="running")
        advisor_state = load_start_state(path, "advisor_enabled")
        advisor_decision = run_advisor_enabled_agent(
            config,
            advisor_state,
            snapshot,
            work_dir=path / "advisor" / round_id,
            review_date=datetime.strptime(round_id, "%Y%m%d").date(),
        )
        next_advisor, advisor_trades = apply_decision(
            advisor_state, advisor_decision, snapshot.prices, config, as_of=round_id
        )
        results["advisor_enabled"] = AgentRoundResult(
            agent_id="advisor_enabled",
            decision=advisor_decision,
            trades=advisor_trades,
            state=next_advisor,
        )
        set_agent_status(path, round_id=round_id, agent_id=current_agent, status="complete")
    except Exception as exc:
        if current_agent is not None:
            set_agent_status(
                path,
                round_id=round_id,
                agent_id=current_agent,
                status="failed",
                message=str(exc),
            )
        raise

    save_state(path, "baseline", results["baseline"].state)
    save_state(path, "advisor_enabled", results["advisor_enabled"].state)
    append_ledger(path, "baseline", round_id, results["baseline"].trades)
    append_ledger(path, "advisor_enabled", round_id, results["advisor_enabled"].trades)

    record = RoundRecord(
        round_id=round_id, started_at=started_at, snapshot=snapshot, results=results
    )
    save_round(path, record)
    set_round_complete(path, round_id)
    emit_progress(progress_callback, stage="done", message="Round complete", round_id=round_id)
    return record


def current_trading_round_id(config: ArenaConfig, now_utc: datetime | None = None) -> str:
    local = (now_utc or datetime.now(UTC)).astimezone(ZoneInfo(config.timezone))
    candidate = (
        local
        if local.weekday() < 5 and local >= trade_moment(config, local)
        else local - timedelta(days=1)
    )
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate.strftime("%Y%m%d")


def is_due(now_utc: datetime, config: ArenaConfig, last_round_date: str | None) -> bool:
    local = now_utc.astimezone(ZoneInfo(config.timezone))
    if local.weekday() >= 5:
        return False
    today = local.strftime("%Y%m%d")
    if last_round_date == today:
        return False
    return local >= trade_moment(config, local)


def trade_moment(config: ArenaConfig, local: datetime) -> datetime:
    hour, minute = (int(part) for part in config.trade_time.split(":"))
    return local.replace(hour=hour, minute=minute, second=0, microsecond=0)


def active_run_ids(root: Path) -> list[str]:
    runs = root / "runs"
    if not runs.exists():
        return []
    out: list[str] = []
    for entry in sorted(runs.iterdir()):
        if not (entry / "metadata.json").exists():
            continue
        if load_metadata(entry).get("status") == "active":
            out.append(entry.name)
    return out


async def run_scheduler(root: Path, *, poll_seconds: float = SCHEDULER_POLL_SECONDS) -> None:
    log.info("arena scheduler started (poll=%.0fs, root=%s)", poll_seconds, root)
    while True:
        try:
            await scheduler_tick(root)
        except Exception:
            log.exception("arena scheduler tick failed")
        await asyncio.sleep(poll_seconds)


async def scheduler_tick(root: Path) -> None:
    now = datetime.now(UTC)
    for run_id in active_run_ids(root):
        path = run_dir(root, run_id)
        config = load_run_config(path)
        meta = load_metadata(path)
        if not is_due(now, config, meta.get("last_round_date")):
            continue
        round_id = current_trading_round_id(config, now)
        if not retry_allowed(meta, round_id=round_id, now=now):
            continue
        lock = lock_for(run_id)
        if lock.locked():
            continue
        log.info("scheduler running round for %s", run_id)
        async with lock:
            try:
                await asyncio.to_thread(run_round_for, root, run_id)
            except Exception as exc:
                log.exception("scheduled round failed for %s", run_id)
                record_failed_attempt(path, round_id=round_id, error=str(exc))
            else:
                if meta.get("round_attempt"):
                    update_metadata(path, round_attempt=None)


def retry_allowed(meta: dict, *, round_id: str, now: datetime) -> bool:
    attempt = meta.get("round_attempt") or {}
    if attempt.get("round_id") != round_id:
        return True
    if attempt.get("attempts", 0) >= MAX_ROUND_ATTEMPTS:
        return False
    next_at = attempt.get("next_attempt_at")
    return next_at is None or now >= datetime.fromisoformat(next_at)


def record_failed_attempt(path: Path, *, round_id: str, error: str) -> None:
    meta = load_metadata(path)
    attempt = meta.get("round_attempt") or {}
    previous = attempt.get("attempts", 0) if attempt.get("round_id") == round_id else 0
    attempts = previous + 1
    now = datetime.now(UTC)
    delay = RETRY_BASE_DELAY_SECONDS * 2 ** (attempts - 1)
    message = f"{now.isoformat()}: attempt {attempts}/{MAX_ROUND_ATTEMPTS} failed: {error}"
    if attempts >= MAX_ROUND_ATTEMPTS:
        message += " (giving up until the next market day)"
    errors = [*(meta.get("errors") or []), message]
    update_metadata(
        path,
        round_attempt={
            "round_id": round_id,
            "attempts": attempts,
            "next_attempt_at": (now + timedelta(seconds=delay)).isoformat(),
        },
        errors=errors[-20:],
    )
