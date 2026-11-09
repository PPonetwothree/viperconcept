"""VIPER demonstrator server.

Run from the project root on Windows:
    python backend\\main.py
then open http://127.0.0.1:8000
"""
from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

import config  # noqa: E402
from api import routes, ws  # noqa: E402
from database.store import EventStore  # noqa: E402
from simulation.runtime import Runtime  # noqa: E402


def create_app(db_path: str | Path | None = None, autostart: bool | None = None,
               run_loop: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = EventStore(db_path or config.DB_PATH)
        runtime = Runtime(store)
        app.state.runtime = runtime
        runtime.log("info", "system", "VIPER demonstrator started in SIMULATION mode — no hardware connected")
        if config.AUTOSTART if autostart is None else autostart:
            runtime.control("start")
        task = asyncio.create_task(runtime.run_forever()) if run_loop else None
        yield
        if task:
            task.cancel()
        store.conn.close()

    app = FastAPI(title="VIPER API", version="0.1.0", lifespan=lifespan,
                  description="Vigilant Infrastructure Protection & Emergency Response — R&D demonstrator. "
                              "All data are simulated.",
                  docs_url="/api/docs-ui", redoc_url=None, openapi_url="/api/openapi.json")
    app.include_router(routes.router)
    app.include_router(ws.router)
    app.mount("/src", StaticFiles(directory=config.FRONTEND_DIR / "src"), name="src")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(config.FRONTEND_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    print(f"\n  VIPER demonstrator → http://{config.HOST}:{config.PORT}\n"
          f"  API docs          → http://{config.HOST}:{config.PORT}/api/docs-ui\n"
          f"  Database          → {config.DB_PATH}\n  Press Ctrl+C to stop.\n")
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="warning")
