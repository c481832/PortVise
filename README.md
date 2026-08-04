# PortVise

Self-hosted AI portfolio review. PortVise runs your holdings through a LangGraph multi-agent
pipeline — combining live market data, news search, and deterministic risk/regime analysis — and
returns a structured decision-support memo.

**Not financial advice.** LLM output can be wrong, market data can be stale, and the app ships
with no authentication. Do not expose it to untrusted users.

## What It Does

- Reviews a stock portfolio through nine specialized agents (see table below).
- Streams every agent step to a browser UI over server-sent events.
- Fetches live quotes and market context from third-party providers.
- Works with any OpenAI-compatible endpoint — cloud provider, gateway, or local model server.
- Also runs headless: CLI, MCP server, or Docker.

## Architecture

```text
START -> planner -> news
  |                  |
  v                  v
 data ------------> theme
  |                  |
  +----> risk        |
  +----> regime      |
  +------------------+
            |
      validation
            |
       allocation
            |
       manager -> END
```

| Agent | Role |
| --- | --- |
| planner | Builds the review plan and search priorities |
| data | Fetches live prices and headlines from Yahoo Finance |
| news | Builds macro and market context |
| risk | Evaluates factor exposures, concentration risk, and scenario losses |
| regime | Classifies market regime and portfolio fit |
| theme | Reviews thematic alignment, crowding risk, and momentum conflicts |
| validation | Cross-checks parallel agent outputs for contradictions |
| allocation | Enforces minimum invested capital, maximum cash, and drawdown-budget gates |
| manager | Converts findings into prioritized action items |

## Quickstart

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), an OpenAI-compatible chat endpoint
and API key. Node.js 20+ only if you rebuild frontend assets.

```bash
uv sync
npm install
```

Put your credentials in `config.local.toml` (gitignored, overrides `config.toml`):

```toml
[llm]
base_url = "https://api.openai.com/v1"
model = "gpt-4.1-mini"
api_key = "your_api_key_here"
```

```bash
uv run python run.py
```

Open `http://localhost:7860`. The API key field in the web UI is temporary and is not saved.

### Configuration

Settings resolve in order: `config.toml` → `config.local.toml` → environment variables. The env
overrides cover the common knobs, including `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`,
`SEARXNG_URL`, and `TAVILY_API_KEY`.

Local model servers work the same way — point `base_url` at your gateway:

```env
LLM_BASE_URL=http://localhost:8003/v1
LLM_MODEL=Qwen3.5-9B-Q4_K_M.gguf
LLM_API_KEY=dummy
```

The **Model & endpoints** panel in the UI can override the model and endpoint per run, and assign
a different model per agent behind a single endpoint.

### News search

Exactly one provider is queried — no fallback chain. Select it with `search.provider` in
`config.toml` or in **Model & endpoints → Search providers**:

- `searxng` (default, self-hosted) — requires a reachable `searxng_url`
- `tavily` — requires `tavily_api_key`

The news agent runs planned searches concurrently; lower `search.concurrent_requests` if your
provider rate-limits.

## Docker

Packages the web app only — no Ollama, model weights, or SearXNG.

```bash
docker compose up --build          # http://localhost:7860
PORT=8080 docker compose up --build
```

Docker uses the baked-in `config.toml` unless you set override environment variables.

## Headless Usage

CLI — `--progress` streams checkpoints to stderr, keeping structured JSON in the output file:

```bash
uv run port-review run request.json --output review-result.json --progress
uv run port-review run - --progress < request.json > review-result.json
uv run port-review schema input     # machine-readable request/response schemas
uv run port-review schema output
```

MCP server:

```bash
uv run python -m port.mcp_server
```

It exposes `run_portfolio_review`, returning the final `manager_review` plus allocation,
validation, risk, regime, theme, news, market-data, and run metadata. Treat `allocation_review`
as the authoritative source for invested/cash thresholds and deployment requirements — the
manager's prose is a synthesis of it. Clients that support progress notifications see live agent
checkpoints during long reviews.

