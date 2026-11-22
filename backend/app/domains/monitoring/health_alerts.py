"""Acknowledgement of confirmed, saved Azure Resource Health observations."""

import json
from datetime import datetime, timezone
from hashlib import sha256
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.access.azure import connection_values, select_subscription
from app.domains.access.models import AzureConnection
from app.domains.access.routes import audit, client_access, get_db
from .observation_models import AzureHealthAcknowledgement, AzureObservation

router = APIRouter()


class HealthAlertRead(BaseModel):
    evidence_id: str
    acknowledged_at: datetime | None = None


def health_evidence(snapshot):
    """Identify findings in the last complete collection, including retained evidence."""
    if snapshot.kind != "monitoring" or snapshot.last_success_at is None:
        return {}
    collected_at = snapshot.last_success_at.astimezone(timezone.utc).isoformat()
    evidence = {}
    for resource in snapshot.payload.get("resources", []):
        resource_id = resource.get("id")
        health = resource.get("health")
        if not isinstance(resource_id, str) or not resource_id or resource.get("health_status") != "synced" or health not in {"degraded", "unavailable"}:
            continue
        parts = [resource_id.casefold(), health, collected_at]
        evidence[sha256(json.dumps(parts).encode()).hexdigest()] = resource
    return evidence


async def attach_health_alerts(db, snapshot, payload):
    evidence = health_evidence(snapshot)
    if not evidence:
        return payload
    rows = await db.scalars(select(AzureHealthAcknowledgement).where(
        AzureHealthAcknowledgement.client_id == snapshot.client_id,
        AzureHealthAcknowledgement.subscription_id == snapshot.subscription_id,
        AzureHealthAcknowledgement.evidence_id.in_(evidence),
    ))
    acknowledged = {row.evidence_id: row.acknowledged_at for row in rows}
    alerts = {resource["id"]: HealthAlertRead(evidence_id=evidence_id, acknowledged_at=acknowledged.get(evidence_id))
              for evidence_id, resource in evidence.items()}
    return {
        **payload,
        "resources": [{**item, "health_alert": alerts[item["id"]].model_dump(mode="json")}
                      if item.get("id") in alerts else item for item in payload.get("resources", [])],
    }


@router.put("/monitoring/health-alerts/{evidence_id}/acknowledgement", response_model=HealthAlertRead)
async def acknowledge_health_alert(request: Request, evidence_id: str = Path(pattern=r"^[a-f0-9]{64}$"),
                                   subscription_id: UUID | None = None, client_id: UUID = Depends(client_access),
                                   db: AsyncSession = Depends(get_db)):
    # Collection and connection updates take this same lock. Verify the exact
    # evidence while it is current, and never take evidence fields from the caller.
    connection = await db.scalar(select(AzureConnection).where(
        AzureConnection.client_id == client_id
    ).with_for_update())
    selected = select_subscription(await connection_values(db, client_id, connection) if connection else None,
                                   subscription_id)
    if not selected:
        raise HTTPException(404, "Azure subscription is not configured")
    selected_id = UUID(selected)
    key = (client_id, selected_id, evidence_id)
    existing = await db.get(AzureHealthAcknowledgement, key)
    if existing:
        return HealthAlertRead(evidence_id=evidence_id, acknowledged_at=existing.acknowledged_at)
    snapshot = await db.get(AzureObservation, (client_id, selected_id, "monitoring"))
    resource = health_evidence(snapshot).get(evidence_id) if snapshot else None
    if resource is None:
        raise HTTPException(409, "Health alert evidence is no longer available. Reload the saved snapshot.")

    row = await db.scalar(insert(AzureHealthAcknowledgement).values(
        client_id=client_id, subscription_id=selected_id, evidence_id=evidence_id,
        resource_id=resource["id"], health=resource["health"], collected_at=snapshot.last_success_at,
        actor_id=request.state.account.id,
    ).on_conflict_do_nothing().returning(AzureHealthAcknowledgement.acknowledged_at))
    if row is None:
        existing = await db.get(AzureHealthAcknowledgement, key)
        row = existing.acknowledged_at
    else:
        audit(db, "acknowledge_azure_health_alert", request.state.account, client_id, evidence_id)
    await db.commit()
    return HealthAlertRead(evidence_id=evidence_id, acknowledged_at=row)
