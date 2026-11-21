import asyncio
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from app.api.router import api_router
from app.db.session import engine
from app.db.session import SessionLocal
from app.domains.architecture import models  # noqa: F401
from app.domains.settings import models as settings_models  # noqa: F401
from app.domains.settings.service import SettingsService
from app.domains.incidents import models as incident_models  # noqa: F401
from app.domains.monitoring import models as monitoring_models  # noqa: F401
from app.domains.monitoring.worker import start_monitoring_worker, stop_monitoring_worker

app = FastAPI(title="MonitorAI V2.20 API", version="2.20")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

def run_migrations(baseline_revision: str | None = None) -> None:
    backend_root = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(backend_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_root / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL", "postgresql+asyncpg://monitorai:monitorai_dev@localhost:55432/monitorai"))
    if baseline_revision:
        command.stamp(alembic_cfg, baseline_revision)
    command.upgrade(alembic_cfg, "head")


async def needs_baseline_stamp() -> bool:
    async with engine.connect() as connection:
        architectures_exists = await connection.scalar(text("SELECT to_regclass('public.architectures') IS NOT NULL"))
        alembic_exists = await connection.scalar(text("SELECT to_regclass('public.alembic_version') IS NOT NULL"))
    return bool(architectures_exists) and not bool(alembic_exists)

@app.on_event("startup")
async def initialize_database():
    baseline = "0004_visual_hierarchy" if await needs_baseline_stamp() else None
    await asyncio.to_thread(run_migrations, baseline)

    # Load persisted Azure credentials into process environment for adapter consumption.
    async with SessionLocal() as session:
        service = SettingsService()
        await service.get_azure_status(db=session)
    start_monitoring_worker()

@app.on_event("shutdown")
async def close_database():
    await stop_monitoring_worker()
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
