from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

from arena import cli
from arena import scheduler as arena_scheduler
from arena.agents import run_advisor_enabled_agent, run_baseline_agent
from arena.leaderboard import build_leaderboard
from arena.models import (
    AgentDecision,
    AgentRoundResult,
    ArenaConfig,
    ArenaPosition,
    Holding,
    MarketSnapshot,
    PortfolioState,
    RoundRecord,
)
from arena.portfolio import apply_decision, initial_state
from arena.scheduler import run_round_for
from arena.state import init_run, save_round
from arena.web import routes as arena_routes
from arena.web.app import create_app


def _config() -> ArenaConfig:
    return ArenaConfig(
        run_name="test-arena",
        starting_cash=1_000.0,
        positions=[
            ArenaPosition(
                ticker="AAPL",
                name="Apple",
                quantity=10.0,
                sector="Technology",
                entry_date=date(2025, 1, 2),
                entry_price=100.0,
                entry_thesis="Quality growth",
            )
        ],
        watchlist=["AAPL", "MSFT", "SPY"],
        benchmark="SPY",
        transaction_cost_bps=10.0,
        max_position_weight=0.50,
        max_holdings=3,
        cash_return_annual_pct=0.0,
        min_trade_value=1.0,
        min_cash_weight=0.05,
        corporate_actions="off",
    )


def _snapshot(
    price: float = 100.0,
    spy: float = 500.0,
    as_of: str = "20260504T210000Z",
) -> MarketSnapshot:
    return MarketSnapshot(
        as_of=as_of,
        prices={"AAPL": price, "MSFT": 200.0, "SPY": spy},
        benchmark="SPY",
        benchmark_price=spy,
        price_movement={"AAPL": {"change_1d_pct": 1.0}},
        headlines={"AAPL": ["Apple headline"]},
    )


def test_apply_decision_enforces_watchlist_cash_and_costs() -> None:
    config = _config()
    state = initial_state(config, _snapshot().prices, agent_id="baseline", as_of="initial")
    decision = AgentDecision(
        target_weights={"AAPL": 0.75, "MSFT": 0.40, "TSLA": 0.20},
        cash_weight=0.0,
        rationale="Test rebalance",
    )

    next_state, trades, corrections = apply_decision(
        state,
        decision,
        _snapshot().prices,
        config,
        as_of="round-1",
    )

    assert next_state.cash >= 0
    assert trades
    assert any("Rejected unknown ticker TSLA" in item for item in corrections)
    assert any("Clipped AAPL" in item for item in corrections)
    assert sum(trade.transaction_cost for trade in trades) > 0


def test_apply_decision_trades_whole_shares() -> None:
    config = _config()
    state = initial_state(config, _snapshot().prices, agent_id="baseline", as_of="initial")
    decision = AgentDecision(
        # MSFT desired value is $900 at $200/share -> 4.5 shares, must floor to 4.
        # SPY desired value is $200 at $500/share -> 0.4 shares, must be skipped.
        target_weights={"AAPL": 0.30, "MSFT": 0.45, "SPY": 0.10},
        cash_weight=0.0,
    )

    next_state, trades, corrections = apply_decision(
        state,
        decision,
        _snapshot().prices,
        config,
        as_of="round-1",
    )

    assert all(trade.quantity == int(trade.quantity) for trade in trades)
    assert next_state.holdings["MSFT"].quantity == 4.0
    assert "SPY" not in next_state.holdings
    assert any("whole share" in item for item in corrections)


def test_apply_decision_full_liquidation_clears_fractional_holding() -> None:
    config = _config()
    state = PortfolioState(
        agent_id="baseline",
        as_of="initial",
        cash=1_000.0,
        holdings={"AAPL": Holding(ticker="AAPL", quantity=10.5, average_cost=100.0)},
        last_prices=_snapshot().prices,
        equity=2_050.0,
    )
    decision = AgentDecision(target_weights={}, cash_weight=1.0)

    next_state, trades, _corrections = apply_decision(
        state,
        decision,
        _snapshot().prices,
        config,
        as_of="round-1",
    )

    assert next_state.holdings == {}
    assert len(trades) == 1
    assert trades[0].quantity == 10.5


def test_baseline_agent_does_not_call_advisor_cli() -> None:
    config = _config()
    state = initial_state(config, _snapshot().prices, agent_id="baseline", as_of="initial")
    expected = AgentDecision(target_weights={"AAPL": 0.25}, cash_weight=0.75)

    with (
        patch("arena.agents.port_config.invoke_structured", return_value=expected) as invoke,
        patch("arena.agents.run_advisor_cli") as advisor_cli,
    ):
        decision = run_baseline_agent(config, state, _snapshot())

    assert decision == expected
    assert invoke.call_count == 1
    assert invoke.call_args.kwargs["agent"] == "arena_baseline"
    assert invoke.call_args.kwargs["use_agent_model"] is False
    advisor_cli.assert_not_called()


