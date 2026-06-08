from __future__ import annotations

import argparse
import json
from pathlib import Path

from arena.data import fetch_market_snapshot
from arena.leaderboard import build_leaderboard
from arena.portfolio import initial_state
from arena.scheduler import run_round_for
from arena.state import (
    AGENTS,
    init_run,
    load_config,
    load_latest_state,
    load_metadata,
    local_date_stamp,
    read_json,
    run_dir,
    write_json,
)
from port.bootstrap import bootstrap
from port.config import config

ARENA_ROOT = Path(__file__).resolve().parent


def _print_json(payload: object) -> None:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")  # type: ignore[assignment]
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _cmd_init(args: argparse.Namespace) -> int:
    config_obj = load_config(Path(args.config))
    snapshot = fetch_market_snapshot(
        config_obj.watchlist, benchmark=config_obj.benchmark, include_web_news=False
    )
    missing = [p.ticker for p in config_obj.positions if p.ticker not in snapshot.prices]
    if missing:
        raise RuntimeError("Cannot initialize; missing prices for " + ", ".join(missing))
    as_of = f"{local_date_stamp(config_obj.timezone)}-initial"
    states = {
        agent_id: initial_state(config_obj, snapshot.prices, agent_id=agent_id, as_of=as_of)
        for agent_id in AGENTS
    }
    path = init_run(ARENA_ROOT, config_obj, states)
    write_json(path / "initial-snapshot.json", snapshot.model_dump(mode="json"))
    _print_json({"run_id": path.name, "path": str(path)})
    return 0


def _cmd_run_round(args: argparse.Namespace) -> int:
    record = run_round_for(ARENA_ROOT, args.run_id)
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
        "metadata": load_metadata(path),
        "latest_states": {
            agent_id: load_latest_state(path, agent_id).model_dump(mode="json")
            for agent_id in AGENTS
        },
        "leaderboard": [row.model_dump(mode="json") for row in build_leaderboard(path)],
    }
    _print_json(payload)
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    host = args.host or config.arena.server_host
    port = args.port or config.arena.server_port
    uvicorn.run("arena.web.app:app", host=host, port=port, log_level="info")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="arena")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Run the arena web app + scheduler engine.")
    serve_parser.add_argument("--host", default=None)
    serve_parser.add_argument("--port", type=int, default=None)
    serve_parser.set_defaults(func=_cmd_serve)

    init_parser = subparsers.add_parser("init", help="Create a new competition from a config JSON.")
    init_parser.add_argument("--config", required=True, help="Arena config JSON path.")
    init_parser.set_defaults(func=_cmd_init)

    round_parser = subparsers.add_parser("run-round", help="Run one competition round now.")
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
