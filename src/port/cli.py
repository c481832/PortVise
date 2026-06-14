from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, TextIO

from pydantic import ValidationError

from port.agent_api_models import AgentReviewRequest, AgentReviewResult
from port.bootstrap import bootstrap
from port.review_runner import run_review

EXIT_OK = 0
EXIT_INVALID_INPUT = 2
EXIT_REVIEW_FAILED = 3
EXIT_TIMEOUT = 4


def _read_json(path: str, stdin: TextIO) -> dict[str, Any]:
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


def _write_json(payload: dict[str, Any], *, output: str | None, pretty: bool) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None)
    if output:
        Path(output).write_text(f"{text}\n", encoding="utf-8")
        return
    sys.stdout.write(f"{text}\n")


def _format_progress_event(event: dict[str, Any]) -> str:
    elapsed = int(float(event.get("elapsed_seconds") or 0))
    minutes, seconds = divmod(elapsed, 60)
    label = str(event.get("label") or event.get("type") or "progress")
    agent = event.get("agent")
    if isinstance(agent, str) and agent:
        label = f"{agent}: {label}"
    return f"[{minutes:02d}:{seconds:02d}] {label}"


def _print_progress(event: dict[str, Any]) -> None:
    print(_format_progress_event(event), file=sys.stderr, flush=True)


async def _run_command(args: argparse.Namespace) -> int:
    if args.timeout_seconds is not None and args.timeout_seconds < 0:
        print("timeout_seconds must be non-negative.", file=sys.stderr)
        return EXIT_INVALID_INPUT

    try:
        payload = _read_json(args.input, sys.stdin)
        request = AgentReviewRequest(**payload)
    except (ValueError, ValidationError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID_INPUT

    if args.timeout_seconds is not None:
        request = request.model_copy(update={"timeout_seconds": args.timeout_seconds})

    try:
        result = await run_review(
            request,
            progress_callback=_print_progress if args.progress else None,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_REVIEW_FAILED

    if result.status != "done":
        print(result.error or f"Review finished with status: {result.status}", file=sys.stderr)
        return EXIT_TIMEOUT if result.status == "timeout" else EXIT_REVIEW_FAILED

    try:
        _write_json(result.model_dump(mode="json"), output=args.output, pretty=args.pretty)
    except OSError as exc:
        print(f"Could not write output: {exc}", file=sys.stderr)
        return EXIT_REVIEW_FAILED
    return EXIT_OK


def _schema_command(args: argparse.Namespace) -> int:
    model = AgentReviewRequest if args.kind == "input" else AgentReviewResult
    schema = model.model_json_schema()
    sys.stdout.write(json.dumps(schema, ensure_ascii=False, indent=2) + "\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="port-review")
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
    run_parser.set_defaults(func=lambda args: asyncio.run(_run_command(args)))

    schema_parser = subparsers.add_parser("schema", help="Print JSON schemas.")
    schema_parser.add_argument("kind", choices=("input", "output"))
    schema_parser.set_defaults(func=_schema_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    bootstrap()
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