def test_advisor_enabled_agent_calls_repo_cli_and_uses_result(tmp_path: Path) -> None:
    config = _config()
    state = initial_state(config, _snapshot().prices, agent_id="advisor_enabled", as_of="initial")
    expected = AgentDecision(target_weights={"MSFT": 0.20}, cash_weight=0.80)

    def fake_cli(*, request_path: Path, output_path: Path, timeout_seconds: int) -> None:
        assert request_path.exists()
        assert timeout_seconds == config.advisor_timeout_seconds
        output_path.write_text(
            json.dumps(
                {
                    "status": "done",
                    "manager_review": {"executive_summary": "Reduce concentration"},
                    "warnings": [],
                }
            ),
            encoding="utf-8",
        )

    with (
        patch("arena.agents.run_advisor_cli", side_effect=fake_cli) as advisor_cli,
        patch("arena.agents.port_config.invoke_structured", return_value=expected) as invoke,
    ):
        decision, result_path = run_advisor_enabled_agent(
            config,
            state,
            _snapshot(),
            work_dir=tmp_path,
            review_date=date(2026, 5, 4),
        )

    assert decision == expected
    assert result_path.exists()
    assert advisor_cli.call_count == 1
    assert invoke.call_count == 1
    assert invoke.call_args.kwargs["agent"] == "arena_advisor_enabled"
    assert invoke.call_args.kwargs["use_agent_model"] is False
    prompt = invoke.call_args.args[1][1].content
    assert "Reduce concentration" in prompt


def test_leaderboard_builds_rows_from_round_records(tmp_path: Path) -> None:
    config = _config()
    states = {
        "baseline": initial_state(
            config,
            _snapshot(100, 500).prices,
            agent_id="baseline",
            as_of="0",
        ),
        "advisor_enabled": initial_state(
            config,
            _snapshot(100, 500).prices,
            agent_id="advisor_enabled",
            as_of="0",
        ),
    }
    run_path = init_run(tmp_path, config, states)

    baseline_state = states["baseline"].model_copy(update={"as_of": "1", "equity": 1_900.0})
    advisor_state = states["advisor_enabled"].model_copy(update={"as_of": "1", "equity": 2_200.0})
    from arena.state import save_state

    save_state(run_path, "baseline", baseline_state)
    save_state(run_path, "advisor_enabled", advisor_state)
    record = RoundRecord(
        round_id="1",
        started_at=datetime.now(UTC),
        snapshot=_snapshot(120, 510, as_of="1"),
        results={
            "baseline": AgentRoundResult(
                agent_id="baseline",
                decision=AgentDecision(),
                state=baseline_state,
            ),
            "advisor_enabled": AgentRoundResult(
                agent_id="advisor_enabled",
                decision=AgentDecision(),
                state=advisor_state,
            ),
        },
    )
    save_round(run_path, record)

    rows = build_leaderboard(run_path)

    by_agent = {row.agent_id: row for row in rows}
    assert set(by_agent) == {"baseline", "advisor_enabled"}
    assert by_agent["advisor_enabled"].rounds == 1
    assert (
        by_agent["advisor_enabled"].cumulative_return > by_agent["baseline"].cumulative_return
    )


def test_cli_init_uses_same_initial_state_for_both_agents(tmp_path: Path, capsys) -> None:
    from arena.state import local_date_stamp

    config = _config()
    config_path = tmp_path / "config.json"
    config_path.write_text(config.model_dump_json(), encoding="utf-8")
    snapshot = _snapshot()
    as_of = f"{local_date_stamp(config.timezone)}-initial"

    with (
        patch.object(cli, "ARENA_ROOT", tmp_path),
        patch("arena.cli.fetch_market_snapshot", return_value=snapshot),
    ):
        code = cli.main(["init", "--config", str(config_path)])

    captured = capsys.readouterr()
    assert code == 0
    run_id = json.loads(captured.out)["run_id"]
    baseline = json.loads(
        (tmp_path / "runs" / run_id / "states" / "baseline" / f"{as_of}.json").read_text(
            encoding="utf-8"
        )
    )
    advisor = json.loads(
        (tmp_path / "runs" / run_id / "states" / "advisor_enabled" / f"{as_of}.json").read_text(
            encoding="utf-8"
        )
    )
    assert baseline["equity"] == advisor["equity"]
    assert baseline["holdings"] == advisor["holdings"]


