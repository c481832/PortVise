from __future__ import annotations

import argparse
import json
from pathlib import Path

from arena.config import config
from arena.leaderboard import load_leaderboard
from arena.run_store import (
    AGENTS,
    ARENA_ROOT,
    load_config,
    load_latest_state,
    load_metadata,
    read_json,
    run_dir,
)
from arena.scheduler import create_competition, run_round_for


def print_json(payload: object) -> None:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")  # type: ignore[assignment]
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def init_command(args: argparse.Namespace) -> int:
    path = create_competition(ARENA_ROOT, load_config(Path(args.config)))
    print_json({"run_id": path.name, "path": str(path)})
    return 0


def run_round_command(args: argparse.Namespace) -> int:
    record = run_round_for(ARENA_ROOT, args.run_id)
    print_json(record)
    return 0


def rank_command(args: argparse.Namespace) -> int:
    rows = load_leaderboard(run_dir(ARENA_ROOT, args.run_id))
    print_json([row.model_dump(mode="json") for row in rows])
    return 0


def show_command(args: argparse.Namespace) -> int:
    path = run_dir(ARENA_ROOT, args.run_id)
    payload = {
        "run_id": args.run_id,
        "config": read_json(path / "config.json"),
        "metadata": load_metadata(path),
        "latest_states": {
            agent_id: load_latest_state(path, agent_id).model_dump(mode="json")
            for agent_id in AGENTS
        },
        "leaderboard": [row.model_dump(mode="json") for row in load_leaderboard(path)],
    }
    print_json(payload)
    return 0


def serve_command(args: argparse.Namespace) -> int:
    import uvicorn

    host = args.host or config.server_host
    port = args.port or config.server_port
    uvicorn.run("arena.web.app:app", host=host, port=port, log_level="info")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="arena")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Run the arena web app + scheduler engine.")
    serve_parser.add_argument("--host", default=None)
    serve_parser.add_argument("--port", type=int, default=None)
    serve_parser.set_defaults(func=serve_command)

    init_parser = subparsers.add_parser("init", help="Create a new competition from a config JSON.")
    init_parser.add_argument("--config", required=True, help="Arena config JSON path.")
    init_parser.set_defaults(func=init_command)

    round_parser = subparsers.add_parser("run-round", help="Run one competition round now.")
    round_parser.add_argument("--run-id", required=True)
    round_parser.set_defaults(func=run_round_command)

    rank_parser = subparsers.add_parser("rank", help="Print the current leaderboard.")
    rank_parser.add_argument("--run-id", required=True)
    rank_parser.set_defaults(func=rank_command)

    show_parser = subparsers.add_parser("show", help="Print run config, states, and leaderboard.")
    show_parser.add_argument("--run-id", required=True)
    show_parser.set_defaults(func=show_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
