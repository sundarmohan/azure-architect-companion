from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.access.azure import connection_values, select_subscription
from app.domains.access.models import AzureConnection
from app.domains.access.routes import audit, client_access, client_admin, get_db
from .health_alerts import attach_health_alerts
from .health_alerts import router as health_alert_router
from .health_incidents import router as health_incident_router
from .observation_models import AzureObservation, AzureObservationSchedule
from .observations import ObservationKind, refresh_observations
from .security_routes import attach_tracking

router = APIRouter()
router.include_router(health_alert_router)
router.include_router(health_incident_router)


class ObservationRead(BaseModel):
    subscription_id: UUID | None
    status: str
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    resources: list[dict] = Field(default_factory=list)
    links: list[dict] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    findings: list[dict] = Field(default_factory=list)
    score: int | None = None
    score_factors: list[dict] = Field(default_factory=list)


class ScheduleWrite(BaseModel):
    enabled: bool
    include_security: bool = False
    interval_minutes: int = Field(ge=5, le=1440)


class ScheduleRead(ScheduleWrite):
    subscription_id: UUID | None
    next_run_at: datetime | None = None


async def observation_read(db, snapshot, selected):
    if snapshot is None:
        return ObservationRead(subscription_id=selected, status="not_synced" if selected else "not_configured")
    payload = await attach_tracking(db, snapshot, snapshot.payload)
    payload = await attach_health_alerts(db, snapshot, payload)
    return ObservationRead(
        subscription_id=selected, status=snapshot.status, last_attempt_at=snapshot.last_attempt_at,
        last_success_at=snapshot.last_success_at, limitations=snapshot.limitations, **payload,
    )


@router.get("/{kind}", response_model=ObservationRead)
async def read_observation(kind: ObservationKind, subscription_id: UUID | None = None,
                           client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db)):
    selected = select_subscription(await connection_values(db, client_id), subscription_id)
    snapshot = await db.get(AzureObservation, (client_id, UUID(selected), kind)) if selected else None
    return await observation_read(db, snapshot, selected)


@router.post("/{kind}/refresh", response_model=ObservationRead)
async def refresh_observation(kind: ObservationKind, request: Request, subscription_id: UUID | None = None,
                              client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db)):
    snapshots = await refresh_observations(db, client_id, subscription_id, (kind,), request)
    snapshot = snapshots.get(kind)
    return await observation_read(db, snapshot, snapshot.subscription_id if snapshot else None)


@router.get("/monitoring/schedule", response_model=ScheduleRead)
async def read_schedule(subscription_id: UUID | None = None, client_id: UUID = Depends(client_admin),
                        db: AsyncSession = Depends(get_db)):
    selected = select_subscription(await connection_values(db, client_id), subscription_id)
    schedule = await db.get(AzureObservationSchedule, (client_id, UUID(selected))) if selected else None
    return ScheduleRead(subscription_id=selected, enabled=schedule.enabled if schedule else False,
                        interval_minutes=schedule.interval_minutes if schedule else 15,
                        include_security=schedule.include_security if schedule else False,
                        next_run_at=schedule.next_run_at if schedule else None)


@router.put("/monitoring/schedule", response_model=ScheduleRead)
async def write_schedule(payload: ScheduleWrite, request: Request, subscription_id: UUID | None = None,
                         client_id: UUID = Depends(client_admin), db: AsyncSession = Depends(get_db)):
    connection = await db.scalar(select(AzureConnection).where(
        AzureConnection.client_id == client_id
    ).with_for_update())
    selected = select_subscription(await connection_values(db, client_id, connection) if connection else None,
                                   subscription_id)
    if selected is None:
        raise HTTPException(409, "Configure an Azure subscription before scheduling collection")
    next_run = datetime.now(timezone.utc) if payload.enabled else None
    values = {**payload.model_dump(), "next_run_at": next_run, "generation": uuid4()}
    await db.execute(insert(AzureObservationSchedule).values(client_id=client_id, subscription_id=UUID(selected), **values)
        .on_conflict_do_update(index_elements=[AzureObservationSchedule.client_id, AzureObservationSchedule.subscription_id],
                               set_=values))
    audit(db, "set_azure_observation_schedule", request.state.account, client_id, selected)
    await db.commit()
    return ScheduleRead(subscription_id=selected, next_run_at=next_run, **payload.model_dump())
