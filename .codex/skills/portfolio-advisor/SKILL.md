---
name: portfolio-advisor
description: Use when a local agent needs to review a stock portfolio through this repository's Portfolio Advisor workflow and consume structured decision-support output.
---

# Portfolio Advisor Agent Usage

Use this skill when the user asks for an AI-assisted portfolio review, concentration/risk review, regime fit review, thematic review, or action plan based on a portfolio.

This tool provides decision support only. Do not present the output as financial advice.

## Preferred Path

If the `run_portfolio_review` MCP tool is available, call it with:

- `portfolio`: object matching `port.portfolio.Portfolio`
- `locale`: optional, default `en`
- `corporate_actions`: `best_effort`, `strict`, or `off`
- `timeout_seconds`: optional, default `1800`; `0` disables the explicit runner timeout
- `llm`: optional model overrides

Read `manager_review` first. Use `validation_review`, `risk_review`, `regime_review`, `theme_review`, `news_review`, and `market_data` to explain or audit the result.

## CLI Fallback

When MCP is unavailable, write the request JSON to a file and run:

```bash
uv run port-review run request.json --output review-result.json
```

For stdin/stdout:

```bash
uv run port-review run - < request.json > review-result.json
```

Print schemas with:

```bash
uv run port-review schema input
uv run port-review schema output
```

## Minimal Request

```json
{
  "portfolio": {
    "name": "Example",
    "positions": [
      {
        "ticker": "AAPL",
        "name": "Apple",
        "weight": 0.1,
        "sector": "Technology",
        "entry_date": "2023-01-01",
        "entry_price": 150.0,
        "current_price": 180.0,
        "entry_thesis": "Services growth"
      }
    ],
    "cash_weight": 0.9,
    "benchmark": "SPY",
    "context_note": "Review concentration and downside risks."
  },
  "corporate_actions": "best_effort"
}
```
