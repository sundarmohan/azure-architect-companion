from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RepositoryFinding(Base):
    __tablename__ = "devsecops_findings"
    __table_args__ = (UniqueConstraint(
        "client_id", "owner", "repository", "source", "fingerprint", name="uq_devsecops_finding_source",
    ),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("client_workspaces.id", ondelete="CASCADE"), index=True)
    owner: Mapped[str] = mapped_column(String(39))
    repository: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(60))
    fingerprint: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(16))
    commit_sha: Mapped[str | None] = mapped_column(String(40))
    image: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
