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
    relationship_metadata = Column("metadata", JSON, nullable=True)  # Additional relationship metadata

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


# ============================================================================
# RESOURCE CATALOG MODELS - Authoritative knowledge layer for resource types
# ============================================================================


class ResourceCatalog(Base):
    """
    Represents a resource type in the Resource Catalog.
    
    The Resource Catalog describes what resource types are supported
    and what properties, dependencies, and requirements they have.
    
    This is separate from the Canonical Architecture Model which describes
    what resources exist in a specific architecture.
    """

    __tablename__ = "resource_catalog"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider = Column(String(50), nullable=False, index=True)  # e.g., "azure", "aws"
    resource_type = Column(String(255), nullable=False, index=True)  # e.g., "microsoft.compute/virtualmachines"
    display_name = Column(String(255), nullable=False)  # e.g., "Virtual Machine"
    category = Column(String(100), nullable=False, index=True)  # e.g., "compute", "networking", "storage"
    description = Column(Text, nullable=True)  # Human-readable description
    version = Column(String(50), nullable=False, default="1.0")  # Catalog version for this resource type
    enabled = Column(Boolean, nullable=False, default=True)  # Whether this resource type is supported
    properties_schema = Column(JSON, nullable=True)  # JSON schema for resource properties
    default_properties = Column(JSON, nullable=True)  # Default properties when creating this resource type
    terraform_mapping = Column(JSON, nullable=True)  # Terraform resource type mapping
    metadata = Column(JSON, nullable=True)  # Additional metadata
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    required_dependencies = relationship(
        "CatalogDependency",
        foreign_keys="CatalogDependency.resource_type_id",
        backref="resource_catalog",
        cascade="all, delete-orphan",
    )
    allowed_parents = relationship(
        "CatalogHierarchy",
        foreign_keys="CatalogHierarchy.child_resource_type_id",
        backref="child_resource",
        cascade="all, delete-orphan",
    )
    allowed_children = relationship(
        "CatalogHierarchy",
        foreign_keys="CatalogHierarchy.parent_resource_type_id",
        backref="parent_resource",
        cascade="all, delete-orphan",
    )
    networking_requirements = relationship(
        "CatalogNetworkingRequirement",
        back_populates="resource_catalog",
        cascade="all, delete-orphan",
    )
    security_requirements = relationship(
        "CatalogSecurityRequirement",
        back_populates="resource_catalog",
        cascade="all, delete-orphan",
    )
    monitoring_requirements = relationship(
        "CatalogMonitoringRequirement",
        back_populates="resource_catalog",
        cascade="all, delete-orphan",
    )
    backup_requirements = relationship(
        "CatalogBackupRequirement",
        back_populates="resource_catalog",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ResourceCatalog(provider={self.provider}, resource_type={self.resource_type})>"


class CatalogDependency(Base):
    """
    Represents a dependency between two resource types in the catalog.
    
    For example: Virtual Machine requires a Network Interface and OS Disk.
    """

    __tablename__ = "catalog_dependencies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    resource_type_id = Column(UUID(as_uuid=True), ForeignKey("resource_catalog.id"), nullable=False, index=True)
    depends_on_resource_type = Column(String(255), nullable=False)  # The resource type this depends on
    dependency_classification = Column(String(20), nullable=False)  # "REQUIRED", "RECOMMENDED", "OPTIONAL"
    reason = Column(Text, nullable=True)  # Why this dependency exists
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<CatalogDependency(classification={self.dependency_classification})>"


class CatalogHierarchy(Base):
    """
    Represents valid containment (parent-child) relationships between resource types.
    
    For example: Resource Group can contain VNet, VNet can contain Subnet.
    """

    __tablename__ = "catalog_hierarchy"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    parent_resource_type_id = Column(UUID(as_uuid=True), ForeignKey("resource_catalog.id"), nullable=False, index=True)
    child_resource_type_id = Column(UUID(as_uuid=True), ForeignKey("resource_catalog.id"), nullable=False, index=True)
    description = Column(Text, nullable=True)  # e.g., "VNet must be contained in a Resource Group"
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<CatalogHierarchy(parent={self.parent_resource_type_id}, child={self.child_resource_type_id})>"


class CatalogNetworkingRequirement(Base):
    """Networking requirements for a resource type."""

    __tablename__ = "catalog_networking_requirements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    resource_catalog_id = Column(UUID(as_uuid=True), ForeignKey("resource_catalog.id"), nullable=False, index=True)
    requirement = Column(Text, nullable=False)  # e.g., "Must be deployed in a VNet"
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    resource_catalog = relationship("ResourceCatalog", back_populates="networking_requirements")

    def __repr__(self) -> str:
        return f"<CatalogNetworkingRequirement(requirement={self.requirement})>"


class CatalogSecurityRequirement(Base):
    """Security requirements for a resource type."""

    __tablename__ = "catalog_security_requirements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    resource_catalog_id = Column(UUID(as_uuid=True), ForeignKey("resource_catalog.id"), nullable=False, index=True)
    requirement = Column(Text, nullable=False)  # e.g., "Must use HTTPS/TLS", "Requires NSG"
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    resource_catalog = relationship("ResourceCatalog", back_populates="security_requirements")

    def __repr__(self) -> str:
        return f"<CatalogSecurityRequirement(requirement={self.requirement})>"


class CatalogMonitoringRequirement(Base):
    """Monitoring requirements for a resource type."""

    __tablename__ = "catalog_monitoring_requirements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    resource_catalog_id = Column(UUID(as_uuid=True), ForeignKey("resource_catalog.id"), nullable=False, index=True)
    requirement = Column(Text, nullable=False)  # e.g., "Recommended to enable diagnostic settings"
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    resource_catalog = relationship("ResourceCatalog", back_populates="monitoring_requirements")

    def __repr__(self) -> str:
        return f"<CatalogMonitoringRequirement(requirement={self.requirement})>"


class CatalogBackupRequirement(Base):
    """Backup requirements for a resource type."""

    __tablename__ = "catalog_backup_requirements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    resource_catalog_id = Column(UUID(as_uuid=True), ForeignKey("resource_catalog.id"), nullable=False, index=True)
    requirement = Column(Text, nullable=False)  # e.g., "Recommended to enable automated backups"
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    resource_catalog = relationship("ResourceCatalog", back_populates="backup_requirements")

    def __repr__(self) -> str:
        return f"<CatalogBackupRequirement(requirement={self.requirement})>"


# ==================== COMPLIANCE ENGINE MODELS ====================


class ComplianceFramework(Base):
    """Represents a compliance framework (HIPAA, GDPR, SOC2, etc.)."""

    __tablename__ = "compliance_frameworks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    framework_name = Column(String(100), nullable=False, unique=True, index=True)  # HIPAA, GDPR, etc.
    framework_version = Column(String(50), nullable=False)  # Version of the framework profile
    display_name = Column(String(255), nullable=False)  # Full name for display
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    controls = relationship(
        "ComplianceControl",
        back_populates="framework",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ComplianceFramework(id={self.id}, name={self.framework_name})>"


class ComplianceControl(Base):
    """Represents a compliance control within a framework."""

    __tablename__ = "compliance_controls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    framework_id = Column(UUID(as_uuid=True), ForeignKey("compliance_frameworks.id"), nullable=False, index=True)
    control_code = Column(String(100), nullable=False)  # e.g., HIPAA-TECH-001
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=False)  # ACCESS_CONTROL, ENCRYPTION, etc.
    evaluation_type = Column(String(50), nullable=False)  # PROPERTY_CHECK, DEPENDENCY_CHECK, etc.
    rule_version = Column(String(50), nullable=False)  # Version of the rule implementation
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    framework = relationship("ComplianceFramework", back_populates="controls")
    policies = relationship(
        "ComplianceControlPolicy",
        back_populates="control",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ComplianceControl(code={self.control_code}, framework_id={self.framework_id})>"


class ComplianceControlPolicy(Base):
    """Policy level (BLOCK, REQUIRED, RECOMMENDATION) for a control."""

    __tablename__ = "compliance_control_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    control_id = Column(UUID(as_uuid=True), ForeignKey("compliance_controls.id"), nullable=False, index=True)
    policy_level = Column(String(50), nullable=False)  # BLOCK, REQUIRED, RECOMMENDATION
    default_enabled = Column(Boolean, nullable=False, default=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    control = relationship("ComplianceControl", back_populates="policies")

    def __repr__(self) -> str:
        return f"<ComplianceControlPolicy(control_id={self.control_id}, level={self.policy_level})>"