### HTTP API

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/config` | GET | Effective model settings, excluding API keys |
| `/api/market/quote/{ticker}` | GET | Live quote for one symbol |
| `/api/review/start` | POST | Start a review and return `review_id` |
| `/api/review/{id}/stream` | GET | SSE stream of agent events |
| `/api/review/{id}/confirm` | POST | Resume graph after an interrupt |
| `/api/review/{id}/result` | GET | Final review state |
| `/api/review/{id}/status` | GET | Poll-based status check |

## Arena

A standalone head-to-head trading competition that runs advisor configurations against each other
on simulated capital, marked daily at the close.

```bash
uv run arena init --config my-competition.json   # prints the new run id
uv run arena serve                               # web UI, default http://localhost:8800
uv run arena run-round --run-id <id>             # run one round now
uv run arena rank --run-id <id>                  # print the leaderboard
uv run arena show --run-id <id>                  # config, states, and leaderboard
```

See `src/arena/config.example.json` for the competition config format, and the `[arena]` section
of `config.toml` for engine settings.

### Result: July 2026

Two agents, identical prompt and model, same starting portfolio ($52,214.05) — one of them handed
a PortVise review each morning. Daily returns over the 11 trading days ending 2026-07-31:

| Date | With PortVise | Baseline | SPY |
| --- | ---: | ---: | ---: |
| 2026-07-18 | -0.03% | -0.06% | +0.00% |
| 2026-07-20 | +0.01% | -0.13% | -0.16% |
| 2026-07-21 | +0.63% | +0.42% | +0.83% |
| 2026-07-22 | +0.35% | +0.17% | -0.12% |
| 2026-07-23 | -0.29% | -1.90% | -1.23% |
| 2026-07-24 | +0.43% | -0.20% | +0.10% |
| 2026-07-27 | -0.22% | -0.28% | +0.03% |
| 2026-07-28 | +0.12% | -0.11% | +0.24% |
| 2026-07-29 | -0.58% | -1.07% | -1.53% |
| 2026-07-30 | +2.36% | +2.44% | +1.67% |
| 2026-07-31 | -0.39% | +1.55% | +0.72% |
| **Cumulative** | **+2.38%** | **+0.77%** | **+0.50%** |
| | +$1,243.44 | +$402.91 | +$262.72 |

One short paper-trading run on one portfolio — illustrative, not evidence of persistent
outperformance.

## Development

```bash
uv sync --group dev
uv run python run.py --reload
npm run frontend:dev            # frontend-only iteration
```

Frontend source lives in `frontend/advisor/src` and `frontend/arena/src`, building into
`src/port/static` and `src/arena/web/static`, which is what FastAPI serves.

Quality gates:

```bash
npm run frontend:build
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
docker build .                  # only if you changed Docker packaging
```

A pre-push hook is available: `git config core.hooksPath .githooks`

## Project Structure

```text
src/
  port/                # Advisor backend
    config.py          # Config loading and OpenAI-compatible client factory
    models.py          # Pydantic output models for all agents
    graph.py           # LangGraph StateGraph wiring
    state.py           # GraphState TypedDict
    prompts.py         # System prompts for all agents
    portfolio.py       # Portfolio model and prompt rendering
    server.py          # FastAPI app entrypoint
    web/               # Routes, session orchestration, SSE helpers
    agents/            # One file per agent
    tools/             # News and external-data tools
    runner/            # Deterministic analysis runners
    schemas/           # Domain-oriented schema import modules
    static/            # Built Advisor UI
  arena/               # Head-to-head trading arena backend
frontend/
  advisor/             # Vite source for the Advisor UI
  arena/               # Vite source for the Arena UI
tests/
```

## Limitations

- Review sessions live in server memory; saved reviews live in the browser. Neither is a durable
  record.
- No built-in authentication or authorization.
- Market data and news come from third-party services and can be delayed, incomplete, or missing.
- LLM-generated analysis can be incorrect, incomplete, or misleading.

## License

MIT. See [LICENSE](LICENSE).
