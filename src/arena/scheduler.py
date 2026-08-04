"""Run one round per market day, and the engine loop that fires it on schedule.

``run_round_for`` is the single producer of a round: it fetches a snapshot, runs both agents,
applies their decisions, and writes the day's states, ledger entries, and RoundRecord. It is
called by the GUI "Run round now" button, the headless CLI, and the scheduler loop.

``run_scheduler`` is a long-running async loop: it wakes periodically and, for every active
competition whose configured ``trade_time`` has passed on a market weekday and that has not yet
recorded today's round, runs one round. A failed round is logged and recorded on the competition
but does not stop the loop; it is retried with exponential backoff and abandoned for the day
after ``MAX_ROUND_ATTEMPTS`` failures.

``lock_for`` hands out one asyncio lock per competition, shared with the web routes, so a manual
GUI run, a delete, and a scheduled round can never touch the same competition concurrently.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from arena.agents import run_advisor_enabled_agent, run_baseline_agent
from arena.data import fetch_market_snapshot
from arena.models import AgentRoundResult, ArenaConfig, PortfolioState, RoundRecord
from arena.portfolio import apply_decision
from arena.state import (
    append_ledger,
    load_latest_state,
    load_metadata,
    load_rounds,
    read_json,
    run_dir,
    save_round,
    save_state,
    update_metadata,
)

log = logging.getLogger(__name__)

ProgressFn = Callable[[dict], None]

SCHEDULER_POLL_SECONDS = 30.0

# After a failed round: retry after 5, 10, then 20 minutes, then give up until the next day.
MAX_ROUND_ATTEMPTS = 4
RETRY_BASE_DELAY_SECONDS = 300.0

_run_locks: dict[str, asyncio.Lock] = {}


def lock_for(run_id: str) -> asyncio.Lock:
    """The per-competition lock shared by the scheduler, manual runs, and deletes."""
    return _run_locks.setdefault(run_id, asyncio.Lock())


def discard_lock(run_id: str) -> None:
    _run_locks.pop(run_id, None)


def _emit(progress: ProgressFn | None, **event: object) -> None:
    if progress is not None:
        progress(dict(event))


def load_run_config(path: Path) -> ArenaConfig:
    return ArenaConfig.model_validate(read_json(path / "config.json"))


def _round_record_path(path: Path, round_id: str) -> Path:
    return path / "rounds" / f"{round_id}.json"


def _load_existing_round(path: Path, round_id: str) -> RoundRecord | None:
    record_path = _round_record_path(path, round_id)
    if not record_path.exists():
        return None
    return RoundRecord.model_validate(read_json(record_path))


def _load_start_state(path: Path, agent_id: str) -> PortfolioState:
    """Load the latest completed state, ignoring partial same-day state files.

    A previous implementation loaded the newest state file for each agent. If one
    agent finished and the other failed, retrying the same date could advance the
    first agent twice. Completed rounds are the source of truth here.
    """
    rounds = load_rounds(path)
    if rounds:
        return _load_state_at(path, agent_id, rounds[-1].round_id)
    initial_states = sorted((path / "states" / agent_id).glob("*-initial.json"))
    if not initial_states:
        return load_latest_state(path, agent_id)
    return _load_state_file(initial_states[-1])


def _load_state_at(path: Path, agent_id: str, as_of: str) -> PortfolioState:
    return _load_state_file(path / "states" / agent_id / f"{as_of}.json")


def _load_state_file(path: Path) -> PortfolioState:
    return PortfolioState.model_validate(read_json(path))


def _set_agent_status(
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
        "updated_at": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
    }
    if message:
        entry["message"] = message
    statuses[agent_id] = entry
    update_metadata(path, active_round_id=round_id, agent_status=statuses)


def _set_round_complete(path: Path, round_id: str) -> None:
    now = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    update_metadata(
        path,
        last_round_date=round_id,
        active_round_id=None,
        agent_status={
            "baseline": {"status": "complete", "round_id": round_id, "updated_at": now},
            "advisor_enabled": {"status": "complete", "round_id": round_id, "updated_at": now},
        },
    )


def run_round_for(root: Path, run_id: str, *, progress: ProgressFn | None = None) -> RoundRecord:
    """Run one competition round for both agents and persist all of it. Idempotent per local day."""
    path = run_dir(root, run_id)
    config = load_run_config(path)
    round_id = current_trading_round_id(config)
    started_at = datetime.now(UTC)
    existing = _load_existing_round(path, round_id)
    if existing is not None:
        if load_metadata(path).get("last_round_date") != round_id:
            _set_round_complete(path, round_id)
        _emit(progress, stage="done", message="Round already complete", round_id=round_id)
        return existing

    _emit(progress, stage="snapshot", message="Fetching market snapshot")
    snapshot = fetch_market_snapshot(
        config.watchlist, benchmark=config.benchmark, include_web_news=True
    )

    results: dict[str, AgentRoundResult] = {}
    current_agent: str | None = None

    try:
        _set_agent_status(path, round_id=round_id, agent_id="baseline", status="pending")
        _set_agent_status(path, round_id=round_id, agent_id="advisor_enabled", status="pending")

        _emit(progress, stage="baseline", message="Baseline agent trading")
        current_agent = "baseline"
        _set_agent_status(path, round_id=round_id, agent_id=current_agent, status="running")
        baseline_state = _load_start_state(path, "baseline")
        baseline_decision = run_baseline_agent(config, baseline_state, snapshot)
        next_baseline, baseline_trades, baseline_corrections = apply_decision(
            baseline_state, baseline_decision, snapshot.prices, config, as_of=round_id
        )
        results["baseline"] = AgentRoundResult(
            agent_id="baseline",
            decision=baseline_decision,
            trades=baseline_trades,
            corrections=baseline_corrections,
            state=next_baseline,
        )
        _set_agent_status(path, round_id=round_id, agent_id=current_agent, status="complete")

        _emit(progress, stage="advisor", message="Advisor agent running PortVise review")
        current_agent = "advisor_enabled"
        _set_agent_status(path, round_id=round_id, agent_id=current_agent, status="running")
        advisor_state = _load_start_state(path, "advisor_enabled")
        advisor_decision, advisor_result_path = run_advisor_enabled_agent(
            config,
            advisor_state,
            snapshot,
            work_dir=path / "advisor" / round_id,
            review_date=datetime.strptime(round_id, "%Y%m%d").date(),
        )
        next_advisor, advisor_trades, advisor_corrections = apply_decision(
            advisor_state, advisor_decision, snapshot.prices, config, as_of=round_id
        )
        results["advisor_enabled"] = AgentRoundResult(
            agent_id="advisor_enabled",
            decision=advisor_decision,
            trades=advisor_trades,
            corrections=advisor_corrections,
            state=next_advisor,
            advisor_result_path=str(advisor_result_path),
        )
        _set_agent_status(path, round_id=round_id, agent_id=current_agent, status="complete")
    except Exception as exc:
        if current_agent is not None:
            _set_agent_status(
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
    _set_round_complete(path, round_id)
    _emit(progress, stage="done", message="Round complete", round_id=round_id)
    return record


def current_trading_round_id(config: ArenaConfig, now_utc: datetime | None = None) -> str:
    """The round id for the trading day whose session has most recently closed.

    Before a weekday's trade_time (or over a weekend), no new close is available yet,
    so this rolls back to the previous market weekday instead of stamping a round for a
    session that hasn't traded — otherwise a pre-market or weekend "Run round now" would
    label a round with today's date while actually using yesterday's closing data.
    """
    local = (now_utc or datetime.now(UTC)).astimezone(ZoneInfo(config.timezone))
    hour, minute = (int(part) for part in config.trade_time.split(":"))
    trade_moment = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    candidate = (
        local if local.weekday() < 5 and local >= trade_moment else local - timedelta(days=1)
    )
    while candidate.weekday() >= 5:  # Saturday/Sunday
        candidate -= timedelta(days=1)
    return candidate.strftime("%Y%m%d")


def is_due(now_utc: datetime, config: ArenaConfig, last_round_date: str | None) -> bool:
    """True when it's a market weekday past trade_time and today's round hasn't run yet."""
    local = now_utc.astimezone(ZoneInfo(config.timezone))
    if local.weekday() >= 5:  # Saturday/Sunday
        return False
    today = local.strftime("%Y%m%d")
    if last_round_date == today:
        return False
    hour, minute = (int(part) for part in config.trade_time.split(":"))
    trade_moment = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return local >= trade_moment


