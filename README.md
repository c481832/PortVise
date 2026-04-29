# Portfolio Advisor

Portfolio Advisor is a self-hosted alpha for AI-assisted portfolio review. It combines portfolio
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
START -> planner -> data -> news
                         |
              +----------+----------+
              |          |          |
             risk      regime      theme
              +----------+----------+
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
- [uv](https://docs.astral.sh/uv/)
- An OpenAI-compatible chat completion endpoint and API key

Install dependencies:

```bash
uv sync
```

Create local configuration:

```bash
cp .env.example .env
```

Edit `.env` with your provider:

```env
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4.1-mini
FAST_LLM_BASE_URL=https://api.openai.com/v1
FAST_LLM_MODEL=gpt-4.1-mini
LLM_API_KEY=your_api_key_here
```

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
cp .env.example .env
# edit .env with your model endpoint and API key
docker compose up --build
```

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
LLM_MODEL=Qwen3.5-35B-A3B-UD-Q6_K_S.gguf
FAST_LLM_BASE_URL=http://localhost:8000/v1
FAST_LLM_MODEL=Qwen2.5-7B-Instruct-Q4_K_M.gguf
LLM_API_KEY=dummy
```

The "fast" model is used for latency-sensitive planner and tool steps. The primary model is used
for deeper analysis agents.

## Optional News Search

Portfolio Advisor uses Tavily when `TAVILY_API_KEY` is set. If it is unset, the app falls back to
DuckDuckGo news search, then optional local SearXNG if configured.

```env
TAVILY_API_KEY=
SEARXNG_URL=http://127.0.0.1:8888
```

Set `SEARXNG_URL=` to disable the SearXNG fallback.

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
uv run port-review run request.json --output review-result.json
```

Stdin/stdout:

```bash
uv run port-review run - < request.json > review-result.json
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

The MCP server exposes `run_portfolio_review`, which returns the final `manager_review` plus validation, risk, regime, theme, news, market-data, and run metadata. This is decision support only and is not financial advice.

## Development

Install dev dependencies:

```bash
uv sync --group dev
```

Run with hot reload:

```bash
uv run python run.py --reload
```

Quality gates:

```bash
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
port/
  config.py          # LLM settings and OpenAI-compatible client factory
  models.py          # Pydantic output models for all agents
  state.py           # GraphState TypedDict
  graph.py           # LangGraph StateGraph wiring
  portfolio.py       # Portfolio model and prompt rendering helpers
  prompts.py         # System prompts for all agents
  server.py          # FastAPI app with SSE streaming
  agents/            # One file per agent
  tools/             # News and external-data tools
  runner/            # Deterministic analysis runners
  static/            # Browser UI
tests/               # Unit and integration tests
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
