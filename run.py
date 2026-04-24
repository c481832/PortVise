#!/usr/bin/env python3
"""
Start the Portfolio Advisor GUI.
    python run.py            # default port 7860
    python run.py --port 8080
"""

import argparse

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Portfolio Advisor")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--reload", action="store_true", help="Hot-reload on code changes")
    args = parser.parse_args()

    print(f"Starting Portfolio Advisor at http://localhost:{args.port}")
    from port.logging_config import build_uvicorn_log_config

    uvicorn.run(
        "port.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
        log_config=build_uvicorn_log_config(),
    )


if __name__ == "__main__":
    main()
