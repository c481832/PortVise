from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from advisor.web.routes import UI_DIR, router


def create_app() -> FastAPI:
    app = FastAPI(title="Portfolio Advisor")
    app.mount("/ui", StaticFiles(directory=str(UI_DIR)), name="ui")
    app.include_router(router)
    return app


app = create_app()
