#!/usr/bin/env python3
"""Start the Portfolio Advisor GUI.

Usage:
    python run.py                # host/port/log_level come from config.toml
    python run.py --port 8080    # CLI flag overrides config.server.port
"""

import argparse

import uvicorn

from advisor.config import config
from advisor.logging import build_uvicorn_log_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Portfolio Advisor")
    parser.add_argument("--host", default=config.server.host)
    parser.add_argument("--port", type=int, default=config.server.port)
    parser.add_argument("--reload", action="store_true", help="Hot-reload on code changes")
    parser.add_argument("--log-level", default=config.server.log_level)
    args = parser.parse_args()

    print(f"Starting Portfolio Advisor at http://localhost:{args.port}")
    uvicorn.run(
        "advisor.web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
        log_config=build_uvicorn_log_config(enable_file_logging=True),
    )


if __name__ == "__main__":
    main()
