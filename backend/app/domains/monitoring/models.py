from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MonitoringSubscription(Base):
    __tablename__ = "monitoring_subscriptions"
    __table_args__ = (UniqueConstraint("subscription_id", name="uq_monitoring_subscriptions_subscription_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    subscription_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(String(100))
    service_principal_provider: Mapped[str] = mapped_column(String(80), nullable=False, default="azure_credentials")
    connection_state: Mapped[str] = mapped_column(String(50), nullable=False, default="not_checked")
    last_error: Mapped[str | None] = mapped_column(Text)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    resources: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    alerts: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    incidents: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    unused_analysis: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metrics_state: Mapped[str] = mapped_column(String(50), nullable=False, default="not_checked")
    alerts_state: Mapped[str] = mapped_column(String(50), nullable=False, default="not_checked")
    incidents_state: Mapped[str] = mapped_column(String(50), nullable=False, default="not_checked")
    refresh_state: Mapped[str] = mapped_column(String(50), nullable=False, default="not_checked")
    refresh_error: Mapped[str | None] = mapped_column(Text)
    last_successful_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
