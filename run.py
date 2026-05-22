#!/usr/bin/env python3
"""Start the Portfolio Advisor GUI.

Usage:
    python run.py                # host/port/log_level come from config.toml
    python run.py --port 8080    # CLI flag overrides config.server.port
"""

import argparse

import uvicorn

from port.bootstrap import bootstrap


def main() -> None:
    bootstrap()
    # Imported AFTER bootstrap so any module-top config reads see a loaded config.
    from port.config import config
    from port.logging_config import build_uvicorn_log_config

    parser = argparse.ArgumentParser(description="Portfolio Advisor")
    parser.add_argument("--host", default=config.server.host)
    parser.add_argument("--port", type=int, default=config.server.port)
    parser.add_argument("--reload", action="store_true", help="Hot-reload on code changes")
    parser.add_argument("--log-level", default=config.server.log_level)
    args = parser.parse_args()

    print(f"Starting Portfolio Advisor at http://localhost:{args.port}")
    uvicorn.run(
        "port.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
        log_config=build_uvicorn_log_config(),
    )


if __name__ == "__main__":
    main()
