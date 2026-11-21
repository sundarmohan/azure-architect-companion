import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

import httpx
from azure.core.exceptions import AzureError
from azure.identity.aio import ClientSecretCredential
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.access.azure import confirm_active_connection, connection_values, select_subscription
from app.domains.access.models import AuditEvent, AzureConnection, AzureInventorySnapshot
from .network import collect_network
from .observation_models import AzureObservation, AzureObservationSchedule
from .telemetry import collect_telemetry

ObservationKind = Literal["monitoring", "network"]
KINDS: tuple[ObservationKind, ...] = ("monitoring", "network")


@dataclass
class CollectionContext:
    subscription_id: UUID
    credentials: dict
    ciphertext: str
    resources: list[dict]
    inventory_exists: bool
    inventory_is_stale: bool


async def observation_context(db: AsyncSession, client_id: UUID, subscription_id: UUID | None):
    connection = await db.get(AzureConnection, client_id)
    values = await connection_values(db, client_id, connection) if connection else None
    selected = select_subscription(values, subscription_id)
    if selected is None:
        return None
    selected = UUID(selected)
    inventory = await db.get(AzureInventorySnapshot, (client_id, selected))
    prefix = f"/subscriptions/{selected}/"
    resources = [row for row in inventory.resources if str(row.get("id", "")).casefold().startswith(prefix)] if inventory else []
    return CollectionContext(
        selected, values, connection.ciphertext, resources,
        inventory is not None and inventory.last_success_at is not None,
        inventory is not None and inventory.status != "synced",
    )


async def collect_observations(context: CollectionContext, kinds: tuple[ObservationKind, ...]):
    if not context.inventory_exists:
        return {kind: ("inventory_required", {}, ["Refresh Azure Inventory to discover resources first."]) for kind in kinds}
    values = context.credentials
    limitations = ["Collection uses the last complete snapshot from Azure Inventory."]
    if context.inventory_is_stale:
        limitations.append("The last inventory refresh failed. The resource list may be stale.")

    async def collect_kind(kind, http, headers):
        try:
            async with asyncio.timeout(60):
                if kind == "monitoring":
                    status, result = await collect_telemetry(context.resources, http, headers)
                    return kind, (status, {"resources": result["resources"]}, limitations + result["limitations"])
                result = await collect_network(str(context.subscription_id), context.resources, http, headers)
                details = limitations + result.limitations
                if result.failure_reason:
                    details.append(f"Azure response status: {result.failure_reason.replace('_', ' ')}.")
                return kind, (result.status, {"resources": result.resources, "links": result.links}, details)
        except (httpx.HTTPError, TimeoutError, ValueError):
            return kind, ("provider_error", {}, limitations + ["Azure collection could not be completed."])

    try:
        async with asyncio.timeout(25):
            async with ClientSecretCredential(
                tenant_id=values["tenant_id"], client_id=values["client_id"], client_secret=values["client_secret"],
            ) as credential:
                token = await credential.get_token("https://management.azure.com/.default")
    except AzureError:
        return {kind: ("authentication_failure", {}, ["Azure authentication failed."]) for kind in kinds}
    except (httpx.HTTPError, TimeoutError):
        return {kind: ("provider_error", {}, ["Azure authentication did not complete."]) for kind in kinds}
    async with httpx.AsyncClient(timeout=8, follow_redirects=False) as http:
        headers = {"Authorization": f"Bearer {token.token}"}
        return dict(await asyncio.gather(*(collect_kind(kind, http, headers) for kind in kinds)))


async def refresh_observations(db: AsyncSession, client_id: UUID, subscription_id: UUID | None,
                               kinds: tuple[ObservationKind, ...], request: Request | None = None,
                               *, schedule_generation: UUID | None = None):
    context = await observation_context(db, client_id, subscription_id)
    if context is None:
        return {}
    key = (client_id, context.subscription_id)
    if request is None:
        schedule = await db.get(AzureObservationSchedule, key)
        if schedule is None or not schedule.enabled or schedule.generation != schedule_generation:
            return {}
    await db.rollback()
    started = datetime.now(timezone.utc)
    results = await collect_observations(context, kinds)
    if request:
        account = await confirm_active_connection(db, request, client_id, context.ciphertext)
        actor_id = account.id
    else:
        ciphertext = await db.scalar(select(AzureConnection.ciphertext).where(
            AzureConnection.client_id == client_id
        ).with_for_update())
        schedule = await db.get(AzureObservationSchedule, key)
        if (ciphertext != context.ciphertext or schedule is None or not schedule.enabled
                or schedule.generation != schedule_generation):
            return {}
        actor_id = None
    snapshots = {}
    for kind, (status, payload, limitations) in results.items():
        key = (client_id, context.subscription_id, kind)
        snapshot = await db.get(AzureObservation, key)
        if snapshot and snapshot.last_attempt_at > started:
            snapshots[kind] = snapshot
            continue
        if snapshot is None:
            snapshot = AzureObservation(client_id=client_id, subscription_id=context.subscription_id,
                                        kind=kind, payload={})
            db.add(snapshot)
        snapshot.last_attempt_at = started
        snapshot.status = status
        snapshot.limitations = limitations
        if status == "synced":
            snapshot.last_success_at = datetime.now(timezone.utc)
            snapshot.payload = payload
        elif status == "partial_failure" and snapshot.last_success_at is None:
            snapshot.payload = payload
        elif snapshot.payload:
            snapshot.limitations = [*limitations, "Displayed data is retained from an earlier collection."]
        db.add(AuditEvent(
            account_id=actor_id, client_id=client_id, action=f"refresh_azure_{kind}",
            target=str(context.subscription_id), outcome="success" if status == "synced" else "failed",
        ))
        snapshots[kind] = snapshot
    await db.commit()
    return snapshots
