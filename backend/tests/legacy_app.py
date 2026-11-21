"""Exercise preserved feature code independently of the Phase 1 API surface.

This test-only application is never included in the production image.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import architecture_router, azure_router
from app.db.session import SessionLocal, engine
from app.domains.access.routes import get_db
from app.domains.monitoring.connection_routes import router as monitoring_router
from app.domains.reports.routes import router as reports_router
from app.domains.settings.routes import router as settings_router
from app.main import health, run_migrations


@asynccontextmanager
async def lifespan(_app):
    await asyncio.to_thread(run_migrations)
    yield
    await engine.dispose()


app = FastAPI(lifespan=lifespan)
app.add_api_route("/health", health)
app.include_router(architecture_router, prefix="/api/architectures")
app.include_router(azure_router, prefix="/api/azure")
app.include_router(reports_router, prefix="/api/reports")
app.include_router(settings_router, prefix="/api/settings")
app.include_router(monitoring_router, prefix="/api/monitoring")


async def legacy_db():
    async with SessionLocal() as db:
        db.info["client_id"] = None
        yield db


app.dependency_overrides[get_db] = legacy_db
