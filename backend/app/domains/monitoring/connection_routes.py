from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal

from .connection_schemas import AzureSubscriptionCandidateRead, MonitoringSubscriptionCreate, MonitoringSubscriptionRead
from .connection_service import MonitoringConnectionService

router = APIRouter()


async def get_db():
    async with SessionLocal() as session:
        yield session


@router.get("/subscriptions", response_model=list[MonitoringSubscriptionRead])
async def list_monitoring_subscriptions(db: AsyncSession = Depends(get_db)):
    return await MonitoringConnectionService().list_saved(db)


@router.get("/subscriptions/available", response_model=list[AzureSubscriptionCandidateRead])
async def discover_monitoring_subscriptions(db: AsyncSession = Depends(get_db)):
    try:
        return await MonitoringConnectionService().discover_subscriptions(db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/subscriptions", response_model=MonitoringSubscriptionRead, status_code=status.HTTP_201_CREATED)
async def connect_monitoring_subscription(payload: MonitoringSubscriptionCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await MonitoringConnectionService().save_subscription(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/subscriptions/{subscription_id}/refresh", response_model=MonitoringSubscriptionRead)
async def refresh_monitoring_subscription(subscription_id: UUID, db: AsyncSession = Depends(get_db)):
    try:
        return await MonitoringConnectionService().refresh_subscription(db, subscription_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/subscriptions/{subscription_id}/metrics", response_model=MonitoringSubscriptionRead)
async def get_monitoring_metrics(
    subscription_id: UUID,
    hours: int = Query(default=24, ge=1, le=720),
    interval: str = Query(default="PT1H", min_length=2, max_length=20),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await MonitoringConnectionService().get_metrics(db, subscription_id, hours, interval)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/subscriptions/{subscription_id}/incidents/{incident_id}/status", response_model=MonitoringSubscriptionRead)
async def update_monitoring_incident_status(
    subscription_id: UUID,
    incident_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await MonitoringConnectionService().update_incident_status(db, subscription_id, incident_id, str(payload.get("status") or ""), payload.get("comment"), str(payload.get("actor") or "platform_operator"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/subscriptions/{subscription_id}", status_code=204)
async def delete_monitoring_subscription(subscription_id: UUID, db: AsyncSession = Depends(get_db)):
    await MonitoringConnectionService().delete_subscription(db, subscription_id)
