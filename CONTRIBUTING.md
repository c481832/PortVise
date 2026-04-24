# Contributing

Portfolio Advisor is a self-hosted alpha for AI-assisted portfolio review. Contributions should
keep the project honest about its limits: this is decision-support software, not financial advice.

## Development Setup

Requirements:

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)

Install dependencies:

```bash
uv sync --group dev
```

Run the app:

```bash
uv run python run.py
```

Open `http://localhost:7860`.

## Quality Gates

Run the same checks used by CI before opening a pull request:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

If you change Docker packaging, also run:

```bash
docker build .
```

## Contribution Guidelines

- Keep public docs cloud-first and OpenAI-compatible; local model setup belongs in advanced docs.
- Do not commit generated artifacts such as `.coverage`, `htmlcov/`, logs, or local `.env` files.
- Avoid overclaiming reliability. LLM output can be wrong, market data can be stale, and the app is
  not a substitute for professional financial advice.
- Prefer focused pull requests with tests for behavior changes.
- Keep agent output schemas backward-compatible unless the UI and tests are updated in the same
  change.

## Local Hooks

A pre-push hook is available:

```bash
git config core.hooksPath .githooks
```

The hook runs lint, format check, and tests. CI remains the source of truth.
