# PortVise

PortVise is a self-hosted alpha for AI-assisted portfolio review. It combines portfolio
inputs, live market data, news search, and a LangGraph multi-agent pipeline into a structured
decision-support memo.

This project is not financial advice. LLM output can be wrong, market data can be stale or
unavailable, and the app is not designed for untrusted public multi-user deployment without
additional controls.

## What It Does

- Reviews a stock portfolio through specialized planner, data, news, risk, regime, theme,
  validation, and manager agents.
- Streams each agent step to a browser UI over server-sent events.
- Fetches live quotes and recent market context from third-party providers.
- Supports OpenAI-compatible model endpoints, including cloud providers and local gateways.
- Runs with `uv` for development or Docker for self-hosted app packaging.

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
| manager | Converts findings into prioritized action items |

## Quickstart: Cloud OpenAI-Compatible Endpoint

Requirements:

- Python 3.12 or newer
- Node.js 20 or newer if you are rebuilding frontend assets
- [uv](https://docs.astral.sh/uv/)
- An OpenAI-compatible chat completion endpoint and API key

Install dependencies:

```bash
uv sync
npm install
```

By default the app reads `config.toml`. For a persistent API key or other machine-local
overrides, write them to `config.local.toml`:

```toml
[llm]
base_url = "https://api.openai.com/v1"
model = "gpt-4.1-mini"
api_key = "your_api_key_here"
```

The API key field in the web UI is temporary and is not saved.

Start the app:

```bash
uv run python run.py
```

Open `http://localhost:7860`.

The same variables work with other OpenAI-compatible providers or gateways. The UI also exposes
per-run model and endpoint overrides from the model settings panel.

## Docker

Docker packages only the web app. It does not bundle Ollama, model weights, SearXNG, or any other
external provider.

```bash
docker compose up --build
```

Docker uses the baked-in `config.toml` unless you set override environment variables such as
`LLM_BASE_URL`, `LLM_MODEL`, or `LLM_API_KEY`.

Open `http://localhost:7860`.

To change the host port:

```bash
PORT=8080 docker compose up --build
```

## Advanced: Local Models

Local/Ollama-compatible endpoints are supported, but they require enough CPU/GPU and memory for
the models you choose. Configure the same OpenAI-compatible variables:

```env
LLM_BASE_URL=http://localhost:8003/v1
LLM_MODEL=Qwen3.5-9B-Q4_K_M.gguf
LLM_API_KEY=dummy
```

The web UI lets you assign different model names per agent while keeping a single
OpenAI-compatible endpoint.

## News Search

News search uses exactly one provider, selected by `search.provider` in `config.toml` (or
from the settings UI): `searxng` (self-hosted, the default) or `tavily` (API key). There is no
fallback chain — only the selected provider is queried.

```env
SEARXNG_URL=http://127.0.0.1:8888
TAVILY_API_KEY=
```

Pick the provider in **Model & endpoints → Search providers**, or set `provider` under
`[search]` in `config.toml`. The chosen provider must have its credential set: a reachable
`searxng_url` for SearXNG, or a `tavily_api_key` for Tavily.
The news research agent runs planned searches concurrently; tune the batch width with
`search.concurrent_requests` or `SEARCH_CONCURRENT_REQUESTS` if your provider needs stricter
rate limiting.

## API Endpoints

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/config` | GET | Effective model settings, excluding API keys |
| `/api/market/quote/{ticker}` | GET | Live quote for one symbol |
| `/api/review/start` | POST | Start a review and return `review_id` |
| `/api/review/{id}/stream` | GET | SSE stream of agent events |
| `/api/review/{id}/confirm` | POST | Resume graph after an interrupt |
| `/api/review/{id}/result` | GET | Final review state |
| `/api/review/{id}/status` | GET | Poll-based status check |

## Agent Usage

Local agents can run the full review workflow without opening the browser UI.

CLI:

```bash
uv run port-review run request.json --output review-result.json --progress
```

`--progress` streams agent checkpoints to stderr while keeping the final structured JSON in the
output file.

Stdin/stdout:

```bash
uv run port-review run - --progress < request.json > review-result.json
```

Print machine-readable schemas:

```bash
uv run port-review schema input
uv run port-review schema output
```

MCP server:

```bash
uv run python -m port.mcp_server
```

The MCP server exposes `run_portfolio_review`, which returns the final `manager_review` plus validation, risk, regime, theme, news, market-data, and run metadata. MCP clients that surface progress notifications can also show live agent checkpoints during long reviews. This is decision support only and is not financial advice.

## Development

Install dev dependencies:

```bash
uv sync --group dev
```

Run with hot reload:

```bash
uv run python run.py --reload
```

Frontend source lives in `frontend/advisor/src` and builds into `src/port/static`, which is what FastAPI serves:

```bash
npm run frontend:build
```

For frontend-only iteration:

```bash
npm run frontend:dev
```

Quality gates:

```bash
npm run frontend:build
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

If you change Docker packaging:

```bash
docker build .
```

A pre-push hook is available:

```bash
git config core.hooksPath .githooks
```

## Project Structure

```text
src/
  port/                # Portfolio Advisor backend
    config.py          # LLM settings and OpenAI-compatible client factory
    models.py          # Pydantic output models for all agents
    schemas/           # Domain-oriented schema import modules
    state.py           # GraphState TypedDict
    graph.py           # LangGraph StateGraph wiring
    portfolio.py       # Portfolio model and prompt rendering helpers
    prompts.py         # System prompts for all agents
    server.py          # Stable FastAPI app entrypoint
    web/               # FastAPI routes, session orchestration, SSE helpers
    agents/            # One file per agent
    tools/             # News and external-data tools
    runner/            # Deterministic analysis runners
    static/            # Built Advisor UI served by FastAPI
  arena/               # Standalone head-to-head trading arena backend
    web/static/        # Built Arena UI served by FastAPI
frontend/
  advisor/             # Vite source for the Advisor UI
  arena/               # Vite source for the Arena UI
  vite.advisor.config.js
  vite.arena.config.js
tests/                 # Unit and integration tests
```

## Current Limitations

- Review sessions are stored in server memory and are not durable records.
- Saved reviews in the UI are stored in the user's browser.
- There is no built-in authentication or authorization.
- The app should not be exposed to untrusted users without additional network and security
  controls.
- Market data and news are provided by third-party services and can be incomplete, delayed, stale,
  or unavailable.
- LLM-generated analysis can be incorrect, incomplete, or misleading.

## License

MIT. See [LICENSE](LICENSE).
