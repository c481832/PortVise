from __future__ import annotations

from pathlib import Path

from port import logging_config
from port.logging_config import build_uvicorn_log_config


def test_build_uvicorn_log_config_can_disable_file_logging() -> None:
    cfg = build_uvicorn_log_config(enable_file_logging=False)

    handlers = cfg.get("handlers", {})
    assert "port_file" not in handlers
    assert "event_file" not in handlers
    assert all(not name.startswith("agent_") for name in handlers)


def test_build_uvicorn_log_config_keeps_file_logging_enabled_by_default(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        logging_config,
        "port_log_path_resolved",
        lambda: tmp_path / "port.log",
    )

    cfg = build_uvicorn_log_config()

    handlers = cfg["handlers"]
    assert "port_file" in handlers
    assert "event_file" in handlers
    assert "agent_planner_file" in handlers
