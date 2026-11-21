from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domains.access.routes import get_db
from app.domains.architecture.models import Architecture, ArchitectureResource, ArchitectureRelationship, AzureSubscription, AzureResourceGroup, ArchitectureDependency
from app.domains.architecture.catalog import (
    AZURE_RESOURCE_CATALOG,
    CATALOG_BY_RESOURCE_TYPE,
    VALID_RELATIONSHIP_MATRIX,
    VALID_RELATIONSHIP_TYPES,
    classify_relationship_rule,
)
from app.domains.architecture.azure_discovery import (
    AzureResourceDiscoveryAdapter,
    AzureResourceDiscoveryService,
)
from app.domains.cost.schemas import (
    ArchitectureActualCostRead,
    ArchitectureCostEstimateRead,
    ActualCostRequest,
    CostEstimateRequest,
)
from app.domains.cost.service import CostEstimationService
from app.domains.monitoring.service import MonitoringService
from app.domains.monitoring.alert_incident_workflow import MonitoringAlertIncidentWorkflow
from app.domains.monitoring.schemas import (
    ArchitectureMonitoringSummaryRead,
    MonitoringAlertSummaryRead,
    MonitoringIncidentDetailRead,
    MonitoringIncidentStatusUpdate,
    MonitoringIncidentSummaryRead,
    MonitoringRequest,
    ResourceMonitoringRead,
    UnusedResourceRequest,
    UnusedResourceSummaryRead,
)
from app.domains.governance import (
    GovernanceComplianceAdapter,
    GovernanceComplianceRequest,
    GovernanceComplianceSummaryRead,
    GovernanceSecurityAdapter,
    GovernanceSecurityRequest,
    GovernanceSecuritySummaryRead,
)
from app.domains.intelligence import IntelligenceAnalysisRead, IntelligenceAnalysisRequest, IntelligenceService
from app.domains.settings.service import SettingsService
from app.domains.architecture.schemas import (
    ArchitectureCreate, ArchitectureRead, ArchitectureUpdate,
    ResourceCreate, ResourceRead, ResourceUpdate,
    RelationshipCreate, RelationshipRead, SubscriptionCreate, SubscriptionRead,
    ResourceGroupCreate, ResourceGroupRead, ResourceGroupUpdate, DependencyRead,
    RelationshipValidationRead, RelationshipValidationRequest,
    AzureDiscoveryRead, AzureDiscoveryRequest,
)

router = APIRouter()

DEFAULT_DEPENDENCIES = {
    item["resource_type"]: item["required_dependencies"]
    for item in AZURE_RESOURCE_CATALOG
}

async def get_architecture_or_404(db: AsyncSession, architecture_id: UUID) -> Architecture:
    architecture = await db.scalar(select(Architecture).where(
        Architecture.id == architecture_id, Architecture.client_id == db.info["client_id"]
    ))
    if not architecture:
        raise HTTPException(status_code=404, detail="Architecture not found")
    return architecture


async def validate_subscription_ownership(
    db: AsyncSession,
    architecture_id: UUID,
    subscription_id: UUID | None,
) -> None:
    if subscription_id is None:
        return
    subscription = await db.scalar(select(AzureSubscription).where(
        AzureSubscription.id == subscription_id, AzureSubscription.architecture_id == architecture_id
    ))
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")


async def validate_resource_group_ownership(
    db: AsyncSession,
    architecture_id: UUID,
    resource_group_id: UUID | None,
) -> None:
    if resource_group_id is None:
        return
    group = await db.scalar(select(AzureResourceGroup).where(
        AzureResourceGroup.id == resource_group_id, AzureResourceGroup.architecture_id == architecture_id
    ))
    if not group:
        raise HTTPException(status_code=404, detail="Resource group not found")


async def ensure_default_dependencies(db: AsyncSession, architecture_id: UUID) -> None:
    existing_rows = await db.execute(
        select(ArchitectureDependency.resource_type, ArchitectureDependency.dependency_type)
        .where(ArchitectureDependency.architecture_id == architecture_id)
    )
    existing_pairs = set(existing_rows.all())

    for resource_type, dependency_types in DEFAULT_DEPENDENCIES.items():
        for dependency_type in dependency_types:
            key = (resource_type, dependency_type)
            if key in existing_pairs:
                continue
            db.add(
                ArchitectureDependency(
                    architecture_id=architecture_id,
                    resource_type=resource_type,
                    dependency_type=dependency_type,
                    required=True,
                    auto_create_allowed=True,
                    notes=None,
                    properties={},
                )
            )


def resolve_requested_subscription(
    subscriptions: list[AzureSubscription],
    requested_subscription: str | None,
) -> AzureSubscription | None:
    requested = str(requested_subscription or "").strip()
    if not requested:
        return None

    try:
        requested_uuid = UUID(requested)
    except ValueError:
        requested_uuid = None

    for item in subscriptions:
        if requested_uuid is not None and item.id == requested_uuid:
            return item

    requested_lower = requested.lower()
    for item in subscriptions:
        external_id = str(item.subscription_id or "").strip().lower()
        if external_id and external_id == requested_lower:
            return item

    raise HTTPException(status_code=404, detail="Subscription not found in architecture scope")


