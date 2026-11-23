from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AzureRecoveryObjectives(Base):
    __tablename__ = "azure_recovery_objectives"
    __table_args__ = (
        CheckConstraint("rpo_hours BETWEEN 1 AND 8760", name="ck_azure_recovery_objectives_rpo"),
        CheckConstraint("rto_minutes BETWEEN 1 AND 525600", name="ck_azure_recovery_objectives_rto"),
    )

    client_id: Mapped[UUID] = mapped_column(ForeignKey("client_workspaces.id", ondelete="CASCADE"), primary_key=True)
    subscription_id: Mapped[UUID] = mapped_column(primary_key=True)
    rpo_hours: Mapped[int]
    rto_minutes: Mapped[int]


class AzureRestoreTest(Base):
    __tablename__ = "azure_restore_tests"
    __table_args__ = (
        CheckConstraint("outcome IN ('passed', 'failed', 'partial')", name="ck_azure_restore_test_outcome"),
        CheckConstraint("recovery_minutes IS NULL OR recovery_minutes BETWEEN 1 AND 525600",
                        name="ck_azure_restore_test_duration"),
        Index("ix_azure_restore_test_scope", "client_id", "subscription_id", "tested_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("client_workspaces.id", ondelete="CASCADE"))
    subscription_id: Mapped[UUID]
    resource_name: Mapped[str] = mapped_column(String(200))
    tested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(String(16))
    recovery_minutes: Mapped[int | None]
    evidence_reference: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
