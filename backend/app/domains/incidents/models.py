from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MonitoringIncident(Base):
    __tablename__ = "monitoring_incidents"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    architecture_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("architectures.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open", index=True)
    owner_id: Mapped[str | None] = mapped_column(String(120))
    timeline: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    affected_resource_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    source_alert_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MonitoringAlert(Base):
    __tablename__ = "monitoring_alerts"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    architecture_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("architectures.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("architecture_resources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    subscription_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("azure_subscriptions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    incident_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("monitoring_incidents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open", index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="monitoring_signal")
    signal_state: Mapped[str | None] = mapped_column(String(60))
    health_status: Mapped[str | None] = mapped_column(String(60))
    resource_name: Mapped[str | None] = mapped_column(String(250))
    resource_type: Mapped[str | None] = mapped_column(String(120))
    message: Mapped[str | None] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(400), nullable=False, index=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
