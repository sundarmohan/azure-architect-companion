import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

import httpx
from azure.identity.aio import ClientSecretCredential
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.architecture.azure_discovery import AzureResourceDiscoveryAdapter
from .azure import azure_failure, confirm_active_connection, connection_values, request_correlation_id, select_subscription
from .models import AuditEvent, AzureConnection, AzureInventorySnapshot
from .routes import client_access, get_db

router = APIRouter()
ARM = "https://management.azure.com"


class ResourceGroup(BaseModel):
    id: str
    name: str
    location: str


class Resource(ResourceGroup):
    type: str
    resource_group: str | None
    parent_azure_resource_id: str | None = None
    properties: dict = Field(default_factory=dict)


class InventoryRead(BaseModel):
    subscription_id: UUID | None
    status: str
    failure_reason: str | None = None
    failure_stage: str | None = None
    correlation_id: str | None = None
    showing_retained_data: bool = False
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    resources: list[Resource] = Field(default_factory=list)
    resource_groups: list[ResourceGroup] = Field(default_factory=list)


def inventory_read(snapshot, subscription_id, request=None):
    if not snapshot:
        status = "not_synced" if subscription_id else "not_configured"
        return InventoryRead(subscription_id=subscription_id, status=status,
                             correlation_id=request_correlation_id(request))
    return InventoryRead(
        subscription_id=subscription_id, status=snapshot.status, failure_reason=snapshot.failure_reason,
        failure_stage=snapshot.failure_stage, correlation_id=request_correlation_id(request),
        showing_retained_data=bool(snapshot.last_success_at and snapshot.status != "synced"),
        last_attempt_at=snapshot.last_attempt_at,
        last_success_at=snapshot.last_success_at, resources=snapshot.resources, resource_groups=snapshot.resource_groups,
    )


def summarize_items(items, subscription_id, *, resources):
    prefix = f"/subscriptions/{subscription_id}/"
    indexed = {}
    for item in items:
        arm_id = item.get("id")
        if not isinstance(arm_id, str) or not arm_id.casefold().startswith(prefix):
            continue
        parts = arm_id.split("/")
        summary = {"id": arm_id, "name": str(item.get("name") or ""), "location": str(item.get("location") or "")}
        if resources:
            summary["type"] = str(item.get("type") or "")
            summary["resource_group"] = parts[4] if len(parts) > 4 and parts[3].casefold() == "resourcegroups" else None
            azure_type = summary["type"].casefold()
            summary["parent_azure_resource_id"] = AzureResourceDiscoveryAdapter()._extract_parent_resource_id(
                arm_id, azure_type,
            )
            raw = item.get("properties") if isinstance(item.get("properties"), dict) else {}
            allowlisted = {}
            for key in ("serverFarmId", "virtualNetworkSubnetId"):
                if isinstance(raw.get(key), str):
                    allowlisted[key] = raw[key]
            site_config = raw.get("siteConfig") if isinstance(raw.get("siteConfig"), dict) else {}
            if isinstance(site_config.get("virtualNetworkSubnetId"), str):
                allowlisted["siteConfig"] = {"virtualNetworkSubnetId": site_config["virtualNetworkSubnetId"]}
            subnet = raw.get("subnet") if isinstance(raw.get("subnet"), dict) else {}
            if isinstance(subnet.get("id"), str):
                allowlisted["subnet"] = {"id": subnet["id"]}
            connections = []
            if isinstance(raw.get("privateLinkServiceConnections"), list):
                for connection in raw["privateLinkServiceConnections"][:50]:
                    props = connection.get("properties") if isinstance(connection, dict) else None
                    if isinstance(props, dict) and isinstance(props.get("privateLinkServiceId"), str):
                        connections.append({"properties": {"privateLinkServiceId": props["privateLinkServiceId"]}})
            if connections:
                allowlisted["privateLinkServiceConnections"] = connections
            summary["properties"] = allowlisted
        indexed[arm_id.casefold()] = summary
    return [indexed[key] for key in sorted(indexed)]


