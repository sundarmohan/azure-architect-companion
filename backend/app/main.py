import asyncio
import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from alembic import command
from alembic.config import Config
from app.api.router import api_router
from app.db.session import engine
from app.domains.access.routes import bootstrap_admin
from app.domains.architecture import models  # noqa: F401
from app.domains.settings import models as settings_models  # noqa: F401
from app.domains.incidents import models as incident_models  # noqa: F401
from app.domains.monitoring import models as monitoring_models  # noqa: F401
from app.domains.monitoring.observation_worker import run_worker, stop_worker
from app.request_safety import safe_request_boundary

app = FastAPI(title="MonitorAI V2.20 API", version="2.20")

dev_origins = []
if os.getenv("MONITORAI_INSECURE_LOCAL_COOKIE") == "1":
    dev_origins = [
        f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (5173, 5174)
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=dev_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Content-Type", "X-Client-ID", "X-MonitorAI-Request"],
)

@app.middleware("http")
async def prevent_api_caching(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.middleware("http")(safe_request_boundary)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, error: RequestValidationError):
    return JSONResponse(status_code=422, content={
        "detail": [{"loc": item["loc"], "type": item["type"]} for item in error.errors()],
    })


app.include_router(api_router, prefix="/api")

def run_migrations() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(backend_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_root / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL", "postgresql+asyncpg://monitorai:monitorai_dev@localhost:55432/monitorai"))
    command.upgrade(alembic_cfg, "head")


@app.on_event("startup")
async def initialize_database():
    await asyncio.to_thread(run_migrations)
    await bootstrap_admin()
    app.state.observation_worker = (
        asyncio.create_task(run_worker()) if os.getenv("MONITORAI_OBSERVATION_WORKER", "1") == "1" else None
    )


@app.on_event("shutdown")
async def close_database():
    await stop_worker(getattr(app.state, "observation_worker", None))
    await engine.dispose()


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.20"}


# Serve the built SPA (production image copies frontend/dist to /app/static).
# Mounted last so /api and /health keep precedence; absent in local dev.
_frontend_dist = Path(os.getenv("FRONTEND_DIST_DIR", Path(__file__).resolve().parents[1] / "static"))
if (_frontend_dist / "index.html").is_file():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
