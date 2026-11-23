from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ComplianceReview(Base):
    __tablename__ = "compliance_reviews"

    client_id: Mapped[UUID] = mapped_column(ForeignKey("client_workspaces.id", ondelete="CASCADE"), primary_key=True)
    subscription_id: Mapped[UUID] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(24), primary_key=True)
    applicability: Mapped[str | None] = mapped_column(String(20))
    outcome: Mapped[str | None] = mapped_column(String(24))
    state: Mapped[str] = mapped_column(String(24))
    note: Mapped[str] = mapped_column(Text)
    action: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(120))
    due_date: Mapped[date | None]
    action_status: Mapped[str | None] = mapped_column(String(24))
    evidence_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ComplianceReviewHistory(Base):
    __tablename__ = "compliance_review_history"
    __table_args__ = (Index(
        "ix_compliance_review_history_scope", "client_id", "subscription_id", "topic", "recorded_at", "id",
    ),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("client_workspaces.id", ondelete="CASCADE"))
    subscription_id: Mapped[UUID]
    topic: Mapped[str] = mapped_column(String(24))
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("local_accounts.id", ondelete="SET NULL"))
    state: Mapped[str] = mapped_column(String(24))
    applicability: Mapped[str | None] = mapped_column(String(20))
    outcome: Mapped[str | None] = mapped_column(String(24))
    action_status: Mapped[str | None] = mapped_column(String(24))
    due_date: Mapped[date | None]
    evidence_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    changed_fields: Mapped[list[str]] = mapped_column(JSONB)
    baseline: Mapped[bool] = mapped_column(default=False)
