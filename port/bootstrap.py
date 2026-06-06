"""Process startup hook: load config from TOML + env, then any other one-shot init.

Every entry point (web server, CLI, MCP server, tests) calls ``bootstrap()`` exactly once
before doing anything that reads config.
"""

from __future__ import annotations

from pathlib import Path

from port.config import load


def bootstrap(toml_path: Path | None = None) -> None:
    """Load config (idempotent). ``toml_path`` defaults to repo-root ``config.toml``."""
    load(toml_path)
