"""Evaluate local metric thresholds using the saved Azure Monitor evidence."""

from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import ForeignKey, String, Text, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.access.azure import connection_values, select_subscription
from app.domains.access.models import AzureConnection
from app.domains.access.routes import audit, client_access, client_admin, get_db
from .observation_models import AzureObservation
from .telemetry import ARM_RESOURCE_ID, MAX_RESOURCES, PLATFORM_METRICS

router = APIRouter()
Aggregation = Literal["average", "total"]


class AzureMetricThreshold(Base):
    __tablename__ = "azure_metric_thresholds"

    client_id: Mapped[UUID] = mapped_column(ForeignKey("client_workspaces.id", ondelete="CASCADE"), primary_key=True)
    subscription_id: Mapped[UUID] = mapped_column(primary_key=True)
    resource_id: Mapped[str] = mapped_column(Text)
    metric: Mapped[str] = mapped_column(String(100))
    aggregation: Mapped[str] = mapped_column(String(12))
    unit: Mapped[str | None] = mapped_column(String(40))
    direction: Mapped[str] = mapped_column(String(8))
    limit: Mapped[float]


class ThresholdWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    resource_id: str = Field(min_length=1, max_length=2048)
    metric: str = Field(min_length=1, max_length=100)
    aggregation: Aggregation
    direction: Literal["above", "below"]
    limit: float = Field(ge=-1e30, le=1e30, allow_inf_nan=False)


class ThresholdRead(ThresholdWrite):
    unit: str | None


class MetricChoice(BaseModel):
    resource_id: str
    resource_name: str
    metric: str
    aggregation: Aggregation
    unit: str | None


class ThresholdAssessment(BaseModel):
    status: Literal["breached", "within", "missing_sample", "unit_changed"]
    value: float | None = None
    sample_at: datetime | None = None
    freshness: Literal["recent", "stale", "retained", "incomplete"] | None = None


class ThresholdWorkspace(BaseModel):
    threshold: ThresholdRead | None
    assessment: ThresholdAssessment | None
    choices: list[MetricChoice]
    snapshot_status: str
    last_attempt_at: datetime | None
    last_success_at: datetime | None


def threshold_series(snapshot):
    if snapshot is None:
        return {}
    prefix = f"/subscriptions/{snapshot.subscription_id}/"
    choices = {}
    for resource in snapshot.payload.get("resources", [])[:MAX_RESOURCES]:
        resource_id = resource.get("id", "")
        if (not isinstance(resource_id, str) or len(resource_id) > 2048 or not ARM_RESOURCE_ID.fullmatch(resource_id)
                or not resource_id.casefold().startswith(prefix)
                or any(segment in {".", ".."} for segment in resource_id.split("/"))
                or any(ord(char) < 32 for char in resource_id)):
            continue
        profile = PLATFORM_METRICS.get(str(resource.get("type", "")).casefold(), {})
        permitted = {(name, group.lower()) for group, names in profile.items() for name in names}
        for series in resource.get("metrics", []):
            name, aggregation = series.get("name"), series.get("aggregation")
            if not isinstance(name, str) or not isinstance(aggregation, str) or (name, aggregation) not in permitted:
                continue
            unit = series.get("unit")
            choice = MetricChoice(
                resource_id=resource_id, resource_name=str(resource.get("name") or resource_id)[:300],
                metric=name, aggregation=aggregation, unit=unit[:40] if isinstance(unit, str) else None,
            )
            choices.setdefault((resource_id.casefold(), name, aggregation), (choice, series.get("points", [])))
    return choices


def evaluate_threshold(snapshot, threshold, series, now):
    selected = series.get((threshold.resource_id.casefold(), threshold.metric, threshold.aggregation))
    if selected is None:
        return ThresholdAssessment(status="missing_sample")
    choice, points = selected
    if choice.unit != threshold.unit:
        return ThresholdAssessment(status="unit_changed")
    latest = None
    for point in points:
        value = point.get("value")
        if type(value) not in (int, float) or abs(value) > 1e30 or not isfinite(value):
            continue
        try:
            timestamp = datetime.fromisoformat(point["timestamp"])
        except (KeyError, TypeError, ValueError):
            continue
        if timestamp.utcoffset() is not None and timestamp <= now and (latest is None or timestamp > latest[0]):
            latest = timestamp, value
    if latest is None:
        return ThresholdAssessment(status="missing_sample")
    timestamp, value = latest
    if snapshot.status != "synced":
        freshness = "retained" if snapshot.last_success_at else "incomplete"
    else:
        freshness = "stale" if now - timestamp > timedelta(hours=24) else "recent"
    breached = value > threshold.limit if threshold.direction == "above" else value < threshold.limit
    return ThresholdAssessment(
        status="breached" if breached else "within", value=value, sample_at=timestamp, freshness=freshness,
    )


def workspace_result(snapshot, threshold, series):
    return ThresholdWorkspace(
        threshold=threshold,
        assessment=evaluate_threshold(snapshot, threshold, series, datetime.now(timezone.utc)) if threshold else None,
        choices=[choice for choice, _ in series.values()],
        snapshot_status=snapshot.status if snapshot else "not_synced",
        last_attempt_at=snapshot.last_attempt_at if snapshot else None,
        last_success_at=snapshot.last_success_at if snapshot else None,
    )


@router.get("/monitoring/thresholds", response_model=ThresholdWorkspace)
async def read_threshold(
    subscription_id: UUID, client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db),
):
    select_subscription(await connection_values(db, client_id), subscription_id)
    snapshot = await db.get(AzureObservation, (client_id, subscription_id, "monitoring"))
    threshold = await db.get(AzureMetricThreshold, (client_id, subscription_id))
    return workspace_result(snapshot, threshold, threshold_series(snapshot))


@router.put("/monitoring/thresholds", response_model=ThresholdWorkspace)
async def save_threshold(
    payload: ThresholdWrite, request: Request, subscription_id: UUID,
    client_id: UUID = Depends(client_admin), db: AsyncSession = Depends(get_db),
):
    connection = await db.scalar(select(AzureConnection).where(AzureConnection.client_id == client_id).with_for_update())
    values = await connection_values(db, client_id, connection) if connection else None
    select_subscription(values, subscription_id)
    snapshot = await db.get(AzureObservation, (client_id, subscription_id, "monitoring"))
    series = threshold_series(snapshot)
    selected = series.get((payload.resource_id.casefold(), payload.metric, payload.aggregation))
    if selected is None:
        raise HTTPException(409, "Select a supported metric from the saved monitoring evidence")
    choice, _ = selected
    changes = {**payload.model_dump(), "resource_id": choice.resource_id, "unit": choice.unit}
    await db.execute(insert(AzureMetricThreshold).values(client_id=client_id, subscription_id=subscription_id, **changes)
                     .on_conflict_do_update(index_elements=[AzureMetricThreshold.client_id, AzureMetricThreshold.subscription_id],
                                            set_=changes))
    audit(db, "save_azure_metric_threshold", request.state.account, client_id, str(subscription_id))
    await db.commit()
    return workspace_result(snapshot, ThresholdRead(**changes), series)
