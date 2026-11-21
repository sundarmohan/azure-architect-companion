from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Assessment(Base):
    __tablename__ = "security_assessments"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("client_workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    scope: Mapped[str] = mapped_column(Text)
    authorization: Mapped[str] = mapped_column(Text)
    environment: Mapped[str | None] = mapped_column(String(80))
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssessmentFinding(Base):
    __tablename__ = "security_assessment_findings"
    __table_args__ = (UniqueConstraint("assessment_id", "source", "external_id", name="uq_assessment_finding_source"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    assessment_id: Mapped[UUID] = mapped_column(ForeignKey("security_assessments.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(160))
    title: Mapped[str] = mapped_column(String(240))
    severity: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(100))
    evidence: Mapped[str] = mapped_column(Text)
    tool_version: Mapped[str | None] = mapped_column(String(100))
    methodology: Mapped[str | None] = mapped_column(String(400))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="open")
    owner: Mapped[str | None] = mapped_column(String(120))
    due_date: Mapped[date | None]
    retest_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FindingEvent(Base):
    __tablename__ = "security_assessment_finding_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    finding_id: Mapped[UUID] = mapped_column(ForeignKey("security_assessment_findings.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[UUID]
    status: Mapped[str] = mapped_column(String(24))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
