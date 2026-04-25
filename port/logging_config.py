"""Uvicorn ``log_config`` — split logs into main event + per-agent flow files."""

from __future__ import annotations

import copy
import logging.config
from pathlib import Path
from typing import Any

from uvicorn.config import LOGGING_CONFIG

from port.config import port_log_path_resolved, settings, wipe_port_log_file

_FILE_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"
_AGENT_NAMES: tuple[str, ...] = (
    "planner",
    "data",
    "news",
    "risk",
    "regime",
    "theme",
    "validation",
    "manager",
)
_AGENT_MODULE_LOGGERS: dict[str, str] = {
    "planner": "port.agents.planner",
    "data": "port.agents.data",
    "news": "port.agents.news",
    "risk": "port.agents.risk",
    "regime": "port.agents.regime",
    "theme": "port.agents.theme",
    "validation": "port.agents.validation",
    "manager": "port.agents.manager",
}

_EXTRA_LOGGERS: tuple[tuple[str, str], ...] = (
    ("port", "INFO"),
    ("langgraph", "INFO"),
    ("langchain", "INFO"),
    ("langchain_core", "INFO"),
    ("fastapi", "INFO"),
    ("starlette", "INFO"),
    ("py.warnings", "WARNING"),
)


def _wipe_rotating_file(log_path: Path) -> None:
    log_path = log_path.resolve()
    log_path.unlink(missing_ok=True)
    for i in range(1, settings.port_log_backup_count + 1):
        log_path.with_name(f"{log_path.name}.{i}").unlink(missing_ok=True)


def build_uvicorn_log_config() -> dict[str, Any]:
    """Return a logging dictConfig with main event + per-agent flow files.

    When ``PORT_LOG_FILE`` is set, the previous file (and rotation fragments) is wiped so
    each new server process starts with fresh logs.
    """
    cfg = copy.deepcopy(LOGGING_CONFIG)
    log_path = port_log_path_resolved()
    if log_path is None:
        return cfg

    log_path = log_path.resolve()
    logs_dir = log_path.parent
    agent_logs_dir = logs_dir / "agents"
    logs_dir.mkdir(parents=True, exist_ok=True)
    agent_logs_dir.mkdir(parents=True, exist_ok=True)
    wipe_port_log_file(log_path)
    event_log_path = logs_dir / "events.log"
    _wipe_rotating_file(event_log_path)
    for agent in _AGENT_NAMES:
        _wipe_rotating_file(agent_logs_dir / f"{agent}.log")

    cfg.setdefault("formatters", {})["port_file"] = {"format": _FILE_FORMAT}
    cfg.setdefault("handlers", {})
    cfg["handlers"]["port_file"] = {
        "formatter": "port_file",
        "class": "logging.handlers.RotatingFileHandler",
        "filename": str(log_path),
        "maxBytes": settings.port_log_max_bytes,
        "backupCount": settings.port_log_backup_count,
    }
    cfg["handlers"]["event_file"] = {
        "formatter": "port_file",
        "class": "logging.handlers.RotatingFileHandler",
        "filename": str(event_log_path),
        "maxBytes": settings.port_log_max_bytes,
        "backupCount": settings.port_log_backup_count,
    }
    for agent in _AGENT_NAMES:
        cfg["handlers"][f"agent_{agent}_file"] = {
            "formatter": "port_file",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(agent_logs_dir / f"{agent}.log"),
            "maxBytes": settings.port_log_max_bytes,
            "backupCount": settings.port_log_backup_count,
        }

    cfg["loggers"]["uvicorn"]["handlers"] = ["default", "port_file"]
    cfg["loggers"]["uvicorn.access"]["handlers"] = ["access", "port_file"]

    cfg.setdefault("loggers", {})
    cfg["loggers"]["port.events"] = {
        "handlers": ["default", "event_file"],
        "level": "INFO",
        "propagate": False,
    }
    for agent in _AGENT_NAMES:
        cfg["loggers"][f"port.agentflow.{agent}"] = {
            "handlers": ["default", f"agent_{agent}_file"],
            "level": "INFO",
            "propagate": False,
        }
        module_logger = _AGENT_MODULE_LOGGERS[agent]
        cfg["loggers"][module_logger] = {
            "handlers": ["default", f"agent_{agent}_file"],
            "level": "INFO",
            "propagate": False,
        }

    for name, level in _EXTRA_LOGGERS:
        cfg["loggers"][name] = {
            "handlers": ["default", "port_file"],
            "level": level,
            "propagate": False,
        }

    return cfg


def apply_port_logging_config() -> None:
    """Apply :func:`build_uvicorn_log_config` (for tests and non-uvicorn entry points)."""
    logging.config.dictConfig(build_uvicorn_log_config())
