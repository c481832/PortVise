from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

from arena import cli
from arena.agents import run_advisor_enabled_agent, run_baseline_agent
from arena.leaderboard import build_leaderboard
from arena.models import (
    AgentDecision,
    AgentRoundResult,
    ArenaConfig,
    ArenaPosition,
    MarketSnapshot,
    RoundRecord,
)
from arena.portfolio import apply_decision, initial_state
from arena.state import init_run, save_round


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
        )

    assert decision == expected
    assert result_path.exists()
    assert advisor_cli.call_count == 1
    assert invoke.call_count == 1
    prompt = invoke.call_args.args[1][1].content
    assert "Reduce concentration" in prompt


def test_leaderboard_scores_agents_from_round_records(tmp_path: Path) -> None:
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

    assert rows[0].agent_id == "advisor_enabled"
    assert rows[0].rounds == 1


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
