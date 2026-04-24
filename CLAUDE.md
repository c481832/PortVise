# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install / sync dependencies (creates .venv automatically)
uv sync

# Start the server (default port 7860)
uv run python run.py

# Dev mode with hot-reload
uv run python run.py --reload --port 7860

# Add a new dependency
uv add <package>
```

Run tests with `uv run pytest`.

## Before pushing

Always run the full CI check suite locally before pushing:

```bash
uv run ruff check .          # lint
uv run ruff format --check . # format
uv run pytest                # tests (≥60% coverage required)
```

A pre-push hook is provided in `.githooks/pre-push` that runs these automatically.
Enable it once per clone:

```bash
git config core.hooksPath .githooks
```

This is especially important because the main branch receives direct pushes — a
broken push will fail CI and trigger the auto-merge back to dev, carrying the
breakage with it.

## Local overrides

Create `CLAUDE.local.md` (gitignored) for machine-specific notes, paths, or
personal preferences you don't want committed.

## Architecture

An 8-node LangGraph pipeline that analyses a stock portfolio and streams results to a web UI over SSE.

### Agent pipeline

```
START → planner_agent → data_agent → news_agent
                                          │
                          ┌─────────────┼─────────────┐
                     risk_agent  regime_agent  theme_agent   (parallel fan-out)
                          └─────────────┼─────────────┘
                                 validation_agent
                                       │
                                 manager_agent → END
```

- **planner_agent** — Pass-through; portfolio and goal (`context_note`) are set when the review starts.
- **data_agent** — Live prices and headlines (Yahoo Finance) before LLM agents.
- **news_agent** — Broad macro & news context for downstream agents.
- **risk / regime / theme agents** — Run in parallel (LangGraph fan-out); each writes to its own key in `GraphState`.
- **validation_agent** — Cross-checks the three parallel results for contradictions and critical issues.
- **manager_agent** — Converts validation findings into concrete, prioritised actions (`ManagerReview`).

### Key files

| File | Role |
|------|------|
| `port/graph.py` | Builds and compiles the LangGraph `StateGraph`; defines node wiring and parallelism. |
| `port/state.py` | `GraphState` (typed dict) + Pydantic output models for every agent (`NewsReview`, `RiskReview`, `RegimeReview`, `ThemeReview`, `ValidationReview`, `ManagerReview`). |
| `port/server.py` | FastAPI app; `ReviewSession` manages one review lifecycle — stores event log, broadcasts SSE, handles interrupt/resume. |
| `port/portfolio.py` | `Portfolio` and `Position` Pydantic models; helpers to serialise positions for prompts. |
| `port/config.py` | LLM client factory; points at two local Ollama endpoints (fast: port 8000, best: port 8003). |
| `port/prompts.py` | System prompts for all agents — edit here to change agent behaviour without touching agent code. |
| `port/agents/*.py` | One file per agent; each calls `llm.with_structured_output(OutputModel)` and writes its result into `GraphState`. |

### Server endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /api/review/start` | Start a new review; returns `review_id`. |
| `GET /api/review/{id}/stream` | SSE stream of agent events. |
| `POST /api/review/{id}/confirm` | Resume graph if a node uses `interrupt()` (unused in default pipeline). |
| `GET /api/review/{id}/result` | Final `ManagerReview` when complete. |
| `GET /api/review/{id}/status` | Poll-based status check. |

### LLM configuration

Both models run locally via Ollama-compatible endpoints (configured in `port/config.py`):

- **Fast model** (`http://localhost:8000/v1`) — Qwen2.5-7B, used for latency-sensitive agents.
- **Best model** (`http://localhost:8003/v1`) — Qwen3.5-35B, used for deep analysis agents.

No cloud API keys are required. `OPENAI_API_KEY` env var is accepted for compatibility but defaults to `"ollama"`.

### Adding a new agent

1. Add a Pydantic output model to `port/state.py` and add its field to `GraphState`.
2. Create `port/agents/my_agent.py` — call `llm.with_structured_output(MyOutputModel)` and return `{"my_result": result}`.
3. Add a system prompt to `port/prompts.py`.
4. Register the node and edge(s) in `port/graph.py`.
5. Expose the result in `port/server.py` SSE broadcast if the UI should display it.
