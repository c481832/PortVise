# Portfolio Advisor

A multi-agent portfolio analysis system built with [LangGraph](https://github.com/langchain-ai/langgraph). Seven specialized agents review a stock portfolio and stream results to a web UI over SSE.

## Architecture

```
START → plan_agent ──(interrupt)──> data_agent → news_agent
                                                     │
                                       ┌─────────────┼─────────────┐
                                  risk_agent    regime_agent   theme_agent   (parallel)
                                       └─────────────┼─────────────┘
                                               validation_agent
                                                     │
                                               planner_agent → END
```

| Agent | Role |
|-------|------|
| **plan** | Human-in-the-loop portfolio confirmation via `interrupt()` |
| **data** | Fetches live prices and headlines from Yahoo Finance |
| **news** | Macro and market context briefing |
| **risk** | Factor exposures, concentration risk, scenario losses |
| **regime** | Market regime classification and portfolio fit scoring |
| **theme** | Thematic alignment, crowding risk, momentum conflicts |
| **validation** | Cross-checks the three parallel results for contradictions |
| **planner** | Converts findings into prioritized action items |

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
# Install dependencies
uv sync

# Copy and edit environment config (optional — defaults work for local LLMs)
cp .env.example .env

# Start the server (default port 7000)
uv run python run.py
```

Open `http://localhost:7000` in a browser.

## LLM Configuration

Both models run locally via Ollama-compatible endpoints. Configure via `.env` or environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `LLM_BASE_URL` | `http://localhost:8003/v1` | Reasoning model endpoint |
| `LLM_MODEL` | `Qwen3.5-35B-A3B-UD-Q6_K_S.gguf` | Reasoning model name |
| `FAST_LLM_BASE_URL` | `http://localhost:8000/v1` | Fast model endpoint |
| `FAST_LLM_MODEL` | `Qwen2.5-7B-Instruct-Q4_K_M.gguf` | Fast model name |
| `LLM_API_KEY` | `dummy` | API key (not needed for local models) |

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/review/start` | POST | Start a new review; returns `review_id` |
| `/api/review/{id}/stream` | GET | SSE stream of agent events |
| `/api/review/{id}/confirm` | POST | Resume graph after plan-agent interrupt |
| `/api/review/{id}/result` | GET | Final `PlannerReview` when complete |
| `/api/review/{id}/status` | GET | Poll-based status check |

## Development

```bash
# Install dev dependencies
uv sync --group dev

# Run with hot-reload
uv run python run.py --reload --port 7000

# Lint and format
uv run ruff check --fix .
uv run ruff format .

# Type check
uv run pyright

# Run tests
uv run pytest

# Set up pre-commit hooks (one-time)
uv run pre-commit install
```

## Project Structure

```
port/
  config.py          # LLM settings (pydantic-settings BaseSettings)
  models.py          # Pydantic output models for all agents
  state.py           # GraphState TypedDict
  graph.py           # LangGraph StateGraph wiring
  portfolio.py       # Portfolio model + text rendering helpers
  prompts.py         # System prompts for all agents
  server.py          # FastAPI app with SSE streaming
  agents/
    _base.py         # Shared prompt builder for parallel agents
    plan.py          # Human-in-the-loop portfolio confirmation
    data.py          # Yahoo Finance data fetcher
    news.py          # Market context agent
    risk.py          # Risk analysis agent
    regime.py        # Regime classification agent
    theme.py         # Theme alignment agent
    validation.py    # Cross-validation agent
    planner.py       # Action planning agent
  static/            # Web UI (HTML/CSS/JS)
tests/
  test_models.py     # Normalizer + model validator tests
  test_portfolio.py  # Text rendering tests
  test_settings.py   # Settings env var loading tests
  test_data.py       # Data helper tests
```
