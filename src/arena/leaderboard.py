from __future__ import annotations

from math import sqrt
from pathlib import Path

from arena.models import LeaderboardRow, PortfolioState, RoundRecord
from arena.state import AGENTS, load_initial_snapshot, load_rounds, load_states


def _max_drawdown(values: list[float]) -> float:
    if not values:
        return 0.0
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return worst


def _volatility(values: list[float]) -> float:
    returns = [
        values[idx] / values[idx - 1] - 1.0 for idx in range(1, len(values)) if values[idx - 1] > 0
    ]
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((item - mean) ** 2 for item in returns) / (len(returns) - 1)
    return sqrt(variance) * sqrt(252.0)


def _benchmark_return(initial_price: float | None, rounds: list[RoundRecord]) -> float:
    prices = [initial_price] if initial_price else []
    prices += [r.snapshot.benchmark_price for r in rounds if r.snapshot.benchmark_price]
    if len(prices) < 2 or not prices[0]:
        return 0.0
    return float(prices[-1] / prices[0] - 1.0)


def _turnover_and_costs(agent_id: str, rounds: list[RoundRecord]) -> tuple[float, float]:
    turnover = 0.0
    costs = 0.0
    for record in rounds:
        result = record.results.get(agent_id)
        if result is None or result.state.equity <= 0:
            continue
        traded = sum(trade.gross_value for trade in result.trades)
        turnover += traded / result.state.equity
        costs += sum(trade.transaction_cost for trade in result.trades)
    return turnover, costs


def _cash_drag(states: list[PortfolioState]) -> float:
    weights = [state.cash / state.equity for state in states if state.equity > 0]
    return sum(weights) / len(weights) if weights else 0.0


def build_leaderboard(path: Path) -> list[LeaderboardRow]:
    rounds = load_rounds(path)
    initial = load_initial_snapshot(path)
    benchmark_return = _benchmark_return(initial.benchmark_price if initial else None, rounds)
    rows: list[LeaderboardRow] = []
    for agent_id in AGENTS:
        states = load_states(path, agent_id)
        values = [state.equity for state in states]
        cumulative = 0.0 if len(values) < 2 or values[0] <= 0 else values[-1] / values[0] - 1.0
        drawdown = _max_drawdown(values)
        vol = _volatility(values)
        turnover, costs = _turnover_and_costs(agent_id, rounds)
        excess = cumulative - benchmark_return
        score = excess - 0.5 * abs(drawdown) - 0.1 * turnover
        rows.append(
            LeaderboardRow(
                agent_id=agent_id,
                rounds=len(rounds),
                cumulative_return=cumulative,
                excess_return_vs_benchmark=excess,
                max_drawdown=drawdown,
                realized_volatility=vol,
                turnover=turnover,
                transaction_costs=costs,
                cash_drag=_cash_drag(states),
                score=score,
            )
        )
    return sorted(rows, key=lambda row: row.score, reverse=True)
