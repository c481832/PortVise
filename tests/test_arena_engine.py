from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from arena.csv_import import parse_positions_csv
from arena.models import AgentDecision, ArenaConfig, ArenaPosition, Trade
from arena.portfolio import apply_decision, initial_state
from arena.scheduler import is_due
from arena.state import append_ledger, load_ledger, load_position_timeline, save_state

PRICES = {"AAPL": 100.0, "MSFT": 200.0, "NVDA": 50.0, "SPY": 500.0}


def _config(**overrides) -> ArenaConfig:
    base = {
        "run_name": "t",
        "starting_cash": 1_000.0,
        "positions": [
            ArenaPosition(
                ticker="AAPL",
                name="Apple",
                quantity=10.0,
                sector="Tech",
                entry_date=date(2025, 1, 2),
                entry_price=80.0,
                entry_thesis="x",
            )
        ],
        "watchlist": ["AAPL", "MSFT", "NVDA", "SPY"],
        "benchmark": "SPY",
        "transaction_cost_bps": 0.0,
        "max_position_weight": 1.0,
        "max_holdings": 3,
        "cash_return_annual_pct": 0.0,
        "min_trade_value": 1.0,
        "min_cash_weight": 0.0,
        "corporate_actions": "off",
    }
    base.update(overrides)
    return ArenaConfig(**base)


# ── cash interest ────────────────────────────────────────────────────────────
def test_cash_interest_accrues_on_idle_cash() -> None:
    config = _config(cash_return_annual_pct=25.2)  # 25.2 / 252 = 0.1% per market day
    state = initial_state(config, PRICES, agent_id="baseline", as_of="0")
    # Hold everything in cash by selling out (target nothing, all cash).
    decision = AgentDecision(target_weights={}, cash_weight=1.0)
    next_state, _trades, _corr = apply_decision(state, decision, PRICES, config, as_of="1")
    # Interest accrues on pre-trade cash (1000 * 1.001 = 1001), plus 1000 proceeds from selling
    # 10 AAPL @100 with no fees -> 2001.
    assert next_state.cash == pytest.approx(2001.0, rel=1e-6)


# ── holdings cap ─────────────────────────────────────────────────────────────
def test_holdings_cap_drops_lowest_weight_targets() -> None:
    config = _config(max_holdings=2, starting_cash=10_000.0, positions=[])
    state = initial_state(config, PRICES, agent_id="baseline", as_of="0")
    decision = AgentDecision(
        target_weights={"AAPL": 0.4, "MSFT": 0.3, "NVDA": 0.1}, cash_weight=0.0
    )
    next_state, _trades, corrections = apply_decision(state, decision, PRICES, config, as_of="1")
    assert "NVDA" not in next_state.holdings  # lowest target dropped
    assert any("max_holdings=2" in c for c in corrections)
    assert len(next_state.holdings) <= 2


# ── per-trade realized P&L + cash_after ──────────────────────────────────────
def test_sell_records_realized_pnl_and_cash_after() -> None:
    config = _config(starting_cash=0.0)  # entry cost 80, sell at 100
    state = initial_state(config, PRICES, agent_id="baseline", as_of="0")
    decision = AgentDecision(target_weights={}, cash_weight=1.0)
    next_state, trades, _corr = apply_decision(state, decision, PRICES, config, as_of="1")
    sells = [t for t in trades if t.side == "sell" and t.ticker == "AAPL"]
    assert sells
    sell = sells[0]
    # 10 shares * (100 - 80) = 200 realized; no fees configured.
    assert sell.realized_pnl == pytest.approx(200.0)
    assert sell.cash_after == pytest.approx(next_state.cash)


def test_buy_has_zero_realized_pnl() -> None:
    config = _config(starting_cash=1_000.0, positions=[])
    state = initial_state(config, PRICES, agent_id="baseline", as_of="0")
    decision = AgentDecision(target_weights={"MSFT": 0.5}, cash_weight=0.5)
    _next, trades, _corr = apply_decision(state, decision, PRICES, config, as_of="1")
    buys = [t for t in trades if t.side == "buy"]
    assert buys and all(t.realized_pnl == 0.0 for t in buys)