async def resolve_requested_subscription_scope(
    request: Request,
    payload: MonitoringRequest | UnusedResourceRequest | None,
) -> str | None:
    # Prefer typed payload when available, but fall back to raw body/query to tolerate stale clients/schemas.
    payload_value = getattr(payload, "subscription_id", None) if payload is not None else None
    if payload_value:
        value = str(payload_value).strip()
        if value:
            return value

    try:
        body = await request.json()
    except Exception:
        body = None

    if isinstance(body, dict):
        body_value = body.get("subscription_id")
        if body_value:
            value = str(body_value).strip()
            if value:
                return value

    query_value = str(request.query_params.get("subscription_id") or "").strip()
    return query_value or None


def scope_resource_groups_by_subscription(
    groups: list[AzureResourceGroup],
    subscription: AzureSubscription | None,
) -> list[AzureResourceGroup]:
    if subscription is None:
        return groups
    return [item for item in groups if item.subscription_id == subscription.id]


def scope_resources_by_subscription(
    resources: list[ArchitectureResource],
    groups: list[AzureResourceGroup],
    subscription: AzureSubscription | None,
) -> list[ArchitectureResource]:
    if subscription is None:
        return resources

    group_ids = {item.id for item in groups}
    selected_external_id = str(subscription.subscription_id or "").strip().lower()
    selected_db_id = str(subscription.id)

    scoped: list[ArchitectureResource] = []
    for resource in resources:
        if resource.resource_group_id and resource.resource_group_id in group_ids:
            scoped.append(resource)
            continue

        props = resource.properties if isinstance(resource.properties, dict) else {}

        db_subscription_hint = str(props.get("subscription_id") or "").strip()
        if db_subscription_hint and db_subscription_hint == selected_db_id:
            scoped.append(resource)
            continue

        external_subscription_hint = str(props.get("azure_subscription_id") or "").strip().lower()
        if selected_external_id and external_subscription_hint == selected_external_id:
            scoped.append(resource)

    return scoped


def validate_relationship_rule(source_type: str, target_type: str, relationship_type: str) -> tuple[bool, str | None]:
    result = classify_relationship_rule(source_type, target_type, relationship_type)
    return result["valid"], result["reason"]


@router.get("", response_model=list[ArchitectureRead])
async def list_architectures(project: str | None = None, environment: str | None = None,
                             db: AsyncSession = Depends(get_db)):
    query = select(Architecture).where(Architecture.client_id == db.info["client_id"])
    if project is not None:
        query = query.where(Architecture.project == project.strip())
    if environment is not None:
        query = query.where(Architecture.environment == environment.strip())
    result = await db.execute(query.order_by(Architecture.created_at.desc()))
    return list(result.scalars().all())

@router.post("", response_model=ArchitectureRead, status_code=201)
async def create_architecture(payload: ArchitectureCreate, db: AsyncSession = Depends(get_db)):
    if payload.provider != "azure":
        raise HTTPException(422, "Only Azure architectures are supported")
    if payload.status != "draft":
        raise HTTPException(422, "New designs must start as drafts")
    values = payload.model_dump()
    values["project"] = payload.project.strip() if payload.project else None
    values["environment"] = payload.environment.strip()
    item = Architecture(client_id=db.info["client_id"], **values)
    db.add(item)
    await db.flush()
    await ensure_default_dependencies(db, item.id)
    await db.commit()
    await db.refresh(item)
    return item

@router.get("/{architecture_id}", response_model=ArchitectureRead)
async def get_architecture(architecture_id: UUID, db: AsyncSession = Depends(get_db)):
    return await get_architecture_or_404(db, architecture_id)

