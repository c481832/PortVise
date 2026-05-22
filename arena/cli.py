from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from arena.agents import run_advisor_enabled_agent, run_baseline_agent
from arena.data import fetch_market_snapshot
from arena.leaderboard import build_leaderboard
from arena.models import AgentRoundResult, ArenaConfig, RoundRecord
from arena.portfolio import apply_decision, initial_state
from arena.state import (
    AGENTS,
    init_run,
    load_config,
    load_latest_state,
    read_json,
    run_dir,
    save_round,
    save_state,
    write_json,
)
from port.bootstrap import bootstrap

ARENA_ROOT = Path(__file__).resolve().parent


def _print_json(payload: object) -> None:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")  # type: ignore[assignment]
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _cmd_init(args: argparse.Namespace) -> int:
    config = load_config(Path(args.config))
    snapshot = fetch_market_snapshot(
        config.watchlist,
        benchmark=config.benchmark,
        include_web_news=False,
    )
    missing = [
        position.ticker for position in config.positions if position.ticker not in snapshot.prices
    ]
    if missing:
        raise RuntimeError("Cannot initialize; missing prices for " + ", ".join(missing))
    states = {
        agent_id: initial_state(
            config,
            snapshot.prices,
            agent_id=agent_id,
            as_of=f"{snapshot.as_of}-initial",
        )
        for agent_id in AGENTS
    }
    path = init_run(ARENA_ROOT, config, states)
    write_json(path / "initial-snapshot.json", snapshot.model_dump(mode="json"))
    _print_json({"run_id": path.name, "path": str(path)})
    return 0


def _load_run_config(run_id: str) -> ArenaConfig:
    return ArenaConfig.model_validate(read_json(run_dir(ARENA_ROOT, run_id) / "config.json"))


def _cmd_run_round(args: argparse.Namespace) -> int:
    path = run_dir(ARENA_ROOT, args.run_id)
    config = _load_run_config(args.run_id)
    snapshot = fetch_market_snapshot(config.watchlist, benchmark=config.benchmark, include_web_news=True)
    round_id = snapshot.as_of
    started_at = datetime.now(UTC)
    results: dict[str, AgentRoundResult] = {}

    baseline_state = load_latest_state(path, "baseline")
    baseline_decision = run_baseline_agent(config, baseline_state, snapshot)
    next_baseline, baseline_trades, baseline_corrections = apply_decision(
        baseline_state,
        baseline_decision,
        snapshot.prices,
        config,
        as_of=round_id,
    )
    save_state(path, "baseline", next_baseline)
    results["baseline"] = AgentRoundResult(
        agent_id="baseline",
        decision=baseline_decision,
        trades=baseline_trades,
        corrections=baseline_corrections,
        state=next_baseline,
    )

    advisor_state = load_latest_state(path, "advisor_enabled")
    advisor_work_dir = path / "advisor" / round_id
    advisor_decision, advisor_result_path = run_advisor_enabled_agent(
        config,
        advisor_state,
        snapshot,
        work_dir=advisor_work_dir,
    )
    next_advisor, advisor_trades, advisor_corrections = apply_decision(
        advisor_state,
        advisor_decision,
        snapshot.prices,
        config,
        as_of=round_id,
    )
    save_state(path, "advisor_enabled", next_advisor)
    results["advisor_enabled"] = AgentRoundResult(
        agent_id="advisor_enabled",
        decision=advisor_decision,
        trades=advisor_trades,
        corrections=advisor_corrections,
        state=next_advisor,
        advisor_result_path=str(advisor_result_path),
    )

    record = RoundRecord(
        round_id=round_id,
        started_at=started_at,
        snapshot=snapshot,
        results=results,
    )
    save_round(path, record)
    _print_json(record)
    return 0


def _cmd_rank(args: argparse.Namespace) -> int:
    rows = build_leaderboard(run_dir(ARENA_ROOT, args.run_id))
    _print_json([row.model_dump(mode="json") for row in rows])
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    path = run_dir(ARENA_ROOT, args.run_id)
    payload = {
        "run_id": args.run_id,
        "config": read_json(path / "config.json"),
        "latest_states": {
            agent_id: load_latest_state(path, agent_id).model_dump(mode="json")
            for agent_id in AGENTS
        },
        "leaderboard": [row.model_dump(mode="json") for row in build_leaderboard(path)],
    }
    _print_json(payload)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m arena.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a new arena run.")
    init_parser.add_argument(
        "--config",
        required=True,
        help="Arena config JSON path.",
    )
    init_parser.set_defaults(func=_cmd_init)

    round_parser = subparsers.add_parser("run-round", help="Run one competition round.")
    round_parser.add_argument("--run-id", required=True)
    round_parser.set_defaults(func=_cmd_run_round)

    rank_parser = subparsers.add_parser("rank", help="Print the current leaderboard.")
    rank_parser.add_argument("--run-id", required=True)
    rank_parser.set_defaults(func=_cmd_rank)

    show_parser = subparsers.add_parser("show", help="Print run config, states, and leaderboard.")
    show_parser.add_argument("--run-id", required=True)
    show_parser.set_defaults(func=_cmd_show)
    return parser


def main(argv: list[str] | None = None) -> int:
    bootstrap()
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
