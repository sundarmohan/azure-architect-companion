from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AzureObservation(Base):
    __tablename__ = "azure_observations"

    client_id: Mapped[UUID] = mapped_column(ForeignKey("client_workspaces.id", ondelete="CASCADE"), primary_key=True)
    subscription_id: Mapped[UUID] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    status: Mapped[str] = mapped_column(String(32))
    last_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    limitations: Mapped[list[str]] = mapped_column(JSONB, default=list)


class AzureObservationSchedule(Base):
    __tablename__ = "azure_observation_schedules"

    client_id: Mapped[UUID] = mapped_column(ForeignKey("client_workspaces.id", ondelete="CASCADE"), primary_key=True)
    subscription_id: Mapped[UUID] = mapped_column(primary_key=True)
    generation: Mapped[UUID] = mapped_column(default=uuid4)
    enabled: Mapped[bool]
    include_security: Mapped[bool] = mapped_column(default=False)
    interval_minutes: Mapped[int]
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class AzureSecurityTracking(Base):
    __tablename__ = "azure_security_tracking"

    client_id: Mapped[UUID] = mapped_column(ForeignKey("client_workspaces.id", ondelete="CASCADE"), primary_key=True)
    subscription_id: Mapped[UUID] = mapped_column(primary_key=True)
    finding_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16))
    owner: Mapped[str | None] = mapped_column(String(120))
    due_date: Mapped[date | None]


class AzureHealthAcknowledgement(Base):
    __tablename__ = "azure_health_acknowledgements"

    client_id: Mapped[UUID] = mapped_column(ForeignKey("client_workspaces.id", ondelete="CASCADE"), primary_key=True)
    subscription_id: Mapped[UUID] = mapped_column(primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    resource_id: Mapped[str] = mapped_column(Text)
    health: Mapped[str] = mapped_column(String(16))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_id: Mapped[UUID]
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AzureHealthIncident(Base):
    __tablename__ = "azure_health_incidents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["client_id", "subscription_id", "evidence_id"],
            ["azure_health_acknowledgements.client_id", "azure_health_acknowledgements.subscription_id",
             "azure_health_acknowledgements.evidence_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("client_id", "subscription_id", "evidence_id", name="uq_health_incident_evidence"),
        Index("ix_health_incident_scope_created", "client_id", "subscription_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    client_id: Mapped[UUID]
    subscription_id: Mapped[UUID]
    evidence_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    owner: Mapped[str | None] = mapped_column(String(120))
    rca_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
