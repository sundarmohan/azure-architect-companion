from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey
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