def failure_details(result):
    state = {
        "authentication_failure": "authentication_failure",
        "permission_failure": "permission_failure",
    }.get(result.get("connection_state"), "provider_error")
    reason = result.get("failure_reason") or state
    return state, reason


@dataclass
class InventoryCollection:
    status: str
    failure_reason: str | None = None
    groups: list[dict] = field(default_factory=list)
    resources: list[dict] = field(default_factory=list)
    failure_stage: str | None = None


async def collect_inventory(values, subscription_id):
    adapter = AzureResourceDiscoveryAdapter()
    base = f"{ARM}/subscriptions/{subscription_id}"
    try:
        async with ClientSecretCredential(
            tenant_id=values["tenant_id"], client_id=values["client_id"], client_secret=values["client_secret"]
        ) as credential:
            token = await credential.get_token(f"{ARM}/.default")
    except Exception as error:
        state, stage, reason = azure_failure(error, "token_acquisition")
        return InventoryCollection(status=state, failure_reason=reason, failure_stage=stage)
    async with httpx.AsyncClient(timeout=10) as http:
        headers = {"Authorization": f"Bearer {token.token}"}
        groups = await adapter._collect_paged(
            client=http, url=f"{base}/resourcegroups", api_version=adapter.RESOURCE_GROUPS_API_VERSION, headers=headers
        )
        if not groups["success"]:
            state, reason = failure_details(groups)
            return InventoryCollection(status=state, failure_reason=reason, failure_stage="resource_groups")
        resources = await adapter._collect_paged(
            client=http, url=f"{base}/resources", api_version=adapter.RESOURCES_API_VERSION, headers=headers
        )
        if not resources["success"]:
            _state, reason = failure_details(resources)
            return InventoryCollection(
                status="partial_failure", failure_reason=reason, failure_stage="resources",
            )
    return InventoryCollection(
        "synced",
        groups=summarize_items(groups["items"], subscription_id, resources=False),
        resources=summarize_items(resources["items"], subscription_id, resources=True),
    )


@router.get("/inventory", response_model=InventoryRead)
async def read_inventory(request: Request, subscription_id: UUID | None = None,
                         client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db)):
    selected = select_subscription(await connection_values(db, client_id), subscription_id)
    snapshot = await db.get(AzureInventorySnapshot, (client_id, UUID(selected))) if selected else None
    return inventory_read(snapshot, selected, request)


@router.post("/inventory/refresh", response_model=InventoryRead)
async def refresh_inventory(request: Request, subscription_id: UUID | None = None,
                            client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db)):
    connection = await db.get(AzureConnection, client_id)
    values = await connection_values(db, client_id, connection) if connection else None
    selected = select_subscription(values, subscription_id)
    if not selected:
        return inventory_read(None, None, request)
    ciphertext = connection.ciphertext
    # Return the connection to the pool during the external request.
    await db.rollback()
    started = datetime.now(timezone.utc)
    try:
        async with asyncio.timeout(45):
            result = await collect_inventory(values, selected)
    except Exception as error:
        state, stage, reason = azure_failure(error, "inventory_collection")
        result = InventoryCollection(status=state, failure_reason=reason, failure_stage=stage)

    account = await confirm_active_connection(db, request, client_id, ciphertext)
    snapshot = await db.get(AzureInventorySnapshot, (client_id, UUID(selected)))
    if snapshot and snapshot.last_attempt_at > started:
        return inventory_read(snapshot, selected, request)
    if snapshot is None:
        snapshot = AzureInventorySnapshot(client_id=client_id, subscription_id=UUID(selected),
                                          resources=[], resource_groups=[])
        db.add(snapshot)
    snapshot.last_attempt_at = started
    snapshot.status = result.status
    snapshot.failure_reason = result.failure_reason
    snapshot.failure_stage = result.failure_stage
    if result.status == "synced":
        snapshot.last_success_at = datetime.now(timezone.utc)
        snapshot.resource_groups = result.groups
        snapshot.resources = result.resources
    db.add(AuditEvent(
        account_id=account.id, action="refresh_azure_inventory", client_id=client_id,
        target=selected, outcome="success" if result.status == "synced" else "failed",
    ))
    await db.commit()
    return inventory_read(snapshot, selected, request)