def test_round_retry_does_not_advance_one_agent_twice(tmp_path: Path) -> None:
    from arena.scheduler import current_trading_round_id
    from arena.state import read_json

    config = _config()
    states = {
        "baseline": initial_state(config, _snapshot().prices, agent_id="baseline", as_of="initial"),
        "advisor_enabled": initial_state(
            config,
            _snapshot().prices,
            agent_id="advisor_enabled",
            as_of="initial",
        ),
    }
    run_path = init_run(tmp_path, config, states)
    round_id = current_trading_round_id(config)
    baseline_inputs = []

    def fake_baseline(_config, state, _snapshot):
        baseline_inputs.append(state)
        return AgentDecision(target_weights={"MSFT": 0.50}, cash_weight=0.50)

    with (
        patch("arena.scheduler.fetch_market_snapshot", return_value=_snapshot()),
        patch("arena.scheduler.run_baseline_agent", side_effect=fake_baseline),
        patch(
            "arena.scheduler.run_advisor_enabled_agent",
            side_effect=RuntimeError("advisor failed"),
        ),
        suppress(RuntimeError),
    ):
        run_round_for(tmp_path, run_path.name)

    assert not (run_path / "states" / "baseline" / f"{round_id}.json").exists()
    meta = read_json(run_path / "metadata.json")
    assert meta["agent_status"]["baseline"]["status"] == "complete"
    assert meta["agent_status"]["advisor_enabled"]["status"] == "failed"

    with (
        patch("arena.scheduler.fetch_market_snapshot", return_value=_snapshot()),
        patch("arena.scheduler.run_baseline_agent", side_effect=fake_baseline),
        patch(
            "arena.scheduler.run_advisor_enabled_agent",
            return_value=(AgentDecision(target_weights={"AAPL": 0.50}, cash_weight=0.50), tmp_path),
        ),
    ):
        record = run_round_for(tmp_path, run_path.name)

    assert record.round_id == round_id
    assert len(baseline_inputs) == 2
    assert baseline_inputs[1].as_of == "initial"
    assert set(baseline_inputs[1].holdings) == {"AAPL"}


def _init_test_run(tmp_path: Path) -> Path:
    config = _config()
    states = {
        "baseline": initial_state(config, _snapshot().prices, agent_id="baseline", as_of="0"),
        "advisor_enabled": initial_state(
            config,
            _snapshot().prices,
            agent_id="advisor_enabled",
            as_of="0",
        ),
    }
    return init_run(tmp_path, config, states)


def test_retry_allowed_backs_off_then_gives_up_for_the_day() -> None:
    from arena.scheduler import MAX_ROUND_ATTEMPTS, retry_allowed

    now = datetime(2026, 7, 6, 15, 0, tzinfo=UTC)
    assert retry_allowed({}, round_id="20260706", now=now)

    attempt = {
        "round_id": "20260706",
        "attempts": 1,
        "next_attempt_at": (now + timedelta(minutes=5)).isoformat(),
    }
    meta = {"round_attempt": attempt}
    assert not retry_allowed(meta, round_id="20260706", now=now)
    assert retry_allowed(meta, round_id="20260706", now=now + timedelta(minutes=5))

    attempt["attempts"] = MAX_ROUND_ATTEMPTS
    assert not retry_allowed(meta, round_id="20260706", now=now + timedelta(hours=6))
    assert retry_allowed(meta, round_id="20260707", now=now + timedelta(days=1))


def test_scheduler_backs_off_after_failed_round(tmp_path: Path) -> None:
    from arena.scheduler import current_trading_round_id
    from arena.state import read_json

    run_path = _init_test_run(tmp_path)
    calls: list[str] = []

    def failing_round(_root: Path, run_id: str) -> None:
        calls.append(run_id)
        raise RuntimeError("boom")

    with (
        patch("arena.scheduler.is_due", return_value=True),
        patch("arena.scheduler.run_round_for", side_effect=failing_round),
    ):
        asyncio.run(arena_scheduler._scheduler_tick(tmp_path))
        # Second tick lands inside the backoff window, so no second attempt.
        asyncio.run(arena_scheduler._scheduler_tick(tmp_path))

    assert calls == [run_path.name]
    meta = read_json(run_path / "metadata.json")
    attempt = meta["round_attempt"]
    assert attempt["round_id"] == current_trading_round_id(_config())
    assert attempt["attempts"] == 1
    assert "attempt 1/" in meta["errors"][-1]
    arena_scheduler.discard_lock(run_path.name)


