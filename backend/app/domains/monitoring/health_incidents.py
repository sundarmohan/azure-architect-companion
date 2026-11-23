"""Client-scoped incident tracking for acknowledged Azure health evidence."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.access.azure import connection_values, select_subscription
from app.domains.access.routes import audit, client_access, get_db
from .observation_models import AzureHealthAcknowledgement, AzureHealthIncident

router = APIRouter()
IncidentStatus = Literal["open", "investigating", "resolved"]
PAGE_SIZE = 20


class IncidentRead(BaseModel):
    id: UUID
    evidence_id: str
    resource_id: str
    health: Literal["degraded", "unavailable"]
    collected_at: AwareDatetime
    acknowledged_at: AwareDatetime
    status: IncidentStatus
    owner: str | None
    rca_note: str | None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class IncidentPage(BaseModel):
    incidents: list[IncidentRead]
    has_next: bool


class IncidentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    status: IncidentStatus
    owner: str | None = Field(default=None, max_length=120)
    rca_note: str | None = Field(default=None, max_length=4000)
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def require_resolution_note(self):
        if self.status == "resolved" and not self.rca_note:
            raise ValueError("A resolution note is required")
        return self


async def selected_subscription(db, client_id, subscription_id):
    selected = select_subscription(await connection_values(db, client_id), subscription_id)
    return UUID(selected) if selected else None


def incident_read(incident, evidence):
    return IncidentRead(
        id=incident.id, evidence_id=incident.evidence_id, resource_id=evidence.resource_id,
        health=evidence.health, collected_at=evidence.collected_at, acknowledged_at=evidence.acknowledged_at,
        status=incident.status, owner=incident.owner, rca_note=incident.rca_note,
        created_at=incident.created_at, updated_at=incident.updated_at,
    )


@router.get("/monitoring/health-incidents", response_model=IncidentPage)
async def list_health_incidents(subscription_id: UUID | None = None, page: int = Query(default=1, ge=1, le=1000),
                                client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db)):
    selected = await selected_subscription(db, client_id, subscription_id)
    if selected is None:
        return IncidentPage(incidents=[], has_next=False)
    incident = AzureHealthIncident
    evidence = AzureHealthAcknowledgement
    rows = (await db.execute(select(incident, evidence).join(evidence, and_(
        incident.client_id == evidence.client_id, incident.subscription_id == evidence.subscription_id,
        incident.evidence_id == evidence.evidence_id,
    )).where(incident.client_id == client_id, incident.subscription_id == selected)
        .order_by(incident.created_at.desc(), incident.id).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE + 1))).all()
    return IncidentPage(incidents=[incident_read(incident, evidence) for incident, evidence in rows[:PAGE_SIZE]],
                        has_next=page < 1000 and len(rows) > PAGE_SIZE)


@router.put("/monitoring/health-alerts/{evidence_id}/incident", response_model=IncidentRead)
async def create_health_incident(request: Request, evidence_id: str = Path(pattern=r"^[a-f0-9]{64}$"),
                                 subscription_id: UUID | None = None, client_id: UUID = Depends(client_access),
                                 db: AsyncSession = Depends(get_db)):
    selected = await selected_subscription(db, client_id, subscription_id)
    evidence = await db.get(AzureHealthAcknowledgement, (client_id, selected, evidence_id)) if selected else None
    if evidence is None:
        raise HTTPException(404, "Acknowledged health evidence not found")
    incident = await db.scalar(insert(AzureHealthIncident).values(
        client_id=client_id, subscription_id=selected, evidence_id=evidence_id, status="open",
    ).on_conflict_do_nothing(constraint="uq_health_incident_evidence").returning(AzureHealthIncident))
    if incident is None:
        incident = (await db.scalars(select(AzureHealthIncident).where(
            AzureHealthIncident.client_id == client_id, AzureHealthIncident.subscription_id == selected,
            AzureHealthIncident.evidence_id == evidence_id,
        ))).one()
    else:
        audit(db, "create_azure_health_incident", request.state.account, client_id, str(incident.id))
    result = incident_read(incident, evidence)
    await db.commit()
    return result


@router.put("/monitoring/health-incidents/{incident_id}", response_model=IncidentRead)
async def update_health_incident(incident_id: UUID, payload: IncidentUpdate, request: Request,
                                 subscription_id: UUID | None = None, client_id: UUID = Depends(client_access),
                                 db: AsyncSession = Depends(get_db)):
    selected = await selected_subscription(db, client_id, subscription_id)
    incident = await db.scalar(select(AzureHealthIncident).where(
        AzureHealthIncident.id == incident_id, AzureHealthIncident.client_id == client_id,
        AzureHealthIncident.subscription_id == selected,
    ).with_for_update()) if selected else None
    if incident is None:
        raise HTTPException(404, "Health incident not found")
    changes = (payload.status, payload.owner or None, payload.rca_note or None)
    current = (incident.status, incident.owner, incident.rca_note)
    if changes != current:
        if payload.updated_at != incident.updated_at:
            raise HTTPException(409, "Health incident changed. Reload it before editing.")
        incident.status, incident.owner, incident.rca_note = changes
        incident.updated_at = datetime.now(timezone.utc)
        audit(db, "update_azure_health_incident", request.state.account, client_id, str(incident.id))
    evidence = await db.get(AzureHealthAcknowledgement, (client_id, selected, incident.evidence_id))
    result = incident_read(incident, evidence)
    await db.commit()
    return result
