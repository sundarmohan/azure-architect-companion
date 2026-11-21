from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, Float, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class Architecture(Base):
    __tablename__ = "architectures"
    __table_args__ = (
        CheckConstraint(
            "client_id IS NULL OR status IN ('draft', 'in_review', 'approved', 'archived')",
            name="ck_architecture_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    client_id: Mapped[UUID | None] = mapped_column(ForeignKey("client_workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    project: Mapped[str | None] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(30), nullable=False, default="azure")
    environment: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    default_region: Mapped[str | None] = mapped_column(String(100))
    graph_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class ArchitectureResource(Base):
    __tablename__ = "architecture_resources"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    architecture_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("architectures.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    azure_resource_type: Mapped[str | None] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str | None] = mapped_column(String(100))
    parent_resource_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("architecture_resources.id", ondelete="SET NULL"),
        index=True,
    )
    resource_group_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("azure_resource_groups.id", ondelete="SET NULL"))
    sku: Mapped[str | None] = mapped_column(String(200))
    properties: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    position_x: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    position_y: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class ArchitectureRelationship(Base):
    __tablename__ = "architecture_relationships"
    __table_args__ = (
        UniqueConstraint(
            "architecture_id",
            "source_resource_id",
            "target_resource_id",
            "relationship_type",
            name="uq_architecture_relationship",
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    architecture_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("architectures.id", ondelete="CASCADE"), nullable=False, index=True)
    source_resource_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("architecture_resources.id", ondelete="CASCADE"), nullable=False)
    target_resource_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("architecture_resources.id", ondelete="CASCADE"), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(80), nullable=False, default="connects_to")
    properties: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AzureResourceGroup(Base):
    __tablename__ = "azure_resource_groups"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    architecture_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("architectures.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str] = mapped_column(String(100), nullable=False)
    subscription_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("azure_subscriptions.id", ondelete="SET NULL"))
    position_x: Mapped[float] = mapped_column(Float, nullable=False, default=80)
    position_y: Mapped[float] = mapped_column(Float, nullable=False, default=120)
    tags: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    properties: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class AzureSubscription(Base):
    __tablename__ = "azure_subscriptions"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    architecture_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("architectures.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    subscription_id: Mapped[str | None] = mapped_column(String(100))
    tenant_id: Mapped[str | None] = mapped_column(String(100))
    environment: Mapped[str] = mapped_column(String(50), nullable=False, default="design")
    properties: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ArchitectureDependency(Base):
    __tablename__ = "architecture_dependencies"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    architecture_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("architectures.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    dependency_type: Mapped[str] = mapped_column(String(100), nullable=False)
    required: Mapped[bool] = mapped_column(default=True)
    auto_create_allowed: Mapped[bool] = mapped_column(default=True)
    notes: Mapped[str | None] = mapped_column(Text)
    properties: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
