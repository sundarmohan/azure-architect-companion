import asyncio
from datetime import datetime, timezone
from uuid import UUID

import httpx
from azure.core.exceptions import AzureError
from azure.identity.aio import ClientSecretCredential
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.architecture.azure_discovery import AzureResourceDiscoveryAdapter
from .azure import connection_values, select_subscription
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


class InventoryRead(BaseModel):
    subscription_id: UUID | None
    status: str
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    resources: list[Resource] = Field(default_factory=list)
    resource_groups: list[ResourceGroup] = Field(default_factory=list)


def inventory_read(snapshot, subscription_id):
    if not snapshot:
        status = "not_synced" if subscription_id else "not_configured"
        return InventoryRead(subscription_id=subscription_id, status=status)
    return InventoryRead(
        subscription_id=subscription_id, status=snapshot.status, last_attempt_at=snapshot.last_attempt_at,
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
        indexed[arm_id.casefold()] = summary
    return [indexed[key] for key in sorted(indexed)]


def failure_state(result):
    return {
        "authentication_failure": "authentication_failure",
        "permission_failure": "permission_failure",
    }.get(result.get("connection_state"), "provider_error")


async def collect_inventory(values, subscription_id):
    adapter = AzureResourceDiscoveryAdapter()
    base = f"{ARM}/subscriptions/{subscription_id}"
    async with ClientSecretCredential(
        tenant_id=values["tenant_id"], client_id=values["client_id"], client_secret=values["client_secret"]
    ) as credential:
        token = await credential.get_token(f"{ARM}/.default")
    async with httpx.AsyncClient(timeout=10) as http:
        headers = {"Authorization": f"Bearer {token.token}"}
        groups = await adapter._collect_paged(
            client=http, url=f"{base}/resourcegroups", api_version=adapter.RESOURCE_GROUPS_API_VERSION, headers=headers
        )
        if not groups["success"]:
            return failure_state(groups), [], []
        resources = await adapter._collect_paged(
            client=http, url=f"{base}/resources", api_version=adapter.RESOURCES_API_VERSION, headers=headers
        )
        if not resources["success"]:
            return "partial_failure", [], []
    return (
        "synced",
        summarize_items(groups["items"], subscription_id, resources=False),
        summarize_items(resources["items"], subscription_id, resources=True),
    )


@router.get("/inventory", response_model=InventoryRead)
async def read_inventory(subscription_id: UUID | None = None, client_id: UUID = Depends(client_access),
                         db: AsyncSession = Depends(get_db)):
    selected = select_subscription(await connection_values(db, client_id), subscription_id)
    snapshot = await db.get(AzureInventorySnapshot, (client_id, UUID(selected))) if selected else None
    return inventory_read(snapshot, selected)


@router.post("/inventory/refresh", response_model=InventoryRead)
async def refresh_inventory(request: Request, subscription_id: UUID | None = None,
                            client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db)):
    connection = await db.get(AzureConnection, client_id)
    values = await connection_values(db, client_id, connection) if connection else None
    selected = select_subscription(values, subscription_id)
    if not selected:
        return inventory_read(None, None)
    actor_id = request.state.account.id
    ciphertext = connection.ciphertext
    # Return the connection to the pool during the external request.
    await db.rollback()
    started = datetime.now(timezone.utc)
    try:
        async with asyncio.timeout(45):
            status, groups, resources = await collect_inventory(values, selected)
    except AzureError:
        status = "authentication_failure"
    except (httpx.HTTPError, ValueError, TimeoutError):
        status = "provider_error"

    active_ciphertext = await db.scalar(select(AzureConnection.ciphertext).where(
        AzureConnection.client_id == client_id
    ).with_for_update())
    if active_ciphertext != ciphertext:
        raise HTTPException(409, "Azure connection changed during refresh")
    snapshot = await db.get(AzureInventorySnapshot, (client_id, UUID(selected)))
    if snapshot and snapshot.last_attempt_at > started:
        return inventory_read(snapshot, selected)
    if snapshot is None:
        snapshot = AzureInventorySnapshot(client_id=client_id, subscription_id=UUID(selected),
                                          resources=[], resource_groups=[])
        db.add(snapshot)
    snapshot.last_attempt_at = started
    snapshot.status = status
    if status == "synced":
        snapshot.last_success_at = datetime.now(timezone.utc)
        snapshot.resource_groups = groups
        snapshot.resources = resources
    db.add(AuditEvent(
        account_id=actor_id, action="refresh_azure_inventory", client_id=client_id,
        target=selected, outcome="success" if status == "synced" else "failed",
    ))
    await db.commit()
    return inventory_read(snapshot, selected)
