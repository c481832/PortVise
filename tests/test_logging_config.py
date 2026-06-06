from __future__ import annotations

import logging
from pathlib import Path

from port import logging_config
from port.logging_config import build_uvicorn_log_config, clear_port_log_files


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
    assert "agent_agent_summary_file" in handlers
    assert cfg["loggers"]["port.agentflow.agent_summary"]["handlers"] == [
        "default",
        "agent_agent_summary_file",
    ]
    assert cfg["loggers"]["port.agent_summary"]["handlers"] == [
        "default",
        "agent_agent_summary_file",
    ]


def test_news_synthesis_flow_logs_route_to_news_agent_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        logging_config,
        "port_log_path_resolved",
        lambda: tmp_path / "port.log",
    )

    cfg = build_uvicorn_log_config()

    news_synthesis_logger = cfg["loggers"]["port.agentflow.news_synthesis"]
    assert news_synthesis_logger["handlers"] == ["default", "agent_news_file"]
    assert news_synthesis_logger["propagate"] is False


def test_clear_port_log_files_truncates_active_logs_and_removes_backups(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "port.log"
    event_path = tmp_path / "events.log"
    agent_path = tmp_path / "agents" / "planner.log"
    agent_path.parent.mkdir()
    for path in (log_path, event_path, agent_path):
        path.write_text("old log\n", encoding="utf-8")
        path.with_name(f"{path.name}.1").write_text("rotated\n", encoding="utf-8")

    monkeypatch.setattr(logging_config, "port_log_path_resolved", lambda: log_path)
    logger = logging.getLogger("port.agentflow.planner")
    handler = logging.FileHandler(agent_path)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        logger.info("active old log")
        clear_port_log_files()
        logger.info("new log")
    finally:
        logger.removeHandler(handler)
        handler.close()

    assert log_path.read_text(encoding="utf-8") == ""
    assert event_path.read_text(encoding="utf-8") == ""
    assert agent_path.read_text(encoding="utf-8") == "new log\n"
    assert not (log_path.with_name("port.log.1")).exists()
    assert not (event_path.with_name("events.log.1")).exists()
    assert not (agent_path.with_name("planner.log.1")).exists()
