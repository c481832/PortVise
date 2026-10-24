# PortVise

Self-hosted AI portfolio review. PortVise runs your holdings through a LangGraph multi-agent
pipeline — combining live market data, news search, and deterministic risk/regime analysis — and
returns a structured decision-support memo.

**Not financial advice.** LLM output can be wrong, market data can be stale, and the app ships
with no authentication. Do not expose it to untrusted users.

## What It Does

- Reviews a stock portfolio through eight specialized agents (see table below).
- Streams every agent step to a browser UI over server-sent events.
- Fetches live quotes and market context from third-party providers.
- Works with any OpenAI-compatible endpoint — cloud provider, gateway, or local model server.
- Also runs headless: CLI or Docker.

## Architecture

```text
START -> data ---------+--> risk ------+
  |                    +--> regime ----+
  |                    +--> theme -----+--> allocation --> manager --> END
  |                           ^        |
  +----> planner --> news ----+--------+
```

| Agent | Role |
| --- | --- |
| planner | Turns the portfolio into the news search plan |
| data | Fetches live prices and headlines from Yahoo Finance |
| news | Runs the planned searches and builds the market briefing |
| risk | Evaluates factor exposures, concentration risk, and scenario losses |
| regime | Classifies market regime and portfolio fit |
| theme | Reviews thematic alignment, crowding risk, and momentum conflicts |
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

Settings resolve in order: `config.toml` → `config.local.toml` → environment variables.
`config.toml` defines every key; `config.local.toml` may only override existing keys, so a typo
fails at startup. Env vars supported (mainly for Docker): `LLM_BASE_URL`, `LLM_MODEL`,
`LLM_API_KEY`, `SEARXNG_URL`, `TAVILY_API_KEY`, `FRED_API_KEY`, and `ADVISOR_LOG_FILE`.

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

### FRED

Series in `[fred].series_ids` (e.g. `BAA10Y`) come from the FRED API. Set `fred.api_key` in
`config.local.toml` or `FRED_API_KEY`. This product uses the FRED® API but is not endorsed or
certified by the Federal Reserve Bank of St. Louis.

## Docker

Packages the web app only — no Ollama, model weights, or SearXNG.

```bash
docker compose up --build          # http://localhost:7860
PORT=8080 docker compose up --build
```

Docker uses the baked-in `config.toml` unless you set override environment variables.

## Sharing with Cloudflare

Cloudflare Tunnel publishes the app without opening inbound ports, and Cloudflare Access only lets
in the email addresses you allow. The app has no login of its own, so never expose port 7860
directly; compose binds it to `127.0.0.1`.

1. Move your domain's DNS to Cloudflare (free plan; the registrar stays the same).
2. In Zero Trust → Networks → Tunnels, create a `cloudflared` tunnel and copy its token.
3. Add a public hostname to the tunnel, e.g. `advisor.example.com` → `http://portfolio-advisor:7860`.
4. In Zero Trust → Access → Applications, add a self-hosted app for that hostname with an
   Allow policy listing the invited emails. Create this before sharing the URL.
5. On the server, put the LLM/search keys plus these in `.env`, then start both containers:

```bash
ADVISOR_LOCK_SETTINGS=true
TUNNEL_TOKEN=...
```

```bash
docker compose --profile tunnel up -d --build
```

`ADVISOR_LOCK_SETTINGS=true` makes the settings panel read-only: saving, resetting and testing
endpoints return 403, as does starting a review with a custom endpoint or key. Without it, any
visitor could point the app at their own server and receive your saved API key. Change settings
through `.env` or `config.local.toml` on the server instead.

Everyone who gets in shares one review history and your LLM and search quotas.

## Headless Usage

CLI — `--progress` streams checkpoints to stderr, keeping structured JSON in the output file:

```bash
uv run advisor-review run request.json --output review-result.json --progress
uv run advisor-review run - --progress < request.json > review-result.json
uv run advisor-review schema input     # machine-readable request/response schemas
uv run advisor-review schema output
```

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

See `src/arena/config.example.json` for the competition config format, and `src/arena/config.toml`
for engine defaults (override with `src/arena/config.local.toml`).

### Result: July–October 2026

