from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from port.bootstrap import bootstrap

bootstrap()  # Load config before anything else touches it.

from port.web.routes import STATIC_DIR, router  # noqa: E402


def create_app() -> FastAPI:
    app = FastAPI(title="Portfolio Advisor")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(router)
    return app


app = create_app()
