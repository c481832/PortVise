"""FastAPI app factory for the arena GUI (separate from the review server).

Serving ``arena serve`` boots this app and, on startup, launches the background scheduler so
the engine trades once per market day at each competition's configured ``trade_time``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from port.bootstrap import bootstrap

bootstrap()

from arena.scheduler import run_scheduler  # noqa: E402
from arena.web.routes import ARENA_ROOT, STATIC_DIR, router  # noqa: E402

log = logging.getLogger(__name__)


def create_app(*, start_scheduler: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(run_scheduler(ARENA_ROOT)) if start_scheduler else None
        try:
            yield
        finally:
            if task is not None:
                task.cancel()

    app = FastAPI(title="Portfolio Arena", lifespan=lifespan)
    app.include_router(router)

    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
    else:
        log.warning("arena frontend not built; %s missing. Run `npm run arena:build`.", STATIC_DIR)

        @app.get("/")
        def _needs_build() -> JSONResponse:
            return JSONResponse(
                status_code=503,
                content={"detail": "Arena frontend not built. Run `npm run arena:build`."},
            )

    return app


app = create_app()
