from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.access.azure import connection_values, select_subscription
from app.domains.access.models import AzureConnection
from app.domains.access.routes import audit, client_access, get_db
from .observation_models import AzureObservation, AzureSecurityTracking

router = APIRouter()


class TrackingWrite(BaseModel):
    status: Literal["open", "in_progress", "resolved", "accepted"]
    owner: str | None = Field(default=None, max_length=120)
    due_date: date | None = None


async def attach_tracking(db, snapshot, payload):
    if not snapshot or snapshot.kind != "security":
        return payload
    findings = payload.get("findings", [])
    if not findings:
        return payload
    rows = await db.scalars(select(AzureSecurityTracking).where(
        AzureSecurityTracking.client_id == snapshot.client_id,
        AzureSecurityTracking.subscription_id == snapshot.subscription_id,
        AzureSecurityTracking.finding_id.in_([item["id"] for item in findings]),
    ))
    tracking = {row.finding_id: TrackingWrite(status=row.status, owner=row.owner, due_date=row.due_date) for row in rows}
    return {**payload, "findings": [{**item, "tracking": tracking.get(item["id"])} for item in findings]}


@router.put("/findings/{finding_id}/tracking", response_model=TrackingWrite)
async def write_tracking(payload: TrackingWrite, request: Request, finding_id: str = Path(pattern=r"^[0-9a-f]{64}$"),
                         subscription_id: UUID | None = None, client_id: UUID = Depends(client_access),
                         db: AsyncSession = Depends(get_db)):
    connection = await db.scalar(select(AzureConnection).where(
        AzureConnection.client_id == client_id
    ).with_for_update())
    selected = select_subscription(await connection_values(db, client_id, connection) if connection else None,
                                   subscription_id)
    if not selected:
        raise HTTPException(404, "Finding not found")
    snapshot = await db.get(AzureObservation, (client_id, UUID(selected), "security"))
    if not snapshot or not any(item["id"] == finding_id for item in snapshot.payload.get("findings", [])):
        raise HTTPException(404, "Finding not found")
    if payload.owner is not None:
        payload.owner = payload.owner.strip() or None
    values = payload.model_dump()
    await db.execute(insert(AzureSecurityTracking).values(client_id=client_id, subscription_id=UUID(selected),
        finding_id=finding_id, **values).on_conflict_do_update(
            index_elements=[AzureSecurityTracking.client_id, AzureSecurityTracking.subscription_id,
                            AzureSecurityTracking.finding_id], set_=values,
        ))
    audit(db, "update_azure_security_tracking", request.state.account, client_id, finding_id)
    await db.commit()
    return payload
