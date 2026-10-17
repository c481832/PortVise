from __future__ import annotations

import copy
import logging
import logging.config
from pathlib import Path
from typing import Any

from uvicorn.config import LOGGING_CONFIG

from advisor.config import REPO_ROOT, config

FILE_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"
AGENT_NAMES: tuple[str, ...] = (
    "planner",
    "data",
    "news",
    "news_summary",
    "risk",
    "regime",
    "theme",
    "allocation",
    "manager",
    "agent_summary",
)
AGENT_MODULE_LOGGERS: dict[str, str] = {
    "planner": "advisor.agents.planner",
    "data": "advisor.agents.data",
    "news": "advisor.agents.news",
    "risk": "advisor.agents.risk",
    "regime": "advisor.agents.regime",
    "theme": "advisor.agents.theme",
    "allocation": "advisor.agents.allocation",
    "manager": "advisor.agents.manager",
}

AGENTFLOW_LOGGER_PREFIX = "advisor.agentflow"


def flow_log(agent: str) -> logging.Logger:
    """The per-agent flow logger, routed to logs/agents/<agent>.log."""
    return logging.getLogger(f"{AGENTFLOW_LOGGER_PREFIX}.{agent}")


EXTRA_LOGGERS: tuple[tuple[str, str], ...] = (
    ("advisor", "INFO"),
    ("langgraph", "INFO"),
    ("langchain", "INFO"),
    ("langchain_core", "INFO"),
    ("fastapi", "INFO"),
    ("starlette", "INFO"),
    ("py.warnings", "WARNING"),
)


def wipe_advisor_log_file(log_path: Path | None, *, backup_count: int) -> None:
    if log_path is None:
        return
    log_path = log_path.resolve()
    log_path.unlink(missing_ok=True)
    for i in range(1, backup_count + 1):
        log_path.with_name(f"{log_path.name}.{i}").unlink(missing_ok=True)


def log_file_paths(log_path: Path) -> tuple[Path, ...]:
    logs_dir = log_path.parent
    agent_logs_dir = logs_dir / "agents"
    return (
        log_path,
        logs_dir / "events.log",
        *(agent_logs_dir / f"{agent}.log" for agent in AGENT_NAMES),
    )


def iter_file_handlers() -> list[logging.FileHandler]:
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


def truncate_active_file_handler(handler: logging.FileHandler) -> None:
    handler.acquire()
    try:
        handler.flush()
        if handler.stream is None:
            handler.stream = handler._open()
        handler.stream.seek(0)
        handler.stream.truncate(0)
    finally:
        handler.release()


def clear_advisor_log_files() -> None:
    log_path = advisor_log_path_resolved()
    if log_path is None:
        return

    paths = {path.resolve() for path in log_file_paths(log_path.resolve())}
    file_handlers = iter_file_handlers()
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
            truncate_active_file_handler(handler)

    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path not in active_paths:
            path.write_text("")
        for i in range(1, config.log.backup_count + 1):
            path.with_name(f"{path.name}.{i}").unlink(missing_ok=True)


def build_uvicorn_log_config(*, enable_file_logging: bool) -> dict[str, Any]:
    cfg = copy.deepcopy(LOGGING_CONFIG)
    if not enable_file_logging:
        return cfg

    log_path = advisor_log_path_resolved()
    if log_path is None:
        return cfg

    log_path = log_path.resolve()
    logs_dir = log_path.parent
    agent_logs_dir = logs_dir / "agents"
    logs_dir.mkdir(parents=True, exist_ok=True)
    agent_logs_dir.mkdir(parents=True, exist_ok=True)
    wipe_advisor_log_file(log_path, backup_count=config.log.backup_count)
    event_log_path = logs_dir / "events.log"
    wipe_advisor_log_file(event_log_path, backup_count=config.log.backup_count)
    for agent in AGENT_NAMES:
        wipe_advisor_log_file(agent_logs_dir / f"{agent}.log", backup_count=config.log.backup_count)

    cfg.setdefault("formatters", {})["port_file"] = {"format": FILE_FORMAT}
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
    for agent in AGENT_NAMES:
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
    cfg["loggers"]["advisor.events"] = {
        "handlers": ["default", "event_file"],
        "level": "INFO",
        "propagate": False,
    }
    for agent in AGENT_NAMES:
        cfg["loggers"][f"{AGENTFLOW_LOGGER_PREFIX}.{agent}"] = {
            "handlers": ["default", f"agent_{agent}_file"],
            "level": "INFO",
            "propagate": False,
        }
        module_logger = AGENT_MODULE_LOGGERS.get(agent)
        if module_logger is None:
            continue
        cfg["loggers"][module_logger] = {
            "handlers": ["default", f"agent_{agent}_file"],
            "level": "INFO",
            "propagate": False,
        }

    for name, level in EXTRA_LOGGERS:
        cfg["loggers"][name] = {
            "handlers": ["default", "port_file"],
            "level": level,
            "propagate": False,
        }

    return cfg


def apply_cli_logging_config() -> None:
    cfg = build_uvicorn_log_config(enable_file_logging=True)
    for logger_config in cfg.get("loggers", {}).values():
        handlers = logger_config.get("handlers")
        if handlers:
            logger_config["handlers"] = [
                handler for handler in handlers if handler not in {"default", "access"}
            ]
    logging.config.dictConfig(cfg)


def advisor_log_path_resolved() -> Path | None:
    raw = (config.log.file or "").strip()
    if not raw:
        return None
    p = Path(raw)
    if p.is_absolute():
        return p.resolve()
    return (REPO_ROOT / p).resolve()
