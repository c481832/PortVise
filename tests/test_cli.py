from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from port.agent_api_models import AgentReviewResult
from port.cli import main
from port.models import ManagerReview


class _NoReadStdin(StringIO):
    def read(self, *_args, **_kwargs) -> str:
        raise AssertionError("stdin should not be read")


def _payload() -> dict:
    return {
        "portfolio": {
            "name": "CLI Test",
            "positions": [
                {
                    "ticker": "AAPL",
                    "name": "Apple",
                    "weight": 0.1,
                    "sector": "Technology",
                    "quantity": 10,
                    "entry_date": "2023-01-01",
                    "entry_price": 150.0,
                    "current_price": 180.0,
                    "dividend": 0.0,
                    "split": 1.0,
                    "entry_thesis": "Services growth",
                    "asset_class": "equity",
                    "country": "US",
                    "tags": ["quality"],
                }
            ],
            "cash_weight": 0.9,
            "base_currency": "USD",
            "benchmark": "SPY",
            "review_date": "2026-04-29",
            "context_note": "",
        },
        "corporate_actions": "off",
    }


def _done_result() -> AgentReviewResult:
    manager_review = ManagerReview.model_validate(
        {
            "portfolio_verdict": {
                "action_timing": "watch",
                "investment_horizon": "tactical",
                "horizon_detail": "1-4 weeks",
                "primary_risk": "",
                "recommended_posture": "",
                "revisit_trigger": "Risk conditions change.",
                "rationale": "",
            },
            "actions": [],
            "do_nothing_case": "",
            "executive_summary": "Done",
        }
    )
    return AgentReviewResult(
        review_id="review-1",
        status="done",
        started_at="2026-04-29T00:00:00+00:00",
        finished_at="2026-04-29T00:01:00+00:00",
        requested_locale="en",
        content_locale="en",
        manager_review=manager_review,
    )