@router.put("/{architecture_id}", response_model=ArchitectureRead)
async def update_architecture(architecture_id: UUID, payload: ArchitectureUpdate, db: AsyncSession = Depends(get_db)):
    item = await get_architecture_or_404(db, architecture_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("provider", "azure") != "azure":
        raise HTTPException(422, "Only Azure architectures are supported")
    if "status" in changes:
        raise HTTPException(422, "Use the design status endpoint to transition this design")
    if any(field in changes and changes[field] is None for field in ("name", "environment", "graph_data")):
        raise HTTPException(422, "Name, environment and graph data cannot be null")
    for field in ("project", "environment"):
        if changes.get(field):
            changes[field] = changes[field].strip()
    for key, value in changes.items():
        setattr(item, key, value)
    await db.commit(); await db.refresh(item); return item

@router.delete("/{architecture_id}", status_code=204)
async def delete_architecture(architecture_id: UUID, db: AsyncSession = Depends(get_db)):
    item = await get_architecture_or_404(db, architecture_id)
    await db.delete(item); await db.commit()

@router.get("/{architecture_id}/resources", response_model=list[ResourceRead])
async def list_resources(architecture_id: UUID, db: AsyncSession = Depends(get_db)):
    await get_architecture_or_404(db, architecture_id)
    result = await db.execute(select(ArchitectureResource).where(ArchitectureResource.architecture_id == architecture_id).order_by(ArchitectureResource.created_at))
    return list(result.scalars().all())

@router.post("/{architecture_id}/resources", response_model=ResourceRead, status_code=201)
async def create_resource(architecture_id: UUID, payload: ResourceCreate, db: AsyncSession = Depends(get_db)):
    await get_architecture_or_404(db, architecture_id)
    await validate_resource_group_ownership(db, architecture_id, payload.resource_group_id)
    if payload.parent_resource_id is not None:
        parent = await db.scalar(select(ArchitectureResource).where(
            ArchitectureResource.id == payload.parent_resource_id, ArchitectureResource.architecture_id == architecture_id
        ))
        if not parent:
            raise HTTPException(status_code=404, detail="Parent resource not found")

    if payload.resource_type not in CATALOG_BY_RESOURCE_TYPE:
        raise HTTPException(status_code=400, detail="Unsupported resource type")

    catalog_item = CATALOG_BY_RESOURCE_TYPE[payload.resource_type]
    payload_data = payload.model_dump()
    if not payload_data.get("azure_resource_type"):
        payload_data["azure_resource_type"] = catalog_item["azure_provider_type"]

    item = ArchitectureResource(architecture_id=architecture_id, **payload_data)
    db.add(item); await db.commit(); await db.refresh(item); return item

@router.put("/{architecture_id}/resources/{resource_id}", response_model=ResourceRead)
async def update_resource(architecture_id: UUID, resource_id: UUID, payload: ResourceUpdate, db: AsyncSession = Depends(get_db)):
    item = await db.get(ArchitectureResource, resource_id)
    if not item or item.architecture_id != architecture_id: raise HTTPException(404, "Resource not found")
    if "resource_group_id" in payload.model_dump(exclude_unset=True):
        await validate_resource_group_ownership(db, architecture_id, payload.resource_group_id)
    payload_data = payload.model_dump(exclude_unset=True)
    if "parent_resource_id" in payload_data:
        parent_resource_id = payload_data["parent_resource_id"]
        if parent_resource_id == resource_id:
            raise HTTPException(status_code=400, detail="A resource cannot be its own parent")
        if parent_resource_id is not None:
            parent = await db.scalar(select(ArchitectureResource).where(
                ArchitectureResource.id == parent_resource_id, ArchitectureResource.architecture_id == architecture_id
            ))
            if not parent:
                raise HTTPException(status_code=404, detail="Parent resource not found")

    for key, value in payload_data.items():
        setattr(item, key, value)
    await db.commit(); await db.refresh(item); return item

@router.delete("/{architecture_id}/resources/{resource_id}", status_code=204)
async def delete_resource(architecture_id: UUID, resource_id: UUID, db: AsyncSession = Depends(get_db)):
    item = await db.get(ArchitectureResource, resource_id)
    if not item or item.architecture_id != architecture_id: raise HTTPException(404, "Resource not found")
    await db.delete(item); await db.commit()

@router.get("/{architecture_id}/relationships", response_model=list[RelationshipRead])
async def list_relationships(architecture_id: UUID, db: AsyncSession = Depends(get_db)):
    await get_architecture_or_404(db, architecture_id)
    result = await db.execute(select(ArchitectureRelationship).where(ArchitectureRelationship.architecture_id == architecture_id))
    return list(result.scalars().all())

@router.post("/{architecture_id}/relationships", response_model=RelationshipRead, status_code=201)
async def create_relationship(architecture_id: UUID, payload: RelationshipCreate, db: AsyncSession = Depends(get_db)):
    await get_architecture_or_404(db, architecture_id)
    source = await db.get(ArchitectureResource, payload.source_resource_id)
    target = await db.get(ArchitectureResource, payload.target_resource_id)
    if not source or not target or source.architecture_id != architecture_id or target.architecture_id != architecture_id:
        raise HTTPException(400, "Both resources must belong to the architecture")
    if source.id == target.id: raise HTTPException(400, "A resource cannot connect to itself")

    is_valid, reason = validate_relationship_rule(
        source.resource_type,
        target.resource_type,
        payload.relationship_type,
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail=reason)

    duplicate_result = await db.execute(
        select(
            exists().where(
                and_(
                    ArchitectureRelationship.architecture_id == architecture_id,
                    ArchitectureRelationship.source_resource_id == payload.source_resource_id,
                    ArchitectureRelationship.target_resource_id == payload.target_resource_id,
                    ArchitectureRelationship.relationship_type == payload.relationship_type,
                )
            )
        )
    )
    if duplicate_result.scalar_one():
        raise HTTPException(400, "Relationship already exists")

    item = ArchitectureRelationship(architecture_id=architecture_id, **payload.model_dump())
    db.add(item); await db.commit(); await db.refresh(item); return item


@router.post("/{architecture_id}/validate-relationship", response_model=RelationshipValidationRead)
async def validate_relationship(
    architecture_id: UUID,
    payload: RelationshipValidationRequest,
    db: AsyncSession = Depends(get_db),
):
    await get_architecture_or_404(db, architecture_id)
    source = await db.get(ArchitectureResource, payload.source_resource_id)
    target = await db.get(ArchitectureResource, payload.target_resource_id)
    if not source or not target or source.architecture_id != architecture_id or target.architecture_id != architecture_id:
        raise HTTPException(status_code=404, detail="Source or target resource not found")

    validation = classify_relationship_rule(
        source.resource_type,
        target.resource_type,
        payload.relationship_type,
    )
    return RelationshipValidationRead(
        valid=validation["valid"],
        reason=validation["reason"],
        status=validation["status"],
        relationship_kind=validation["kind"],
        reference="https://learn.microsoft.com/azure/architecture/",
    )

@router.delete("/{architecture_id}/relationships/{relationship_id}", status_code=204)
async def delete_relationship(architecture_id: UUID, relationship_id: UUID, db: AsyncSession = Depends(get_db)):
    item = await db.get(ArchitectureRelationship, relationship_id)
    if not item or item.architecture_id != architecture_id: raise HTTPException(404, "Relationship not found")
    await db.delete(item); await db.commit()


@router.get("/{architecture_id}/subscriptions", response_model=list[SubscriptionRead])
async def list_subscriptions(architecture_id: UUID, db: AsyncSession = Depends(get_db)):
    await get_architecture_or_404(db, architecture_id)
    result = await db.execute(select(AzureSubscription).where(AzureSubscription.architecture_id == architecture_id))
    return list(result.scalars().all())

@router.post("/{architecture_id}/subscriptions", response_model=SubscriptionRead, status_code=201)
async def create_subscription(
    architecture_id: UUID,
    payload: SubscriptionCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    await get_architecture_or_404(db, architecture_id)

    payload_data = payload.model_dump()
    external_subscription_id = str(payload_data.get("subscription_id") or "").strip().lower()
    if external_subscription_id:
        existing_result = await db.execute(
            select(AzureSubscription).where(
                AzureSubscription.architecture_id == architecture_id,
                AzureSubscription.subscription_id.is_not(None),
                AzureSubscription.subscription_id.ilike(external_subscription_id),
            )
        )
        existing = existing_result.scalars().first()
        if existing is not None:
            existing.name = payload_data.get("name") or existing.name
            existing.tenant_id = payload_data.get("tenant_id") or existing.tenant_id
            existing.environment = payload_data.get("environment") or existing.environment
            existing_props = existing.properties if isinstance(existing.properties, dict) else {}
            submitted_props = payload_data.get("properties") if isinstance(payload_data.get("properties"), dict) else {}
            existing_props.update(submitted_props)
            existing.properties = existing_props
            await db.commit()
            await db.refresh(existing)
            response.status_code = status.HTTP_200_OK
            return existing

    item = AzureSubscription(architecture_id=architecture_id, **payload_data)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item

@router.get("/{architecture_id}/resource-groups", response_model=list[ResourceGroupRead])
async def list_resource_groups(architecture_id: UUID, db: AsyncSession = Depends(get_db)):
    await get_architecture_or_404(db, architecture_id)
    result = await db.execute(select(AzureResourceGroup).where(AzureResourceGroup.architecture_id == architecture_id))
    return list(result.scalars().all())

@router.post("/{architecture_id}/resource-groups", response_model=ResourceGroupRead, status_code=201)
async def create_resource_group(architecture_id: UUID, payload: ResourceGroupCreate, db: AsyncSession = Depends(get_db)):
    await get_architecture_or_404(db, architecture_id)
    await validate_subscription_ownership(db, architecture_id, payload.subscription_id)
    item = AzureResourceGroup(architecture_id=architecture_id, **payload.model_dump())
    db.add(item); await db.commit(); await db.refresh(item); return item


@router.put("/{architecture_id}/resource-groups/{resource_group_id}", response_model=ResourceGroupRead)
async def update_resource_group(
    architecture_id: UUID,
    resource_group_id: UUID,
    payload: ResourceGroupUpdate,
    db: AsyncSession = Depends(get_db),
):
    item = await db.get(AzureResourceGroup, resource_group_id)
    if not item or item.architecture_id != architecture_id:
        raise HTTPException(404, "Resource group not found")

    if "subscription_id" in payload.model_dump(exclude_unset=True):
        await validate_subscription_ownership(db, architecture_id, payload.subscription_id)

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/{architecture_id}/resource-groups/{resource_group_id}", status_code=204)
async def delete_resource_group(architecture_id: UUID, resource_group_id: UUID, db: AsyncSession = Depends(get_db)):
    item = await db.get(AzureResourceGroup, resource_group_id)
    if not item or item.architecture_id != architecture_id:
        raise HTTPException(404, "Resource group not found")

    attached_resources = await db.execute(
        select(ArchitectureResource.id)
        .where(ArchitectureResource.architecture_id == architecture_id)
        .where(ArchitectureResource.resource_group_id == resource_group_id)
        .limit(1)
    )
    if attached_resources.scalar_one_or_none() is not None:
        raise HTTPException(400, "Resource group still contains resources")

    await db.delete(item)
    await db.commit()

@router.get("/{architecture_id}/dependencies", response_model=list[DependencyRead])
async def list_dependencies(architecture_id: UUID, db: AsyncSession = Depends(get_db)):
    await get_architecture_or_404(db, architecture_id)
    result = await db.execute(select(ArchitectureDependency).where(ArchitectureDependency.architecture_id == architecture_id))
    return list(result.scalars().all())


@router.post("/{architecture_id}/discover-resources", response_model=AzureDiscoveryRead)
async def discover_azure_resources(
    architecture_id: UUID,
    payload: AzureDiscoveryRequest,
    db: AsyncSession = Depends(get_db),
):
    await get_architecture_or_404(db, architecture_id)

    subscription = await db.get(AzureSubscription, payload.subscription_id)
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    if subscription.architecture_id != architecture_id:
        raise HTTPException(status_code=400, detail="Subscription must belong to the architecture")

    if not subscription.subscription_id:
        return AzureDiscoveryRead(
            success=False,
            connection_state="not_configured",
            message="Selected subscription is missing Azure subscription_id",
            architecture_id=architecture_id,
            subscription_id=subscription.id,
        )

    adapter = AzureResourceDiscoveryAdapter()
    discovered = await adapter.discover_subscription_resources(subscription_id=subscription.subscription_id)

    if not discovered.get("success"):
        return AzureDiscoveryRead(
            success=False,
            connection_state=str(discovered.get("connection_state") or "azure_api_failure"),
            message=str(discovered.get("error") or "Azure discovery failed"),
            architecture_id=architecture_id,
            subscription_id=subscription.id,
        )

    service = AzureResourceDiscoveryService()
    summary = await service.sync_discovered_resources(
        architecture_id=architecture_id,
        subscription=subscription,
        discovered=discovered,
        db=db,
        resource_model=ArchitectureResource,
        resource_group_model=AzureResourceGroup,
    )

    discovered_subscription = discovered.get("subscription") if isinstance(discovered.get("subscription"), dict) else {}
    discovered_subscription_id = str(discovered_subscription.get("id") or "").strip() or None
    discovered_subscription_name = str(discovered_subscription.get("name") or "").strip() or None
    discovered_subscription_state = str(discovered_subscription.get("state") or "").strip() or None

    if discovered_subscription_id:
        subscription.subscription_id = discovered_subscription_id
    if discovered_subscription_name:
        subscription.name = discovered_subscription_name
    props = dict(subscription.properties) if isinstance(subscription.properties, dict) else {}
    props.update(
        {
            "discovery_last_sync_at": datetime.now(timezone.utc).isoformat(),
            "discovered_subscription_state": discovered_subscription_state,
        }
    )
    subscription.properties = props
    await db.commit()
    await db.refresh(subscription)

    return AzureDiscoveryRead(
        success=True,
        connection_state="configured_connected",
        message="Discovery completed",
        architecture_id=architecture_id,
        subscription_id=subscription.id,
        discovered_subscription_id=discovered_subscription_id,
        discovered_subscription_name=discovered_subscription_name,
        discovered_subscription_state=discovered_subscription_state,
        resource_groups_discovered=summary["resource_groups_discovered"],
        resources_discovered=summary["resources_discovered"],
        resource_groups_created=summary["resource_groups_created"],
        resource_groups_updated=summary["resource_groups_updated"],
        resources_created=summary["resources_created"],
        resources_updated=summary["resources_updated"],
        hierarchy_links_updated=summary["hierarchy_links_updated"],
        unsupported_resources=summary["unsupported_resources"],
        skipped_without_group=summary["skipped_without_group"],
        normalized_resources=summary["normalized_resources"],
    )


@router.post("/{architecture_id}/cost-estimate", response_model=ArchitectureCostEstimateRead)
async def estimate_architecture_cost(
    architecture_id: UUID,
    payload: CostEstimateRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    architecture = await get_architecture_or_404(db, architecture_id)

    resources_result = await db.execute(
        select(ArchitectureResource)
        .where(ArchitectureResource.architecture_id == architecture_id)
        .order_by(ArchitectureResource.created_at)
    )
    resources = list(resources_result.scalars().all())

    groups_result = await db.execute(
        select(AzureResourceGroup)
        .where(AzureResourceGroup.architecture_id == architecture_id)
        .order_by(AzureResourceGroup.created_at)
    )
    groups = list(groups_result.scalars().all())

    subs_result = await db.execute(
        select(AzureSubscription)
        .where(AzureSubscription.architecture_id == architecture_id)
        .order_by(AzureSubscription.created_at)
    )
    subscriptions = list(subs_result.scalars().all())

    service = CostEstimationService()
    return await service.estimate_architecture_cost(
        architecture=architecture,
        resources=resources,
        resource_groups=groups,
        subscriptions=subscriptions,
        region_override=payload.region if payload else None,
    )


@router.post("/{architecture_id}/actual-cost", response_model=ArchitectureActualCostRead)
async def get_architecture_actual_cost(
    architecture_id: UUID,
    payload: ActualCostRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    architecture = await get_architecture_or_404(db, architecture_id)

    subs_result = await db.execute(
        select(AzureSubscription)
        .where(AzureSubscription.architecture_id == architecture_id)
        .order_by(AzureSubscription.created_at)
    )
    subscriptions = list(subs_result.scalars().all())

    service = CostEstimationService()
    return await service.get_architecture_actual_cost(
        architecture=architecture,
        subscriptions=subscriptions,
        requested_subscription_id=payload.subscription_id if payload else None,
        start_date=payload.start_date if payload else None,
        end_date=payload.end_date if payload else None,
    )


@router.post("/{architecture_id}/resources/{resource_id}/monitoring", response_model=ResourceMonitoringRead)
async def get_resource_monitoring(
    architecture_id: UUID,
    resource_id: UUID,
    payload: MonitoringRequest | None = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    architecture = await get_architecture_or_404(db, architecture_id)

    resource = await db.get(ArchitectureResource, resource_id)
    if not resource or resource.architecture_id != architecture_id:
        raise HTTPException(status_code=404, detail="Resource not found")

    groups_result = await db.execute(
        select(AzureResourceGroup)
        .where(AzureResourceGroup.architecture_id == architecture_id)
    )
    groups = list(groups_result.scalars().all())

    subs_result = await db.execute(
        select(AzureSubscription)
        .where(AzureSubscription.architecture_id == architecture_id)
    )
    subscriptions = list(subs_result.scalars().all())

    request_payload = payload or MonitoringRequest()
    requested_subscription = await resolve_requested_subscription_scope(request, payload)
    selected_subscription = resolve_requested_subscription(subscriptions, requested_subscription)
    scoped_groups = scope_resource_groups_by_subscription(groups, selected_subscription)
    scoped_resources = scope_resources_by_subscription([resource], scoped_groups, selected_subscription)
    if selected_subscription is not None and not scoped_resources:
        raise HTTPException(status_code=404, detail="Resource not found in selected subscription scope")

    start_time, end_time = request_payload.resolved_window()

    service = MonitoringService()
    return await service.monitor_resource(
        architecture=architecture,
        resource=resource,
        resource_groups=scoped_groups,
        subscriptions=[selected_subscription] if selected_subscription is not None else subscriptions,
        start_time=start_time,
        end_time=end_time,
        interval=request_payload.interval,
    )


@router.post("/{architecture_id}/monitoring-summary", response_model=ArchitectureMonitoringSummaryRead)
async def get_architecture_monitoring_summary(
    architecture_id: UUID,
    payload: MonitoringRequest | None = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    architecture = await get_architecture_or_404(db, architecture_id)

    resources_result = await db.execute(
        select(ArchitectureResource)
        .where(ArchitectureResource.architecture_id == architecture_id)
        .order_by(ArchitectureResource.created_at)
    )
    resources = list(resources_result.scalars().all())

    groups_result = await db.execute(
        select(AzureResourceGroup)
        .where(AzureResourceGroup.architecture_id == architecture_id)
    )
    groups = list(groups_result.scalars().all())

    subs_result = await db.execute(
        select(AzureSubscription)
        .where(AzureSubscription.architecture_id == architecture_id)
    )
    subscriptions = list(subs_result.scalars().all())

    request_payload = payload or MonitoringRequest()
    requested_subscription = await resolve_requested_subscription_scope(request, payload)
    selected_subscription = resolve_requested_subscription(subscriptions, requested_subscription)
    scoped_groups = scope_resource_groups_by_subscription(groups, selected_subscription)
    scoped_resources = scope_resources_by_subscription(resources, scoped_groups, selected_subscription)

    start_time, end_time = request_payload.resolved_window()

    service = MonitoringService()
    return await service.monitor_architecture(
        architecture=architecture,
        resources=scoped_resources,
        resource_groups=scoped_groups,
        subscriptions=[selected_subscription] if selected_subscription is not None else subscriptions,
        start_time=start_time,
        end_time=end_time,
        interval=request_payload.interval,
    )


@router.post("/{architecture_id}/incident-summary", response_model=MonitoringIncidentSummaryRead)
async def get_architecture_incident_summary(
    architecture_id: UUID,
    payload: MonitoringRequest | None = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    architecture = await get_architecture_or_404(db, architecture_id)

    resources_result = await db.execute(
        select(ArchitectureResource)
        .where(ArchitectureResource.architecture_id == architecture_id)
        .order_by(ArchitectureResource.created_at)
    )
    resources = list(resources_result.scalars().all())

    groups_result = await db.execute(
        select(AzureResourceGroup)
        .where(AzureResourceGroup.architecture_id == architecture_id)
    )
    groups = list(groups_result.scalars().all())

    subs_result = await db.execute(
        select(AzureSubscription)
        .where(AzureSubscription.architecture_id == architecture_id)
    )
    subscriptions = list(subs_result.scalars().all())

    request_payload = payload or MonitoringRequest()
    requested_subscription = await resolve_requested_subscription_scope(request, payload)
    selected_subscription = resolve_requested_subscription(subscriptions, requested_subscription)
    scoped_groups = scope_resource_groups_by_subscription(groups, selected_subscription)
    scoped_resources = scope_resources_by_subscription(resources, scoped_groups, selected_subscription)

    start_time, end_time = request_payload.resolved_window()

    service = MonitoringService()
    monitoring_summary = await service.monitor_architecture(
        architecture=architecture,
        resources=scoped_resources,
        resource_groups=scoped_groups,
        subscriptions=[selected_subscription] if selected_subscription is not None else subscriptions,
        start_time=start_time,
        end_time=end_time,
        interval=request_payload.interval,
    )

    workflow = MonitoringAlertIncidentWorkflow()
    return await workflow.sync_from_monitoring(
        architecture_id=architecture.id,
        monitoring_summary=monitoring_summary,
        resources=scoped_resources,
        resource_groups=scoped_groups,
        subscriptions=subscriptions,
        selected_subscription_id=selected_subscription.id if selected_subscription is not None else None,
        db=db,
    )


@router.post("/{architecture_id}/alerts-summary", response_model=MonitoringAlertSummaryRead)
async def get_architecture_alert_summary(
    architecture_id: UUID,
    payload: MonitoringRequest | None = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    architecture = await get_architecture_or_404(db, architecture_id)

    resources_result = await db.execute(
        select(ArchitectureResource)
        .where(ArchitectureResource.architecture_id == architecture_id)
        .order_by(ArchitectureResource.created_at)
    )
    resources = list(resources_result.scalars().all())

    groups_result = await db.execute(
        select(AzureResourceGroup)
        .where(AzureResourceGroup.architecture_id == architecture_id)
    )
    groups = list(groups_result.scalars().all())

    subs_result = await db.execute(
        select(AzureSubscription)
        .where(AzureSubscription.architecture_id == architecture_id)
    )
    subscriptions = list(subs_result.scalars().all())

    request_payload = payload or MonitoringRequest()
    requested_subscription = await resolve_requested_subscription_scope(request, payload)
    selected_subscription = resolve_requested_subscription(subscriptions, requested_subscription)
    scoped_groups = scope_resource_groups_by_subscription(groups, selected_subscription)
    scoped_resources = scope_resources_by_subscription(resources, scoped_groups, selected_subscription)

    start_time, end_time = request_payload.resolved_window()

    service = MonitoringService()
    monitoring_summary = await service.monitor_architecture(
        architecture=architecture,
        resources=scoped_resources,
        resource_groups=scoped_groups,
        subscriptions=[selected_subscription] if selected_subscription is not None else subscriptions,
        start_time=start_time,
        end_time=end_time,
        interval=request_payload.interval,
    )

    workflow = MonitoringAlertIncidentWorkflow()
    await workflow.sync_from_monitoring(
        architecture_id=architecture.id,
        monitoring_summary=monitoring_summary,
        resources=scoped_resources,
        resource_groups=scoped_groups,
        subscriptions=subscriptions,
        selected_subscription_id=selected_subscription.id if selected_subscription is not None else None,
        db=db,
    )
    return await workflow.build_alert_summary(
        architecture_id=architecture.id,
        selected_subscription_id=selected_subscription.id if selected_subscription is not None else None,
        db=db,
    )


@router.post("/{architecture_id}/unused-resources", response_model=UnusedResourceSummaryRead)
async def get_architecture_unused_resources(
    architecture_id: UUID,
    payload: UnusedResourceRequest | None = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    architecture = await get_architecture_or_404(db, architecture_id)

    resources_result = await db.execute(
        select(ArchitectureResource)
        .where(ArchitectureResource.architecture_id == architecture_id)
        .order_by(ArchitectureResource.created_at)
    )
    resources = list(resources_result.scalars().all())

    groups_result = await db.execute(
        select(AzureResourceGroup)
        .where(AzureResourceGroup.architecture_id == architecture_id)
    )
    groups = list(groups_result.scalars().all())

    subs_result = await db.execute(
        select(AzureSubscription)
        .where(AzureSubscription.architecture_id == architecture_id)
    )
    subscriptions = list(subs_result.scalars().all())

    request_payload = payload or UnusedResourceRequest()
    requested_subscription = await resolve_requested_subscription_scope(request, payload)
    selected_subscription = resolve_requested_subscription(subscriptions, requested_subscription)
    scoped_groups = scope_resource_groups_by_subscription(groups, selected_subscription)
    scoped_resources = scope_resources_by_subscription(resources, scoped_groups, selected_subscription)

    azure_status = await SettingsService().get_azure_status(db=db)

    service = MonitoringService()
    return await service.detect_unused_resources(
        architecture=architecture,
        resources=scoped_resources,
        lookback_days=request_payload.lookback_days,
        azure_connection_state=azure_status.connection_state,
        azure_connection_message=azure_status.message,
    )


@router.get("/{architecture_id}/incidents", response_model=list[MonitoringIncidentDetailRead])
async def list_architecture_incidents(
    architecture_id: UUID,
    subscription_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    await get_architecture_or_404(db, architecture_id)
    subs_result = await db.execute(
        select(AzureSubscription)
        .where(AzureSubscription.architecture_id == architecture_id)
    )
    subscriptions = list(subs_result.scalars().all())
    selected_subscription = resolve_requested_subscription(subscriptions, subscription_id)

    workflow = MonitoringAlertIncidentWorkflow()
    rows = await workflow.list_incidents(
        architecture_id=architecture_id,
        selected_subscription_id=selected_subscription.id if selected_subscription is not None else None,
        db=db,
    )
    items: list[MonitoringIncidentDetailRead] = []
    for row in rows:
        detail = await workflow.get_incident_detail(
            architecture_id=architecture_id,
            incident_id=UUID(row.incident_id),
            db=db,
        )
        if detail:
            items.append(detail)
    return items


@router.get("/{architecture_id}/incidents/{incident_id}", response_model=MonitoringIncidentDetailRead)
async def get_architecture_incident_detail(
    architecture_id: UUID,
    incident_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    await get_architecture_or_404(db, architecture_id)
    workflow = MonitoringAlertIncidentWorkflow()
    detail = await workflow.get_incident_detail(
        architecture_id=architecture_id,
        incident_id=incident_id,
        db=db,
    )
    if not detail:
        raise HTTPException(status_code=404, detail="Incident not found")
    return detail


@router.put("/{architecture_id}/incidents/{incident_id}/status", response_model=MonitoringIncidentDetailRead)
async def update_architecture_incident_status(
    architecture_id: UUID,
    incident_id: UUID,
    payload: MonitoringIncidentStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    await get_architecture_or_404(db, architecture_id)
    workflow = MonitoringAlertIncidentWorkflow()
    detail = await workflow.update_incident_status(
        architecture_id=architecture_id,
        incident_id=incident_id,
        payload=payload,
        db=db,
    )
    if not detail:
        raise HTTPException(status_code=404, detail="Incident not found")
    return detail


@router.post("/{architecture_id}/governance-summary", response_model=GovernanceComplianceSummaryRead)
async def get_architecture_governance_summary(
    architecture_id: UUID,
    payload: GovernanceComplianceRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    architecture = await get_architecture_or_404(db, architecture_id)

    resources_result = await db.execute(
        select(ArchitectureResource)
        .where(ArchitectureResource.architecture_id == architecture_id)
        .order_by(ArchitectureResource.created_at)
    )
    resources = list(resources_result.scalars().all())

    adapter = GovernanceComplianceAdapter()
    request_payload = payload or GovernanceComplianceRequest()
    frameworks = adapter.resolve_frameworks(
        graph_data=architecture.graph_data,
        requested_frameworks=request_payload.frameworks,
    )

    azure_status = await SettingsService().get_azure_status(db=db)

    return adapter.build_summary(
        architecture_id=str(architecture.id),
        resources=resources,
        frameworks=frameworks,
        default_region=architecture.default_region,
        azure_connection_state=azure_status.connection_state,
        azure_connection_message=azure_status.message,
    )


@router.post("/{architecture_id}/security-summary", response_model=GovernanceSecuritySummaryRead)
async def get_architecture_security_summary(
    architecture_id: UUID,
    payload: GovernanceSecurityRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    _ = payload
    architecture = await get_architecture_or_404(db, architecture_id)

    resources_result = await db.execute(
        select(ArchitectureResource)
        .where(ArchitectureResource.architecture_id == architecture_id)
        .order_by(ArchitectureResource.created_at)
    )
    resources = list(resources_result.scalars().all())

    relationships_result = await db.execute(
        select(ArchitectureRelationship)
        .where(ArchitectureRelationship.architecture_id == architecture_id)
    )
    relationships = list(relationships_result.scalars().all())

    adapter = GovernanceSecurityAdapter()
    return adapter.build_summary(
        architecture_id=str(architecture.id),
        resources=resources,
        relationships=relationships,
    )


@router.post("/{architecture_id}/intelligence-analysis", response_model=IntelligenceAnalysisRead)
async def get_architecture_intelligence_analysis(
    architecture_id: UUID,
    payload: IntelligenceAnalysisRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    requested_provider = payload.provider if payload else None
    architecture = await get_architecture_or_404(db, architecture_id)

    resources_result = await db.execute(
        select(ArchitectureResource)
        .where(ArchitectureResource.architecture_id == architecture_id)
        .order_by(ArchitectureResource.created_at)
    )
    resources = list(resources_result.scalars().all())

    relationships_result = await db.execute(
        select(ArchitectureRelationship)
        .where(ArchitectureRelationship.architecture_id == architecture_id)
    )
    relationships = list(relationships_result.scalars().all())

    groups_result = await db.execute(
        select(AzureResourceGroup)
        .where(AzureResourceGroup.architecture_id == architecture_id)
        .order_by(AzureResourceGroup.created_at)
    )
    resource_groups = list(groups_result.scalars().all())

    subscriptions_result = await db.execute(
        select(AzureSubscription)
        .where(AzureSubscription.architecture_id == architecture_id)
        .order_by(AzureSubscription.created_at)
    )
    subscriptions = list(subscriptions_result.scalars().all())

    service = IntelligenceService()
    try:
        return await service.analyze_architecture(
            architecture=architecture,
            resources=resources,
            relationships=relationships,
            resource_groups=resource_groups,
            subscriptions=subscriptions,
            requested_provider=requested_provider,
            db=db,
        )
    except Exception:
        return IntelligenceAnalysisRead(
            architecture_id=str(architecture.id),
            status="error",
            provider="deterministic_fallback",
            error_state="provider_error",
            state="error",
            overall_assessment="Intelligence analysis failed.",
            message="Intelligence analysis failed with a controlled provider error state.",
        )
