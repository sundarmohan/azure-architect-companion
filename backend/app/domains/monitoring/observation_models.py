from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String
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
