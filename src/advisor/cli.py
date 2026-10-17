from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, TextIO

from pydantic import ValidationError

from advisor.logging import advisor_log_path_resolved, apply_cli_logging_config
from advisor.run_new_review import run_review
from advisor.schemas.runner import ReviewRequest, ReviewResult

EXIT_OK = 0
EXIT_INVALID_INPUT = 2
EXIT_REVIEW_FAILED = 3
EXIT_TIMEOUT = 4

log = logging.getLogger(__name__)


def print_log_hint() -> None:
    log_path = advisor_log_path_resolved()
    if log_path is None:
        return
    print(
        f"Detailed logs: {log_path} and {log_path.parent / 'agents'}/*.log",
        file=sys.stderr,
    )


def read_json(path: str, stdin: TextIO) -> dict[str, Any]:
    try:
        text = stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Could not read input: {exc}") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Input JSON must be an object.")
    return payload


def write_json(payload: dict[str, Any], *, output: str | None, pretty: bool) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None)
    if output:
        Path(output).write_text(f"{text}\n", encoding="utf-8")
        return
    sys.stdout.write(f"{text}\n")


def format_progress_event(event: dict[str, Any]) -> str:
    elapsed = int(float(event.get("elapsed_seconds") or 0))
    minutes, seconds = divmod(elapsed, 60)
    label = str(event.get("label") or event.get("type") or "progress")
    agent = event.get("agent")
    if isinstance(agent, str) and agent:
        label = f"{agent}: {label}"
    return f"[{minutes:02d}:{seconds:02d}] {label}"


def print_progress(event: dict[str, Any]) -> None:
    print(format_progress_event(event), file=sys.stderr, flush=True)


async def run_command(args: argparse.Namespace) -> int:
    if args.timeout_seconds is not None and args.timeout_seconds < 0:
        print("timeout_seconds must be non-negative.", file=sys.stderr)
        return EXIT_INVALID_INPUT

    try:
        payload = read_json(args.input, sys.stdin)
        request = ReviewRequest(**payload)
    except (ValueError, ValidationError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID_INPUT

    if args.timeout_seconds is not None:
        request = request.model_copy(update={"timeout_seconds": args.timeout_seconds})

    try:
        result = await run_review(
            request,
            progress_callback=print_progress if args.progress else None,
        )
    except Exception as exc:
        log.exception("CLI review raised an exception")
        print(str(exc), file=sys.stderr)
        print_log_hint()
        return EXIT_REVIEW_FAILED

    if result.status != "done":
        error = result.error or f"Review finished with status: {result.status}"
        log.error("Review %s finished with status %s: %s", result.review_id, result.status, error)
        print(error, file=sys.stderr)
        print_log_hint()
        return EXIT_TIMEOUT if result.status == "timeout" else EXIT_REVIEW_FAILED

    try:
        write_json(result.model_dump(mode="json"), output=args.output, pretty=args.pretty)
    except OSError as exc:
        print(f"Could not write output: {exc}", file=sys.stderr)
        return EXIT_REVIEW_FAILED
    return EXIT_OK


def schema_command(args: argparse.Namespace) -> int:
    model = ReviewRequest if args.kind == "input" else ReviewResult
    schema = model.model_json_schema()
    sys.stdout.write(json.dumps(schema, ensure_ascii=False, indent=2) + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="advisor-review")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a portfolio review from JSON input.")
    run_parser.add_argument("input", help="Request JSON file, or '-' for stdin.")
    run_parser.add_argument("--output", help="Write result JSON to this file instead of stdout.")
    run_parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    run_parser.add_argument(
        "--progress",
        action="store_true",
        help="Stream review progress to stderr while keeping final JSON on stdout/output.",
    )
    run_parser.add_argument(
        "--timeout-seconds",
        type=int,
        help="Override request timeout in seconds; 0 disables the explicit timeout.",
    )
    run_parser.set_defaults(func=lambda args: asyncio.run(run_command(args)))

    schema_parser = subparsers.add_parser("schema", help="Print JSON schemas.")
    schema_parser.add_argument("kind", choices=("input", "output"))
    schema_parser.set_defaults(func=schema_command)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "run":
        apply_cli_logging_config()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
