from __future__ import annotations

from pathlib import Path

from arena.run_store import AGENTS, load_initial_snapshot, load_rounds, load_states
from arena.schemas import LeaderboardRow, MarketSnapshot, PortfolioState, RoundRecord


def compute_cumulative_return(values: list[float]) -> float:
    if len(values) < 2 or values[0] <= 0:
        return 0.0
    return values[-1] / values[0] - 1.0


def compute_max_drawdown(values: list[float]) -> float:
    if not values:
        return 0.0
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return worst


def compute_benchmark_return(initial_price: float | None, rounds: list[RoundRecord]) -> float:
    prices = [initial_price] if initial_price else []
    prices += [r.snapshot.benchmark_price for r in rounds if r.snapshot.benchmark_price]
    if len(prices) < 2 or not prices[0]:
        return 0.0
    return float(prices[-1] / prices[0] - 1.0)


def compute_turnover(agent_id: str, rounds: list[RoundRecord]) -> float:
    turnover = 0.0
    for record in rounds:
        result = record.results.get(agent_id)
        if result is None or result.state.equity <= 0:
            continue
        traded = sum(trade.gross_value for trade in result.trades)
        turnover += traded / result.state.equity
    return turnover


def load_leaderboard(path: Path) -> list[LeaderboardRow]:
    states = {agent_id: load_states(path, agent_id) for agent_id in AGENTS}
    return build_leaderboard(load_rounds(path), states, load_initial_snapshot(path))


def build_leaderboard(
    rounds: list[RoundRecord],
    states_by_agent: dict[str, list[PortfolioState]],
    initial: MarketSnapshot | None,
) -> list[LeaderboardRow]:
    initial_price = initial.benchmark_price if initial else None
    benchmark_return = compute_benchmark_return(initial_price, rounds)
    rows: list[LeaderboardRow] = []
    for agent_id, states in states_by_agent.items():
        values = [state.equity for state in states]
        cumulative = compute_cumulative_return(values)
        rows.append(
            LeaderboardRow(
                agent_id=agent_id,
                excess_return_vs_benchmark=cumulative - benchmark_return,
                max_drawdown=compute_max_drawdown(values),
                turnover=compute_turnover(agent_id, rounds),
            )
        )
    return rows