# ── CSV import ───────────────────────────────────────────────────────────────
SAMPLE_CSV = (
    "ticker,name,sector,quantity,entry_date,entry_price,entry_thesis\n"
    "NVDA,Nvidia,Technology,25,2025-01-02,135.50,AI leader\n"
    "MSFT,Microsoft,Technology,30,2025-01-02,418.00,Cloud + AI\n"
)


def test_parse_positions_csv_parses_rows() -> None:
    positions = parse_positions_csv(SAMPLE_CSV)
    assert [p.ticker for p in positions] == ["NVDA", "MSFT"]
    assert positions[0].entry_price == 135.50


def test_parse_positions_csv_missing_column_raises() -> None:
    bad = "ticker,name,sector,quantity,entry_date,entry_thesis\nNVDA,Nvidia,Tech,25,2025-01-02,x\n"
    with pytest.raises(ValueError, match="entry_price"):
        parse_positions_csv(bad)


def test_parse_positions_csv_bad_number_raises() -> None:
    bad = (
        "ticker,name,sector,quantity,entry_date,entry_price,entry_thesis\n"
        "NVDA,Nvidia,Tech,notanumber,2025-01-02,10,x\n"
    )
    with pytest.raises(ValueError, match="row 2"):
        parse_positions_csv(bad)


# ── ledger ───────────────────────────────────────────────────────────────────
def _trade(ticker: str) -> Trade:
    return Trade(
        ticker=ticker,
        side="buy",
        quantity=1.0,
        price=10.0,
        gross_value=10.0,
        transaction_cost=0.0,
        realized_pnl=0.0,
        cash_after=5.0,
    )


def test_ledger_append_and_idempotent_same_day(tmp_path: Path) -> None:
    append_ledger(tmp_path, "baseline", "20260101", [_trade("AAPL")])
    append_ledger(tmp_path, "baseline", "20260102", [_trade("MSFT")])
    assert [e.ticker for e in load_ledger(tmp_path, "baseline")] == ["AAPL", "MSFT"]
    # Re-running 20260102 replaces, not duplicates.
    append_ledger(tmp_path, "baseline", "20260102", [_trade("NVDA")])
    entries = load_ledger(tmp_path, "baseline")
    assert [e.ticker for e in entries] == ["AAPL", "NVDA"]


def test_position_timeline_reports_value_and_pnl(tmp_path: Path) -> None:
    config = _config()
    state = initial_state(config, PRICES, agent_id="baseline", as_of="20260101")
    save_state(tmp_path, "baseline", state)
    timeline = load_position_timeline(tmp_path, "baseline")
    assert len(timeline) == 1
    aapl = timeline[0]["positions"]["AAPL"]
    assert aapl["mkt_value"] == pytest.approx(1_000.0)  # 10 * 100
    assert aapl["unrealized_pnl"] == pytest.approx(200.0)  # 10 * (100 - 80)


# ── scheduler ────────────────────────────────────────────────────────────────
def test_is_due_true_after_trade_time_on_weekday() -> None:
    config = _config(trade_time="16:00", timezone="America/New_York")
    ny = ZoneInfo("America/New_York")
    # Wednesday 2026-06-10 at 16:30 NY → after trade_time, not yet run.
    now = datetime(2026, 6, 10, 16, 30, tzinfo=ny).astimezone(ZoneInfo("UTC"))
    assert is_due(now, config, last_round_date=None) is True


def test_is_due_false_before_trade_time() -> None:
    config = _config(trade_time="16:00", timezone="America/New_York")
    ny = ZoneInfo("America/New_York")
    now = datetime(2026, 6, 10, 9, 30, tzinfo=ny).astimezone(ZoneInfo("UTC"))
    assert is_due(now, config, last_round_date=None) is False


def test_is_due_false_on_weekend() -> None:
    config = _config(trade_time="16:00", timezone="America/New_York")
    ny = ZoneInfo("America/New_York")
    now = datetime(2026, 6, 13, 17, 0, tzinfo=ny).astimezone(ZoneInfo("UTC"))  # Saturday
    assert is_due(now, config, last_round_date=None) is False


def test_is_due_false_if_already_ran_today() -> None:
    config = _config(trade_time="16:00", timezone="America/New_York")
    ny = ZoneInfo("America/New_York")
    now = datetime(2026, 6, 10, 16, 30, tzinfo=ny).astimezone(ZoneInfo("UTC"))
    assert is_due(now, config, last_round_date="20260610") is False
