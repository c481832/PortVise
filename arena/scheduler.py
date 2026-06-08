"""Run one round per market day, and the engine loop that fires it on schedule.

``run_round_for`` is the single producer of a round: it fetches a snapshot, runs both agents,
applies their decisions, and writes the day's states, ledger entries, and RoundRecord. It is
called by the GUI "Run round now" button, the headless CLI, and the scheduler loop.

``run_scheduler`` is a long-running async loop: it wakes periodically and, for every active
competition whose configured ``trade_time`` has passed on a market weekday and that has not yet
recorded today's round, runs one round. A failed round is logged and recorded on the competition
but does not stop the loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from arena.agents import run_advisor_enabled_agent, run_baseline_agent
from arena.data import fetch_market_snapshot
from arena.models import AgentRoundResult, ArenaConfig, RoundRecord
from arena.portfolio import apply_decision
from arena.state import (
    append_ledger,
    load_latest_state,
    load_metadata,
    local_date_stamp,
    read_json,
    run_dir,
    save_round,
    save_state,
    update_metadata,
)

log = logging.getLogger(__name__)

ProgressFn = Callable[[dict], None]

SCHEDULER_POLL_SECONDS = 30.0


def _emit(progress: ProgressFn | None, **event: object) -> None:
    if progress is not None:
        progress(dict(event))


def load_run_config(path: Path) -> ArenaConfig:
    return ArenaConfig.model_validate(read_json(path / "config.json"))


def run_round_for(root: Path, run_id: str, *, progress: ProgressFn | None = None) -> RoundRecord:
    """Run one competition round for both agents and persist all of it. Idempotent per local day."""
    path = run_dir(root, run_id)
    config = load_run_config(path)
    round_id = local_date_stamp(config.timezone)
    started_at = datetime.now(UTC)

    _emit(progress, stage="snapshot", message="Fetching market snapshot")
    snapshot = fetch_market_snapshot(
        config.watchlist, benchmark=config.benchmark, include_web_news=True
    )

    results: dict[str, AgentRoundResult] = {}

    _emit(progress, stage="baseline", message="Baseline agent trading")
    baseline_state = load_latest_state(path, "baseline")
    baseline_decision = run_baseline_agent(config, baseline_state, snapshot)
    next_baseline, baseline_trades, baseline_corrections = apply_decision(
        baseline_state, baseline_decision, snapshot.prices, config, as_of=round_id
    )
    save_state(path, "baseline", next_baseline)
    append_ledger(path, "baseline", round_id, baseline_trades)
    results["baseline"] = AgentRoundResult(
        agent_id="baseline",
        decision=baseline_decision,
        trades=baseline_trades,
        corrections=baseline_corrections,
        state=next_baseline,
    )

    _emit(progress, stage="advisor", message="Advisor agent running PortVise review")
    advisor_state = load_latest_state(path, "advisor_enabled")
    advisor_decision, advisor_result_path = run_advisor_enabled_agent(
        config, advisor_state, snapshot, work_dir=path / "advisor" / round_id
    )
    next_advisor, advisor_trades, advisor_corrections = apply_decision(
        advisor_state, advisor_decision, snapshot.prices, config, as_of=round_id
    )
    save_state(path, "advisor_enabled", next_advisor)
    append_ledger(path, "advisor_enabled", round_id, advisor_trades)
    results["advisor_enabled"] = AgentRoundResult(
        agent_id="advisor_enabled",
        decision=advisor_decision,
        trades=advisor_trades,
        corrections=advisor_corrections,
        state=next_advisor,
        advisor_result_path=str(advisor_result_path),
    )

    record = RoundRecord(
        round_id=round_id, started_at=started_at, snapshot=snapshot, results=results
    )
    save_round(path, record)
    update_metadata(path, last_round_date=round_id)
    _emit(progress, stage="done", message="Round complete", round_id=round_id)
    return record


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
        log.info("scheduler running round for %s", run_id)
        try:
            await asyncio.to_thread(run_round_for, root, run_id)
        except Exception as exc:  # surface on the competition, keep scheduling others
            log.exception("scheduled round failed for %s", run_id)
            errors = list(meta.get("errors") or [])
            errors.append(f"{now.isoformat()}: {exc}")
            update_metadata(path, errors=errors[-20:])
