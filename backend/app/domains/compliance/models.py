from datetime import date, datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ComplianceReview(Base):
    __tablename__ = "compliance_reviews"

    client_id: Mapped[UUID] = mapped_column(ForeignKey("client_workspaces.id", ondelete="CASCADE"), primary_key=True)
    subscription_id: Mapped[UUID] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(24), primary_key=True)
    state: Mapped[str] = mapped_column(String(24))
    note: Mapped[str] = mapped_column(Text)
    action: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(120))
    due_date: Mapped[date | None]
    action_status: Mapped[str | None] = mapped_column(String(24))
    evidence_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
