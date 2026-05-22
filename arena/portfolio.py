from __future__ import annotations

from datetime import date

from arena.models import (
    AgentDecision,
    ArenaConfig,
    Holding,
    PortfolioState,
    Trade,
)
from port.config import config as global_config
from port.portfolio import Portfolio, Position


def equity_for(state: PortfolioState, prices: dict[str, float]) -> float:
    holdings_value = 0.0
    for ticker, holding in state.holdings.items():
        price = prices.get(ticker, state.last_prices.get(ticker, 0.0))
        holdings_value += holding.quantity * price
    return round(state.cash + holdings_value, global_config.arena.cash_round_decimals)


def weights_for(state: PortfolioState, prices: dict[str, float]) -> dict[str, float]:
    equity = equity_for(state, prices)
    if equity <= 0:
        return {}
    return {
        ticker: (holding.quantity * prices.get(ticker, state.last_prices.get(ticker, 0.0))) / equity
        for ticker, holding in state.holdings.items()
    }


def initial_state(
    config: ArenaConfig,
    prices: dict[str, float],
    *,
    agent_id: str,
    as_of: str,
) -> PortfolioState:
    holdings = {
        p.ticker: Holding(
            ticker=p.ticker,
            quantity=p.quantity,
            average_cost=p.entry_price,
        )
        for p in config.positions
        if p.quantity > 0
    }
    state = PortfolioState(
        agent_id=agent_id,
        as_of=as_of,
        cash=config.starting_cash,
        holdings=holdings,
        last_prices={k: v for k, v in prices.items() if v > 0},
        equity=0.0,
    )
    return state.model_copy(update={"equity": equity_for(state, prices)})


def _normalize_decision(
    decision: AgentDecision,
    config: ArenaConfig,
) -> tuple[dict[str, float], float, list[str]]:
    corrections: list[str] = []
    watchlist = set(config.watchlist)
    targets: dict[str, float] = {}
    for ticker, raw_weight in decision.target_weights.items():
        if ticker not in watchlist:
            corrections.append(f"Rejected unknown ticker {ticker}.")
            continue
        weight = max(0.0, float(raw_weight))
        if weight > config.max_position_weight:
            corrections.append(
                f"Clipped {ticker} from {weight:.4f} to max {config.max_position_weight:.4f}."
            )
            weight = config.max_position_weight
        if weight:
            targets[ticker] = weight

    cash_weight = max(config.min_cash_weight, min(1.0, float(decision.cash_weight)))
    total_risky = sum(targets.values())
    max_risky = max(0.0, 1.0 - cash_weight)
    if total_risky > max_risky and total_risky > 0:
        scale = max_risky / total_risky
        targets = {ticker: weight * scale for ticker, weight in targets.items()}
        corrections.append(f"Scaled target weights by {scale:.4f} to preserve cash constraint.")
    return targets, cash_weight, corrections