Two agents, identical prompt and model, same starting portfolio ($52,214.05) — one of them handed
a PortVise review each morning. Daily returns over the 65 arena rounds ending 2026-10-16:

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
| 2026-08-03 | +1.02% | +1.84% | +1.42% |
| 2026-08-04 | +0.79% | +1.58% | +1.80% |
| 2026-08-05 | +0.11% | -0.47% | -0.20% |
| 2026-08-06 | +0.80% | +0.27% | -0.16% |
| 2026-08-07 | +0.17% | +0.58% | +0.61% |
| 2026-08-10 | +0.60% | -0.28% | -0.02% |
| 2026-08-11 | -0.02% | -0.78% | -0.32% |
| 2026-08-12 | +0.20% | +0.30% | +0.24% |
| 2026-08-13 | +0.07% | -0.23% | +0.70% |
| 2026-08-14 | +0.10% | -1.04% | -0.20% |
| 2026-08-17 | -0.36% | -0.10% | -0.47% |
| 2026-08-18 | +0.47% | -0.59% | -0.67% |
| 2026-08-19 | -0.17% | -0.65% | +0.21% |
| 2026-08-20 | -0.28% | -0.59% | -0.85% |
| 2026-08-21 | -0.25% | +0.30% | +0.40% |
| 2026-08-24 | -0.11% | -0.45% | -0.28% |
| 2026-08-25 | -0.23% | +0.59% | +0.31% |
| 2026-08-26 | -0.21% | -0.08% | +0.02% |
| 2026-08-27 | +0.76% | +1.39% | +0.66% |
| 2026-08-28 | -0.15% | +0.05% | -0.22% |
| 2026-08-31 | +0.06% | -0.61% | -0.30% |
| 2026-09-01 | -0.08% | -0.34% | -0.68% |
| 2026-09-02 | +0.15% | +0.56% | +0.45% |
| 2026-09-03 | +0.56% | +0.93% | +1.04% |
| 2026-09-04 | -0.48% | -0.25% | -0.38% |
| 2026-09-08 | -0.09% | -0.13% | -0.54% |
| 2026-09-09 | +0.35% | +0.32% | -0.46% |
| 2026-09-10 | -0.19% | -0.43% | -0.60% |
| 2026-09-11 | +0.74% | +0.64% | +0.83% |
| 2026-09-14 | -0.30% | -0.38% | -0.44% |
| 2026-09-15 | +0.30% | -0.06% | -0.44% |
| 2026-09-16 | -0.69% | -0.30% | -0.44% |
| 2026-09-17 | +0.96% | +0.97% | +1.14% |
| 2026-09-18 | +0.13% | +0.24% | -0.15% |
| 2026-09-21 | +1.38% | +1.85% | +1.57% |
| 2026-09-22 | -0.54% | -0.26% | -0.01% |
| 2026-09-23 | -0.36% | -0.99% | -0.73% |
| 2026-09-24 | +0.48% | +0.51% | -0.08% |
| 2026-09-25 | +0.46% | +0.31% | +0.54% |
| 2026-09-28 | -0.87% | -1.33% | -0.74% |
| 2026-09-29 | -0.06% | +0.27% | -0.18% |
| 2026-09-30 | +0.05% | -0.16% | -0.23% |
| 2026-10-01 | +0.12% | -0.12% | +0.20% |
| 2026-10-02 | +0.82% | +1.17% | +0.74% |
| 2026-10-05 | +0.56% | +0.83% | +0.67% |
| 2026-10-06 | +0.68% | +0.93% | +0.55% |
| 2026-10-07 | -0.18% | +0.00% | -0.23% |
| 2026-10-08 | -0.48% | -1.56% | -0.42% |
| 2026-10-09 | +0.50% | +0.74% | +0.59% |
| 2026-10-12 | -0.20% | +0.03% | -0.06% |
| 2026-10-13 | -0.06% | +0.49% | -0.01% |
| 2026-10-14 | -0.35% | -1.32% | -1.07% |
| 2026-10-15 | -0.27% | -0.07% | +0.27% |
| 2026-10-16 | -0.28% | -1.00% | -1.11% |
| **Cumulative** | **+8.80%** | **+3.84%** | **+2.68%** |
| | +$4,592.91 | +$2,006.57 | +$1,400.73 |

One short paper-trading run on one portfolio — illustrative, not evidence of persistent
outperformance.

## Development

```bash
uv sync --group dev
uv run python run.py --reload
npm run advisor:dev             # frontend-only iteration (arena: npm run arena:dev)
```

Frontend source lives in `frontend/advisor/src` and `frontend/arena/src`, with code and styles
used by both in `frontend/shared`. They build into `src/advisor/web/ui` and `src/arena/web/ui`,
which is what FastAPI serves.

Quality gates:

```bash
npm run build                   # both frontends
uv run ruff check .
uv run ruff format --check .
uv run pyright
docker build .                  # only if you changed Docker packaging
```

A pre-push hook is available: `git config core.hooksPath .githooks`

## Project Structure

```text
src/
  advisor/                # Advisor backend
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
    web/ui/            # Built Advisor UI
  arena/               # Head-to-head trading arena backend
frontend/
  advisor/             # Vite source for the Advisor UI
  arena/               # Vite source for the Arena UI
```

## Limitations

- Review sessions live in server memory; saved reviews live in the browser. Neither is a durable
  record.
- No built-in authentication or authorization.
- Market data and news come from third-party services and can be delayed, incomplete, or missing.
- LLM-generated analysis can be incorrect, incomplete, or misleading.

## License

MIT. See [LICENSE](LICENSE).
