"""
SQLAlchemy models for the Canonical Architecture Model.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Column,
    String,
    DateTime,
    ForeignKey,
    UUID,
    JSON,
    Boolean,
    Text,
)
from sqlalchemy.orm import relationship

from ..db.base import Base


class Architecture(Base):
    """Represents a complete architecture design."""

    __tablename__ = "architectures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    provider = Column(String(50), nullable=False)  # e.g., "azure"
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    versions = relationship(
        "ArchitectureVersion",
        back_populates="architecture",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Architecture(id={self.id}, name={self.name})>"


class ArchitectureVersion(Base):
    """Represents a version of an architecture."""

    __tablename__ = "architecture_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    architecture_id = Column(UUID(as_uuid=True), ForeignKey("architectures.id"), nullable=False, index=True)
    version_number = Column(String(50), nullable=False)  # e.g., "1.0", "2.1"
    status = Column(String(50), nullable=False, default="draft")  # draft, validated, deployed
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_by = Column(String(255), nullable=True)

    # Relationships
    architecture = relationship("Architecture", back_populates="versions")
    resources = relationship(
        "Resource",
        back_populates="architecture_version",
        cascade="all, delete-orphan",
    )
    relationships = relationship(
        "Relationship",
        back_populates="architecture_version",
        cascade="all, delete-orphan",
    )
    dependencies = relationship(
        "Dependency",
        back_populates="architecture_version",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ArchitectureVersion(id={self.id}, version={self.version_number})>"


class Resource(Base):
    """Represents a single Azure resource in the architecture."""

    __tablename__ = "resources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    architecture_version_id = Column(UUID(as_uuid=True), ForeignKey("architecture_versions.id"), nullable=False, index=True)
    resource_key = Column(String(255), nullable=False)  # Unique identifier within the version
    resource_type = Column(String(255), nullable=False, index=True)  # e.g., "microsoft.compute/virtualmachines"
    name = Column(String(255), nullable=False)
    location = Column(String(100), nullable=True)
    sku = Column(JSON, nullable=True)  # e.g., {"tier": "Standard", "name": "Standard_B1s"}
    properties = Column(JSON, nullable=True)  # Resource-specific properties
    tags = Column(JSON, nullable=True)  # Resource tags
    parent_resource_id = Column(UUID(as_uuid=True), ForeignKey("resources.id"), nullable=True)  # Hierarchy
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    architecture_version = relationship("ArchitectureVersion", back_populates="resources")
    parent = relationship(
        "Resource",
        remote_side=[id],
        backref="children",
        foreign_keys=[parent_resource_id],
    )

    def __repr__(self) -> str:
        return f"<Resource(id={self.id}, type={self.resource_type}, name={self.name})>"


class Relationship(Base):
    """Represents a logical connection between two resources."""

    __tablename__ = "relationships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    architecture_version_id = Column(UUID(as_uuid=True), ForeignKey("architecture_versions.id"), nullable=False, index=True)
    source_resource_id = Column(UUID(as_uuid=True), ForeignKey("resources.id"), nullable=False, index=True)
    target_resource_id = Column(UUID(as_uuid=True), ForeignKey("resources.id"), nullable=False, index=True)
    relationship_type = Column(String(100), nullable=False)  # e.g., "connects_to", "uses", "protects"
    metadata = Column(JSON, nullable=True)  # Additional relationship metadata

    # Relationships
    architecture_version = relationship("ArchitectureVersion", back_populates="relationships")
    source_resource = relationship(
        "Resource",
        foreign_keys=[source_resource_id],
        backref="outgoing_relationships",
    )
    target_resource = relationship(
        "Resource",
        foreign_keys=[target_resource_id],
        backref="incoming_relationships",
    )

    def __repr__(self) -> str:
        return f"<Relationship(type={self.relationship_type}, source={self.source_resource_id}, target={self.target_resource_id})>"


class Dependency(Base):
    """Represents a technical provisioning dependency between resources."""

    __tablename__ = "dependencies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    architecture_version_id = Column(UUID(as_uuid=True), ForeignKey("architecture_versions.id"), nullable=False, index=True)
    resource_id = Column(UUID(as_uuid=True), ForeignKey("resources.id"), nullable=False, index=True)
    depends_on_resource_id = Column(UUID(as_uuid=True), ForeignKey("resources.id"), nullable=False, index=True)
    dependency_type = Column(String(100), nullable=False)  # e.g., "requires", "waits_for", "needs"
    required = Column(Boolean, nullable=False, default=True)  # Whether this dependency is required
    reason = Column(Text, nullable=True)  # Human-readable reason for the dependency

    # Relationships
    architecture_version = relationship("ArchitectureVersion", back_populates="dependencies")
    resource = relationship(
        "Resource",
        foreign_keys=[resource_id],
        backref="outgoing_dependencies",
    )
    depends_on_resource = relationship(
        "Resource",
        foreign_keys=[depends_on_resource_id],
        backref="incoming_dependencies",
    )

    def __repr__(self) -> str:
        return f"<Dependency(type={self.dependency_type}, required={self.required})>"