def test_scheduler_skips_competition_while_manual_round_runs(tmp_path: Path) -> None:
    run_path = _init_test_run(tmp_path)
    calls: list[str] = []

    async def scenario() -> None:
        async with arena_scheduler.lock_for(run_path.name):
            await arena_scheduler._scheduler_tick(tmp_path)

    with (
        patch("arena.scheduler.is_due", return_value=True),
        patch(
            "arena.scheduler.run_round_for",
            side_effect=lambda _root, run_id: calls.append(run_id),
        ),
    ):
        asyncio.run(scenario())

    assert calls == []
    arena_scheduler.discard_lock(run_path.name)


def test_round_status_reports_engine_phase() -> None:
    from arena.web.routes import _round_status

    config = _config()  # defaults: trade_time 16:10, America/New_York
    # Friday 2026-07-10; 15:00 ET is before trade_time, 17:00 ET is after.
    before = datetime(2026, 7, 10, 19, 0, tzinfo=UTC)
    after = datetime(2026, 7, 10, 21, 0, tzinfo=UTC)

    scheduled = _round_status(config, {}, now=before)
    assert scheduled["phase"] == "scheduled"
    assert scheduled["next_run_at"].startswith("2026-07-10T16:10")

    assert _round_status(config, {}, now=after)["phase"] == "due"

    running = _round_status(
        config,
        {"active_round_id": "20260710", "agent_status": {"baseline": {"status": "running"}}},
        now=after,
    )
    assert running["phase"] == "running"
    assert running["running_agent"] == "baseline"

    complete = _round_status(
        config,
        {
            "last_round_date": "20260710",
            "agent_status": {"baseline": {"status": "complete", "updated_at": "20260710T211500Z"}},
        },
        now=after,
    )
    assert complete["phase"] == "complete"
    assert complete["completed_at"] == "20260710T211500Z"
    assert complete["next_run_at"].startswith("2026-07-13T16:10")  # skips the weekend

    retrying = _round_status(
        config,
        {
            "round_attempt": {
                "round_id": "20260710",
                "attempts": 1,
                "next_attempt_at": "2026-07-10T21:30:00+00:00",
            },
            "errors": ["boom"],
        },
        now=after,
    )
    assert retrying["phase"] == "retrying"
    assert retrying["attempts"] == 1
    assert retrying["last_error"] == "boom"

    gave_up = _round_status(
        config,
        {
            "round_attempt": {
                "round_id": "20260710",
                "attempts": arena_scheduler.MAX_ROUND_ATTEMPTS,
            },
            "errors": ["boom"],
        },
        now=after,
    )
    assert gave_up["phase"] == "failed"
    assert gave_up["next_run_at"].startswith("2026-07-13T16:10")


def test_competition_detail_includes_round_status(tmp_path: Path) -> None:
    run_path = _init_test_run(tmp_path)
    with patch.object(arena_routes, "ARENA_ROOT", tmp_path):
        client = TestClient(create_app(start_scheduler=False))
        response = client.get(f"/api/competitions/{run_path.name}")

    assert response.status_code == 200
    status = response.json()["round_status"]
    assert status["phase"] in {"scheduled", "due", "complete", "running", "retrying", "failed"}
    assert status["max_attempts"] == arena_scheduler.MAX_ROUND_ATTEMPTS


def test_delete_competition_conflicts_while_round_running(tmp_path: Path) -> None:
    run_path = _init_test_run(tmp_path)
    lock = arena_scheduler.lock_for(run_path.name)
    asyncio.run(lock.acquire())
    try:
        with patch.object(arena_routes, "ARENA_ROOT", tmp_path):
            client = TestClient(create_app(start_scheduler=False))
            response = client.delete(f"/api/competitions/{run_path.name}")
    finally:
        lock.release()
        arena_scheduler.discard_lock(run_path.name)

    assert response.status_code == 409
    assert run_path.exists()


def test_delete_competition_removes_run_directory(tmp_path: Path) -> None:
    config = _config()
    states = {
        "baseline": initial_state(config, _snapshot().prices, agent_id="baseline", as_of="0"),
        "advisor_enabled": initial_state(
            config,
            _snapshot().prices,
            agent_id="advisor_enabled",
            as_of="0",
        ),
    }
    run_path = init_run(tmp_path, config, states)

    with patch.object(arena_routes, "ARENA_ROOT", tmp_path):
        client = TestClient(create_app(start_scheduler=False))
        response = client.delete(f"/api/competitions/{run_path.name}")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted", "run_id": run_path.name}
    assert not run_path.exists()