def test_cli_run_reads_file_and_writes_stdout(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "request.json"
    input_path.write_text(json.dumps(_payload()), encoding="utf-8")

    with patch("port.cli.run_review", return_value=_done_result()):
        code = main(["run", str(input_path)])

    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["manager_review"]["executive_summary"] == "Done"
    assert captured.err == ""


def test_cli_run_initializes_file_logging(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "request.json"
    input_path.write_text(json.dumps(_payload()), encoding="utf-8")

    with (
        patch("port.cli.apply_cli_logging_config") as configure_logging,
        patch("port.cli.run_review", return_value=_done_result()),
    ):
        code = main(["run", str(input_path)])

    assert code == 0
    configure_logging.assert_called_once_with()
    assert json.loads(capsys.readouterr().out)["status"] == "done"


def test_cli_run_writes_output_file(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    input_path.write_text(json.dumps(_payload()), encoding="utf-8")

    with patch("port.cli.run_review", return_value=_done_result()):
        code = main(["run", str(input_path), "--output", str(output_path)])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == ""
    assert json.loads(output_path.read_text(encoding="utf-8"))["status"] == "done"


def test_cli_run_reads_stdin_when_input_is_dash(capsys) -> None:
    with (
        patch("sys.stdin", StringIO(json.dumps(_payload()))),
        patch("port.cli.run_review", return_value=_done_result()),
    ):
        code = main(["run", "-"])

    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["status"] == "done"
    assert captured.err == ""


def test_cli_run_pretty_prints_output(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "request.json"
    input_path.write_text(json.dumps(_payload()), encoding="utf-8")

    with patch("port.cli.run_review", return_value=_done_result()):
        code = main(["run", str(input_path), "--pretty"])

    captured = capsys.readouterr()
    assert code == 0
    assert "\n  " in captured.out
    assert json.loads(captured.out)["status"] == "done"


def test_cli_run_progress_prints_events_to_stderr(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "request.json"
    input_path.write_text(json.dumps(_payload()), encoding="utf-8")

    async def fake_run_review(_request, *, progress_callback):
        progress_callback(
            {
                "type": "agent_step",
                "agent": "planner",
                "label": "Planning news search queries...",
                "elapsed_seconds": 1.23,
            }
        )
        return _done_result()

    with patch("port.cli.run_review", side_effect=fake_run_review):
        code = main(["run", str(input_path), "--progress"])

    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["status"] == "done"
    assert "[00:01]" in captured.err
    assert "planner: Planning news search queries..." in captured.err


def test_cli_run_timeout_override_is_passed_to_run_review(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "request.json"
    input_path.write_text(json.dumps(_payload()), encoding="utf-8")

    with patch("port.cli.run_review", return_value=_done_result()) as run_review:
        code = main(["run", str(input_path), "--timeout-seconds", "12"])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    assert run_review.await_args is not None
    request = run_review.await_args.args[0]
    assert request.timeout_seconds == 12


def test_cli_run_negative_timeout_returns_2_without_running_review(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "request.json"
    input_path.write_text(json.dumps(_payload()), encoding="utf-8")

    with patch("port.cli.run_review", return_value=_done_result()) as run_review:
        code = main(["run", str(input_path), "--timeout-seconds", "-1"])

    captured = capsys.readouterr()
    assert code == 2
    assert "timeout" in captured.err
    assert captured.out == ""
    run_review.assert_not_called()


def test_cli_run_negative_timeout_with_stdin_does_not_read_or_run(capsys) -> None:
    with (
        patch("sys.stdin", _NoReadStdin()),
        patch("port.cli.run_review", return_value=_done_result()) as run_review,
    ):
        code = main(["run", "-", "--timeout-seconds", "-1"])

    captured = capsys.readouterr()
    assert code == 2
    assert "timeout" in captured.err
    assert captured.out == ""
    run_review.assert_not_called()


def test_cli_run_invalid_input_returns_2(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "bad.json"
    input_path.write_text("{", encoding="utf-8")

    code = main(["run", str(input_path)])

    captured = capsys.readouterr()
    assert code == 2
    assert "Invalid JSON" in captured.err
    assert captured.out == ""


def test_cli_run_error_result_returns_3(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "request.json"
    input_path.write_text(json.dumps(_payload()), encoding="utf-8")
    result = AgentReviewResult(
        review_id="review-1",
        status="error",
        started_at="2026-04-29T00:00:00+00:00",
        finished_at="2026-04-29T00:01:00+00:00",
        requested_locale="en",
        content_locale="en",
        error="model unavailable",
    )

    with patch("port.cli.run_review", return_value=result):
        code = main(["run", str(input_path)])

    captured = capsys.readouterr()
    assert code == 3
    assert "model unavailable" in captured.err
    assert "Detailed logs:" in captured.err
    assert "agents/*.log" in captured.err
    assert captured.out == ""


def test_cli_run_review_exception_returns_3(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "request.json"
    input_path.write_text(json.dumps(_payload()), encoding="utf-8")

    with patch("port.cli.run_review", side_effect=RuntimeError("boom")):
        code = main(["run", str(input_path)])

    captured = capsys.readouterr()
    assert code == 3
    assert "boom" in captured.err
    assert "Detailed logs:" in captured.err
    assert captured.out == ""


def test_cli_run_timeout_result_returns_4(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "request.json"
    input_path.write_text(json.dumps(_payload()), encoding="utf-8")
    result = AgentReviewResult(
        review_id="review-1",
        status="timeout",
        started_at="2026-04-29T00:00:00+00:00",
        finished_at="2026-04-29T00:01:00+00:00",
        requested_locale="en",
        content_locale="en",
        error="review timed out",
    )

    with patch("port.cli.run_review", return_value=result):
        code = main(["run", str(input_path)])

    captured = capsys.readouterr()
    assert code == 4
    assert "review timed out" in captured.err
    assert "Detailed logs:" in captured.err
    assert captured.out == ""


def test_cli_run_output_write_error_returns_3(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "request.json"
    output_path = tmp_path / "missing" / "result.json"
    input_path.write_text(json.dumps(_payload()), encoding="utf-8")

    with patch("port.cli.run_review", return_value=_done_result()):
        code = main(["run", str(input_path), "--output", str(output_path)])

    captured = capsys.readouterr()
    assert code == 3
    assert "Could not write output" in captured.err
    assert captured.out == ""


def test_cli_schema_prints_request_schema(capsys) -> None:
    code = main(["schema", "input"])

    captured = capsys.readouterr()
    assert code == 0
    assert "portfolio" in json.loads(captured.out)["properties"]


def test_cli_schema_prints_result_schema(capsys) -> None:
    code = main(["schema", "output"])

    captured = capsys.readouterr()
    assert code == 0
    assert "manager_review" in json.loads(captured.out)["properties"]
