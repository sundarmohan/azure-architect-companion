"""
Pydantic schemas for API requests and responses.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


# ==================== Architecture Schemas ====================


class ArchitectureCreate(BaseModel):
    """Schema for creating an architecture."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    provider: str = Field(default="azure", max_length=50)


class ArchitectureUpdate(BaseModel):
    """Schema for updating an architecture."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


class ArchitectureResponse(BaseModel):
    """Schema for architecture API response."""

    id: UUID
    name: str
    description: Optional[str]
    provider: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== Architecture Version Schemas ====================


class ArchitectureVersionCreate(BaseModel):
    """Schema for creating an architecture version."""

    version_number: str = Field(..., min_length=1, max_length=50)
    status: str = Field(default="draft", max_length=50)
    created_by: Optional[str] = None


class ArchitectureVersionUpdate(BaseModel):
    """Schema for updating an architecture version."""

    version_number: Optional[str] = Field(None, min_length=1, max_length=50)
    status: Optional[str] = Field(None, max_length=50)


class ArchitectureVersionResponse(BaseModel):
    """Schema for architecture version API response."""

    id: UUID
    architecture_id: UUID
    version_number: str
    status: str
    created_at: datetime
    created_by: Optional[str]

    class Config:
        from_attributes = True


# ==================== Resource Schemas ====================


class ResourceCreate(BaseModel):
    """Schema for creating a resource."""

    resource_key: str = Field(..., min_length=1, max_length=255)
    resource_type: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    location: Optional[str] = Field(None, max_length=100)
    sku: Optional[dict] = None
    properties: Optional[dict] = None
    tags: Optional[dict] = None
    parent_resource_id: Optional[UUID] = None


class ResourceUpdate(BaseModel):
    """Schema for updating a resource."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    location: Optional[str] = Field(None, max_length=100)
    sku: Optional[dict] = None
    properties: Optional[dict] = None
    tags: Optional[dict] = None
    parent_resource_id: Optional[UUID] = None


class ResourceResponse(BaseModel):
    """Schema for resource API response."""

    id: UUID
    architecture_version_id: UUID
    resource_key: str
    resource_type: str
    name: str
    location: Optional[str]
    sku: Optional[dict]
    properties: Optional[dict]
    tags: Optional[dict]
    parent_resource_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== Relationship Schemas ====================


class RelationshipCreate(BaseModel):
    """Schema for creating a relationship."""

    source_resource_id: UUID
    target_resource_id: UUID
    relationship_type: str = Field(..., min_length=1, max_length=100)
    metadata: Optional[dict] = None


class RelationshipUpdate(BaseModel):
    """Schema for updating a relationship."""

    relationship_type: Optional[str] = Field(None, min_length=1, max_length=100)
    metadata: Optional[dict] = None


class RelationshipResponse(BaseModel):
    """Schema for relationship API response."""

    id: UUID
    architecture_version_id: UUID
    source_resource_id: UUID
    target_resource_id: UUID
    relationship_type: str
    metadata: Optional[dict]

    class Config:
        from_attributes = True


# ==================== Dependency Schemas ====================


class DependencyCreate(BaseModel):
    """Schema for creating a dependency."""

    resource_id: UUID
    depends_on_resource_id: UUID
    dependency_type: str = Field(..., min_length=1, max_length=100)
    required: bool = True
    reason: Optional[str] = None


class DependencyUpdate(BaseModel):
    """Schema for updating a dependency."""

    dependency_type: Optional[str] = Field(None, min_length=1, max_length=100)
    required: Optional[bool] = None
    reason: Optional[str] = None


class DependencyResponse(BaseModel):
    """Schema for dependency API response."""

    id: UUID
    architecture_version_id: UUID
    resource_id: UUID
    depends_on_resource_id: UUID
    dependency_type: str
    required: bool
    reason: Optional[str]

    class Config:
        from_attributes = True
