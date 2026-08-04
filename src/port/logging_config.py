"""Uvicorn ``log_config`` — split logs into main event + per-agent flow files."""

from __future__ import annotations

import copy
import logging
import logging.config
from pathlib import Path
from typing import Any

from uvicorn.config import LOGGING_CONFIG

from port.config import config, port_log_path_resolved, wipe_port_log_file

_FILE_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"
_AGENT_NAMES: tuple[str, ...] = (
    "planner",
    "data",
    "news",
    "risk",
    "regime",
    "theme",
    "validation",
    "allocation",
    "manager",
    "agent_summary",
)
_AGENT_MODULE_LOGGERS: dict[str, str] = {
    "planner": "port.agents.planner",
    "data": "port.agents.data",
    "news": "port.agents.news",
    "risk": "port.agents.risk",
    "regime": "port.agents.regime",
    "theme": "port.agents.theme",
    "validation": "port.agents.validation",
    "allocation": "port.agents.allocation",
    "manager": "port.agents.manager",
    "agent_summary": "port.agent_summary",
}
_AGENT_FLOW_LOG_ALIASES: dict[str, str] = {
    "news_synthesis": "news",
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
    for i in range(1, config.log.backup_count + 1):
        log_path.with_name(f"{log_path.name}.{i}").unlink(missing_ok=True)


def _log_file_paths(log_path: Path) -> tuple[Path, ...]:
    logs_dir = log_path.parent
    agent_logs_dir = logs_dir / "agents"
    return (
        log_path,
        logs_dir / "events.log",
        *(agent_logs_dir / f"{agent}.log" for agent in _AGENT_NAMES),
    )


def _iter_file_handlers() -> list[logging.FileHandler]:
    handlers: list[logging.FileHandler] = []
    seen: set[int] = set()
    manager = logging.root.manager
    loggers = [logging.getLogger()]
    loggers.extend(
        logger for logger in manager.loggerDict.values() if isinstance(logger, logging.Logger)
    )
    for logger in loggers:
        for handler in logger.handlers:
            if isinstance(handler, logging.FileHandler) and id(handler) not in seen:
                handlers.append(handler)
                seen.add(id(handler))
    return handlers


def _truncate_active_file_handler(handler: logging.FileHandler) -> None:
    handler.acquire()
    try:
        handler.flush()
        if handler.stream is None:
            handler.stream = handler._open()
        handler.stream.seek(0)
        handler.stream.truncate(0)
    finally:
        handler.release()


def clear_port_log_files() -> None:
    """Clear current file logs so a new review run owns the visible log set."""
    log_path = port_log_path_resolved()
    if log_path is None:
        return

    paths = {path.resolve() for path in _log_file_paths(log_path.resolve())}
    file_handlers = _iter_file_handlers()
    active_paths: set[Path] = set()
    for handler in file_handlers:
        base_filename = getattr(handler, "baseFilename", None)
        if base_filename is None:
            continue
        try:
            handler_path = Path(base_filename).resolve()
        except OSError:
            continue
        if handler_path in paths:
            active_paths.add(handler_path)
            _truncate_active_file_handler(handler)

    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path not in active_paths:
            path.write_text("")
        for i in range(1, config.log.backup_count + 1):
            path.with_name(f"{path.name}.{i}").unlink(missing_ok=True)


def build_uvicorn_log_config(*, enable_file_logging: bool = True) -> dict[str, Any]:
    """Return a logging dictConfig with main event + per-agent flow files.

    When ``PORT_LOG_FILE`` is set, the previous file (and rotation fragments) is wiped so
    each new server process starts with fresh logs.
    """
    cfg = copy.deepcopy(LOGGING_CONFIG)
    if not enable_file_logging:
        return cfg

    log_path = port_log_path_resolved()
    if log_path is None:
        return cfg

    log_path = log_path.resolve()
    logs_dir = log_path.parent
    agent_logs_dir = logs_dir / "agents"
    logs_dir.mkdir(parents=True, exist_ok=True)
    agent_logs_dir.mkdir(parents=True, exist_ok=True)
    wipe_port_log_file(log_path, backup_count=config.log.backup_count)
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
        "maxBytes": config.log.max_bytes,
        "backupCount": config.log.backup_count,
    }
    cfg["handlers"]["event_file"] = {
        "formatter": "port_file",
        "class": "logging.handlers.RotatingFileHandler",
        "filename": str(event_log_path),
        "maxBytes": config.log.max_bytes,
        "backupCount": config.log.backup_count,
    }
    for agent in _AGENT_NAMES:
        cfg["handlers"][f"agent_{agent}_file"] = {
            "formatter": "port_file",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(agent_logs_dir / f"{agent}.log"),
            "maxBytes": config.log.max_bytes,
            "backupCount": config.log.backup_count,
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
    for flow_name, agent_log in _AGENT_FLOW_LOG_ALIASES.items():
        cfg["loggers"][f"port.agentflow.{flow_name}"] = {
            "handlers": ["default", f"agent_{agent_log}_file"],
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


def apply_port_logging_config(*, enable_file_logging: bool = True) -> None:
    """Apply :func:`build_uvicorn_log_config` (for tests and non-uvicorn entry points)."""
    logging.config.dictConfig(build_uvicorn_log_config(enable_file_logging=enable_file_logging))


def apply_cli_logging_config() -> None:
    """Enable detailed file logs for CLI runs without echoing them to stderr.

    CLI progress and errors have their own concise stderr format.  The file handlers retain the
    full prompts, structured LLM outputs, and module diagnostics for post-mortem debugging.
    """
    cfg = build_uvicorn_log_config(enable_file_logging=True)
    for logger_config in cfg.get("loggers", {}).values():
        handlers = logger_config.get("handlers")
        if handlers:
            logger_config["handlers"] = [
                handler for handler in handlers if handler not in {"default", "access"}
            ]
    logging.config.dictConfig(cfg)