def _active_run_ids(root: Path) -> list[str]:
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
    """Poll forever; run today's round for any active competition that is due."""
    log.info("arena scheduler started (poll=%.0fs, root=%s)", poll_seconds, root)
    while True:
        try:
            await _scheduler_tick(root)
        except Exception:  # never let one bad tick kill the loop
            log.exception("arena scheduler tick failed")
        await asyncio.sleep(poll_seconds)


async def _scheduler_tick(root: Path) -> None:
    now = datetime.now(UTC)
    for run_id in _active_run_ids(root):
        path = run_dir(root, run_id)
        config = load_run_config(path)
        meta = load_metadata(path)
        if not is_due(now, config, meta.get("last_round_date")):
            continue
        round_id = current_trading_round_id(config, now)
        if not retry_allowed(meta, round_id=round_id, now=now):
            continue
        lock = lock_for(run_id)
        if lock.locked():  # a manual round for this competition is in flight
            continue
        log.info("scheduler running round for %s", run_id)
        async with lock:
            try:
                await asyncio.to_thread(run_round_for, root, run_id)
            except Exception as exc:  # back off on this competition, keep scheduling others
                log.exception("scheduled round failed for %s", run_id)
                _record_failed_attempt(path, round_id=round_id, error=str(exc))
            else:
                if meta.get("round_attempt"):
                    update_metadata(path, round_attempt=None)


def retry_allowed(meta: dict, *, round_id: str, now: datetime) -> bool:
    """False while today's failed round is backing off or has exhausted its attempts."""
    attempt = meta.get("round_attempt") or {}
    if attempt.get("round_id") != round_id:
        return True
    if attempt.get("attempts", 0) >= MAX_ROUND_ATTEMPTS:
        return False
    next_at = attempt.get("next_attempt_at")
    return next_at is None or now >= datetime.fromisoformat(next_at)


def _record_failed_attempt(path: Path, *, round_id: str, error: str) -> None:
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
