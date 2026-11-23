from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.assessments.routes import router as assessment_router
from app.domains.backup.routes import router as backup_router
from app.domains.compliance.routes import router as compliance_router
from app.domains.cost.actual_routes import router as actual_cost_router
from app.domains.access.azure import router as settings_router
from app.domains.access.inventory import router as inventory_router
from app.domains.access.routes import audit, audit_router, client_access, get_db, require_request_header
from app.domains.access.routes import router as auth_router
from app.domains.architecture.artifacts import router as artifacts_router
from app.domains.architecture.lifecycle import router as lifecycle_router
from app.domains.architecture.azure_routes import router as azure_router
from app.domains.architecture.models import Architecture
from app.domains.architecture.routes import router as architecture_router
from app.domains.monitoring.diagnostics import router as diagnostics_router
from app.domains.monitoring.observation_routes import router as observation_router
from app.domains.monitoring.security_routes import router as security_router

GRAPH_ENDPOINTS = {
    "list_architectures", "create_architecture", "get_architecture", "update_architecture",
    "delete_architecture", "list_resources", "create_resource", "update_resource", "delete_resource",
    "list_relationships", "create_relationship", "delete_relationship", "validate_relationship",
    "list_subscriptions", "create_subscription", "list_resource_groups", "create_resource_group",
    "update_resource_group", "delete_resource_group", "list_dependencies", "estimate_architecture_cost",
}


READ_ONLY_POSTS = {"validate_relationship", "estimate_architecture_cost"}


async def authorize_graph(request: Request, client_id: UUID = Depends(client_access),
                          db: AsyncSession = Depends(get_db)):
    endpoint = request.scope["route"].name
    if endpoint not in GRAPH_ENDPOINTS:
        raise HTTPException(403, "This feature is unavailable in the current phase")
    mutating = request.method not in {"GET", "HEAD"} and endpoint not in READ_ONLY_POSTS
    architecture_id = request.path_params.get("architecture_id")
    if architecture_id is not None:
        try:
            parsed = UUID(architecture_id)
        except ValueError:
            raise HTTPException(404, "Architecture not found") from None
        lookup = select(Architecture.status).where(
            Architecture.id == parsed, Architecture.client_id == client_id
        )
        stage = await db.scalar(lookup.with_for_update() if mutating else lookup)
        if stage is None:
            audit(db, "architecture_access", request.state.account, client_id, str(parsed), "denied")
            await db.commit()
            raise HTTPException(404, "Architecture not found")
        if endpoint == "delete_architecture":
            if request.state.client_role != "admin":
                raise HTTPException(403, "Client administrator required")
            if stage not in {"draft", "archived"}:
                raise HTTPException(409, "Archive the design before deleting it")
        elif mutating and stage != "draft":
            raise HTTPException(409, "Only draft designs can be edited")
    if mutating:
        audit(db, endpoint, request.state.account, client_id, architecture_id)


api_router = APIRouter(dependencies=[Depends(require_request_header)])
api_router.include_router(auth_router, prefix="/auth", tags=["authentication"])
api_router.include_router(audit_router, tags=["audit"])
api_router.include_router(architecture_router, prefix="/architectures", tags=["architectures"],
                          dependencies=[Depends(authorize_graph)])
api_router.include_router(azure_router, prefix="/azure", tags=["azure"], dependencies=[Depends(client_access)])
api_router.include_router(settings_router, prefix="/settings/azure", tags=["settings"])
api_router.include_router(inventory_router, prefix="/azure", tags=["azure-inventory"])
api_router.include_router(lifecycle_router, prefix="/architectures", tags=["design-lifecycle"])
api_router.include_router(artifacts_router, prefix="/architectures", tags=["design-artifacts"])
api_router.include_router(backup_router, prefix="/azure", tags=["azure-backup"])
api_router.include_router(actual_cost_router, prefix="/azure/cost", tags=["azure-cost"])
api_router.include_router(compliance_router, prefix="/compliance", tags=["compliance"])
api_router.include_router(observation_router, prefix="/azure", tags=["azure-observations"])
api_router.include_router(diagnostics_router, prefix="/azure/diagnostics", tags=["azure-diagnostics"])
api_router.include_router(security_router, prefix="/azure/security", tags=["azure-security"])
api_router.include_router(assessment_router, prefix="/assessments", tags=["security-assessments"])
