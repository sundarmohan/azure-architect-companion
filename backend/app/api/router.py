from fastapi import APIRouter
from app.domains.architecture.routes import router as architecture_router
from app.domains.architecture.azure_routes import router as azure_router
from app.domains.reports.routes import router as reports_router
from app.domains.settings.routes import router as settings_router
from app.domains.monitoring.connection_routes import router as monitoring_router
api_router = APIRouter()
api_router.include_router(architecture_router, prefix="/architectures", tags=["architectures"])
api_router.include_router(azure_router, prefix="/azure", tags=["azure"])
api_router.include_router(reports_router, prefix="/reports", tags=["reports"])
api_router.include_router(settings_router, prefix="/settings", tags=["settings"])
api_router.include_router(monitoring_router, prefix="/monitoring", tags=["monitoring"])
