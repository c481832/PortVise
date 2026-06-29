from __future__ import annotations

import json
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import cast

from langchain_core.messages import HumanMessage, SystemMessage

import port.config as port_config
from arena.models import AgentDecision, ArenaConfig, MarketSnapshot, PortfolioState
from arena.portfolio import to_review_portfolio, weights_for


def _shared_prompt(
    *,
    agent_id: str,
    config: ArenaConfig,
    state: PortfolioState,
    snapshot: MarketSnapshot,
    advisor_result: dict | None = None,
) -> list:
    current_weights = weights_for(state, snapshot.prices)
    payload = {
        "agent_id": agent_id,
        "objective": (
            "Construct the next paper portfolio using only the watchlist, cash constraints, "
            "price movement, and news in this bundle."
        ),
        "constraints": {
            "watchlist": config.watchlist,
            "benchmark": config.benchmark,
            "transaction_cost_bps": config.transaction_cost_bps,
            "max_position_weight": config.max_position_weight,
            "min_cash_weight": config.min_cash_weight,
            "min_trade_value": config.min_trade_value,
            "long_only": True,
        },
        "portfolio": {
            "cash": state.cash,
            "equity": state.equity,
            "holdings": {
                ticker: holding.model_dump(mode="json")
                for ticker, holding in state.holdings.items()
            },
            "current_weights": current_weights,
        },
        "market_snapshot": snapshot.model_dump(mode="json"),
        "advisor_result": advisor_result,
    }
    system = SystemMessage(
        content=(
            "You are a portfolio-construction agent in a controlled paper-trading arena. "
            "Return target weights, not trade orders. Use only tickers in the watchlist. "
            "Keep target weights plus cash_weight <= 1.0. Never claim certainty."
        )
    )
    human = HumanMessage(content=json.dumps(payload, ensure_ascii=False, indent=2))
    return [system, human]


def run_baseline_agent(
    config: ArenaConfig,
    state: PortfolioState,
    snapshot: MarketSnapshot,
) -> AgentDecision:
    return cast(
        AgentDecision,
        port_config.invoke_structured(
            AgentDecision,
            _shared_prompt(
                agent_id="baseline",
                config=config,
                state=state,
                snapshot=snapshot,
            ),
            agent="arena_baseline",
            use_agent_model=False,
            max_tokens=2048,
            temperature=0.1,
        ),
    )


def run_advisor_cli(
    *,
    request_path: Path,
    output_path: Path,
    timeout_seconds: int,
) -> None:
    cmd = [
        "uv",
        "run",
        "port-review",
        "run",
        str(request_path),
        "--output",
        str(output_path),
        "--progress",
        "--timeout-seconds",
        str(timeout_seconds),
    ]
    completed = subprocess.run(cmd, check=False, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "advisor CLI failed "
            f"(exit {completed.returncode}): {completed.stderr.strip() or completed.stdout.strip()}"
        )


def build_advisor_request(
    config: ArenaConfig,
    state: PortfolioState,
    snapshot: MarketSnapshot,
) -> dict:
    try:
        review_date = date.fromisoformat(snapshot.as_of[:10])
    except ValueError:
        try:
            review_date = datetime.strptime(snapshot.as_of[:8], "%Y%m%d").date()
        except ValueError:
            review_date = date.today()
    portfolio = to_review_portfolio(state, config, snapshot.prices, review_date=review_date)
    return {
        "portfolio": portfolio.model_dump(mode="json"),
        "corporate_actions": config.corporate_actions,
        "timeout_seconds": config.advisor_timeout_seconds,
    }


def run_advisor_enabled_agent(
    config: ArenaConfig,
    state: PortfolioState,
    snapshot: MarketSnapshot,
    *,
    work_dir: Path,
) -> tuple[AgentDecision, Path]:
    request_path = work_dir / "advisor-request.json"
    result_path = work_dir / "advisor-result.json"
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(
        json.dumps(build_advisor_request(config, state, snapshot), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    run_advisor_cli(
        request_path=request_path,
        output_path=result_path,
        timeout_seconds=config.advisor_timeout_seconds,
    )
    advisor_result = json.loads(result_path.read_text(encoding="utf-8"))
    decision = cast(
        AgentDecision,
        port_config.invoke_structured(
            AgentDecision,
            _shared_prompt(
                agent_id="advisor_enabled",
                config=config,
                state=state,
                snapshot=snapshot,
                advisor_result={
                    "manager_review": advisor_result.get("manager_review"),
                    "validation_review": advisor_result.get("validation_review"),
                    "risk_review": advisor_result.get("risk_review"),
                    "regime_review": advisor_result.get("regime_review"),
                    "theme_review": advisor_result.get("theme_review"),
                    "news_review": advisor_result.get("news_review"),
                    "market_data": advisor_result.get("market_data"),
                    "warnings": advisor_result.get("warnings", []),
                },
            ),
            agent="arena_advisor_enabled",
            use_agent_model=False,
            max_tokens=2048,
            temperature=0.1,
        ),
    )
    return decision, result_path
