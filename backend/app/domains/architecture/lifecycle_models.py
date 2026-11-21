from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DesignRevision(Base):
    __tablename__ = "design_revisions"
    __table_args__ = (UniqueConstraint("architecture_id", "number", name="uq_design_revision_number"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    architecture_id: Mapped[UUID] = mapped_column(ForeignKey("architectures.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DesignLifecycleEvent(Base):
    __tablename__ = "design_lifecycle_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    architecture_id: Mapped[UUID] = mapped_column(ForeignKey("architectures.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(32))
    from_status: Mapped[str] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