def apply_decision(
    state: PortfolioState,
    decision: AgentDecision,
    prices: dict[str, float],
    config: ArenaConfig,
    *,
    as_of: str,
) -> tuple[PortfolioState, list[Trade], list[str]]:
    targets, _cash_weight, corrections = _normalize_decision(decision, config)
    # bps = basis points; 1 bp = 1/10_000 (unit conversion, not magic).
    fee_rate = config.transaction_cost_bps / 10_000.0
    equity = equity_for(state, prices)
    cash = state.cash
    holdings = {ticker: holding.model_copy(deep=True) for ticker, holding in state.holdings.items()}
    trades: list[Trade] = []

    desired_values = {ticker: weight * equity for ticker, weight in targets.items()}
    tickers = sorted(set(holdings) | set(desired_values))
    diffs: dict[str, float] = {}
    for ticker in tickers:
        price = prices.get(ticker)
        if price is None or price <= 0:
            corrections.append(f"Skipped {ticker}; no valid price.")
            continue
        current = holdings.get(
            ticker,
            Holding(ticker=ticker, quantity=0.0, average_cost=0.0),
        )
        current_value = current.quantity * price
        diffs[ticker] = desired_values.get(ticker, 0.0) - current_value

    for ticker, diff in sorted(diffs.items(), key=lambda item: item[1]):
        if diff >= -config.min_trade_value:
            continue
        price = prices[ticker]
        holding = holdings.get(ticker)
        if holding is None:
            continue
        quantity = min(holding.quantity, abs(diff) / price)
        gross = quantity * price
        if gross < config.min_trade_value:
            continue
        cost = gross * fee_rate
        holding.quantity = max(0.0, holding.quantity - quantity)
        cash += gross - cost
        trades.append(
            Trade(
                ticker=ticker,
                side="sell",
                quantity=round(quantity, 8),
                price=round(price, 6),
                gross_value=round(gross, 6),
                transaction_cost=round(cost, 6),
            )
        )
        if holding.quantity <= global_config.arena.minimum_position_threshold:
            holdings.pop(ticker, None)

    for ticker, diff in sorted(diffs.items(), key=lambda item: item[1], reverse=True):
        if diff <= config.min_trade_value:
            continue
        price = prices[ticker]
        desired_quantity = diff / price
        affordable_quantity = cash / (price * (1.0 + fee_rate)) if price > 0 else 0.0
        quantity = min(desired_quantity, affordable_quantity)
        gross = quantity * price
        if gross < config.min_trade_value:
            if desired_quantity > 0:
                corrections.append(f"Skipped buy for {ticker}; insufficient cash after costs.")
            continue
        cost = gross * fee_rate
        cash -= gross + cost
        existing = holdings.get(ticker)
        if existing is None:
            holdings[ticker] = Holding(ticker=ticker, quantity=quantity, average_cost=price)
        else:
            old_value = existing.quantity * existing.average_cost
            new_quantity = existing.quantity + quantity
            existing.average_cost = (old_value + gross) / new_quantity if new_quantity else price
            existing.quantity = new_quantity
        trades.append(
            Trade(
                ticker=ticker,
                side="buy",
                quantity=round(quantity, 8),
                price=round(price, 6),
                gross_value=round(gross, 6),
                transaction_cost=round(cost, 6),
            )
        )

    new_state = PortfolioState(
        agent_id=state.agent_id,
        as_of=as_of,
        cash=round(max(0.0, cash), 6),
        holdings={
            ticker: h
            for ticker, h in sorted(holdings.items())
            if h.quantity > global_config.arena.minimum_position_threshold
        },
        last_prices={ticker: price for ticker, price in prices.items() if price > 0},
        equity=0.0,
    )
    return (
        new_state.model_copy(update={"equity": equity_for(new_state, prices)}),
        trades,
        corrections,
    )


def to_review_portfolio(
    state: PortfolioState,
    config: ArenaConfig,
    prices: dict[str, float],
    *,
    review_date: date,
) -> Portfolio:
    equity = equity_for(state, prices)
    weight_map = weights_for(state, prices)
    positions: list[Position] = []
    by_ticker = {p.ticker: p for p in config.positions}
    for ticker, holding in sorted(state.holdings.items()):
        price = prices.get(ticker, state.last_prices.get(ticker, holding.average_cost))
        template = by_ticker.get(ticker)
        positions.append(
            Position(
                ticker=ticker,
                name=template.name if template else ticker,
                weight=weight_map.get(ticker, 0.0),
                quantity=holding.quantity,
                sector=template.sector if template else "Unknown",
                entry_date=template.entry_date if template else review_date,
                entry_price=holding.average_cost or price,
                current_price=price,
                dividend=0.0,
                split=1.0,
                entry_thesis=template.entry_thesis if template else "Arena watchlist allocation",
                asset_class="equity",
                country="US",
                tags=[],
            )
        )
    cash_weight = state.cash / equity if equity > 0 else 1.0
    return Portfolio(
        name=f"{config.run_name}-{state.agent_id}",
        positions=positions,
        cash_weight=cash_weight,
        base_currency="USD",
        benchmark=config.benchmark,
        review_date=review_date,
        context_note=(
            "Arena paper-trading review. Recommend portfolio construction under the configured "
            "cash, watchlist, and position constraints."
        ),
    )
