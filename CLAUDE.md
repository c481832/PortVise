# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install / sync dependencies (creates .venv automatically)
uv sync

# Start the server (default port 7000)
uv run python run.py

# Dev mode with hot-reload
uv run python run.py --reload --port 7000

# Add a new dependency
uv add <package>
```

There are no automated tests in this project.

## Architecture

A 7-node LangGraph pipeline that analyses a stock portfolio and streams results to a web UI over SSE.

### Agent pipeline

```
START → plan_agent ──(interrupt)──> news_agent
                                       │
                          ┌────────────┼────────────┐
                     risk_agent  regime_agent  theme_agent   (parallel fan-out)
                          └────────────┼────────────┘
                                 validation_agent
                                       │
                                 planner_agent → END
```

- **plan_agent** — Confirms/modifies portfolio with human-in-the-loop `interrupt()` before analysis begins.
- **news_agent** — Broad macro & news context; runs first so downstream agents can use it.
- **risk / regime / theme agents** — Run in parallel (LangGraph fan-out); each writes to its own key in `GraphState`.
- **validation_agent** — Cross-checks the three parallel results for contradictions and critical issues.
- **planner_agent** — Converts validation findings into concrete, prioritised actions.

### Key files

| File | Role |
|------|------|
| `port/graph.py` | Builds and compiles the LangGraph `StateGraph`; defines node wiring and parallelism. |
| `port/state.py` | `GraphState` (typed dict) + Pydantic output models for every agent (`NewsReview`, `RiskReview`, `RegimeReview`, `ThemeReview`, `ValidationReview`, `PlannerReview`). |
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
| `POST /api/review/{id}/confirm` | Resume graph after plan-agent interrupt. |
| `GET /api/review/{id}/result` | Final `PlannerReview` when complete. |
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
