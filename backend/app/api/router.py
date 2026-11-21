from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.access.azure import router as settings_router
from app.domains.access.routes import audit, client_access, get_db, require_request_header
from app.domains.access.routes import router as auth_router
from app.domains.architecture.azure_routes import router as azure_router
from app.domains.architecture.models import Architecture
from app.domains.architecture.routes import router as architecture_router

GRAPH_ENDPOINTS = {
    "list_architectures", "create_architecture", "get_architecture", "update_architecture",
    "delete_architecture", "list_resources", "create_resource", "update_resource", "delete_resource",
    "list_relationships", "create_relationship", "delete_relationship", "validate_relationship",
    "list_subscriptions", "create_subscription", "list_resource_groups", "create_resource_group",
    "update_resource_group", "delete_resource_group", "list_dependencies",
}


async def authorize_graph(request: Request, client_id: UUID = Depends(client_access),
                          db: AsyncSession = Depends(get_db)):
    endpoint = request.scope["route"].name
    if endpoint not in GRAPH_ENDPOINTS:
        raise HTTPException(403, "This operation is unavailable in Phase 1")
    architecture_id = request.path_params.get("architecture_id")
    if architecture_id is not None:
        try:
            parsed = UUID(architecture_id)
        except ValueError:
            raise HTTPException(404, "Architecture not found") from None
        if not await db.scalar(select(Architecture.id).where(
            Architecture.id == parsed, Architecture.client_id == client_id
        )):
            audit(db, "architecture_access", request.state.account, client_id, str(parsed), "denied")
            await db.commit()
            raise HTTPException(404, "Architecture not found")
    if request.method not in {"GET", "HEAD"} and endpoint != "validate_relationship":
        audit(db, endpoint, request.state.account, client_id, architecture_id)


api_router = APIRouter(dependencies=[Depends(require_request_header)])
api_router.include_router(auth_router, prefix="/auth", tags=["authentication"])
api_router.include_router(architecture_router, prefix="/architectures", tags=["architectures"],
                          dependencies=[Depends(authorize_graph)])
api_router.include_router(azure_router, prefix="/azure", tags=["azure"], dependencies=[Depends(client_access)])
api_router.include_router(settings_router, prefix="/settings/azure", tags=["settings"])
