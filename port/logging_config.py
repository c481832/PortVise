"""Uvicorn ``log_config`` — mirror stderr/stdout (terminal) to ``port.log``."""

from __future__ import annotations

import copy
import logging.config
from typing import Any

from uvicorn.config import LOGGING_CONFIG

from port.config import port_log_path_resolved, settings, wipe_port_log_file

_FILE_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"

_EXTRA_LOGGERS: tuple[tuple[str, str], ...] = (
    ("port", "INFO"),
    ("langgraph", "INFO"),
    ("langchain", "INFO"),
    ("langchain_core", "INFO"),
    ("fastapi", "INFO"),
    ("starlette", "INFO"),
    ("py.warnings", "WARNING"),
)


def build_uvicorn_log_config() -> dict[str, Any]:
    """Return a logging dictConfig like uvicorn’s defaults, plus a shared log file.

    When ``PORT_LOG_FILE`` is set, the previous file (and rotation fragments) is wiped so
    each new server process starts with a fresh file. The same records that go to the
    terminal (uvicorn + access + ``port.*`` + common libs) are also written to that file.
    """
    cfg = copy.deepcopy(LOGGING_CONFIG)
    log_path = port_log_path_resolved()
    if log_path is None:
        return cfg

    log_path = log_path.resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    wipe_port_log_file(log_path)

    cfg.setdefault("formatters", {})["port_file"] = {"format": _FILE_FORMAT}
    cfg["handlers"]["port_file"] = {
        "formatter": "port_file",
        "class": "logging.handlers.RotatingFileHandler",
        "filename": str(log_path),
        "maxBytes": settings.port_log_max_bytes,
        "backupCount": settings.port_log_backup_count,
    }

    cfg["loggers"]["uvicorn"]["handlers"] = ["default", "port_file"]
    cfg["loggers"]["uvicorn.access"]["handlers"] = ["access", "port_file"]

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
