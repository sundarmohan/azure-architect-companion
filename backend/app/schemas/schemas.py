"""
Pydantic schemas for API requests and responses.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


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

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    id: UUID
    architecture_version_id: UUID
    source_resource_id: UUID
    target_resource_id: UUID
    relationship_type: str
    metadata: Optional[dict] = Field(
        None,
        validation_alias="relationship_metadata",
        serialization_alias="metadata",
    )


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


# ==================== Resource Catalog Schemas ====================


class CatalogDependencyResponse(BaseModel):
    """Schema for catalog dependency API response."""

    id: UUID
    depends_on_resource_type: str
    dependency_classification: str  # "REQUIRED", "RECOMMENDED", "OPTIONAL"
    reason: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class CatalogHierarchyResponse(BaseModel):
    """Schema for catalog hierarchy API response."""

    parent_resource_type: str
    child_resource_type: str
    description: Optional[str]


class TerraformMappingResponse(BaseModel):
    """Schema for Terraform mapping API response."""

    resource_type: str
    terraform_type: Optional[str]
    provider: Optional[str]
    additional_mapping: Optional[dict]


class ResourceCatalogResponse(BaseModel):
    """Schema for resource catalog API response."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    id: UUID
    provider: str
    resource_type: str
    display_name: str
    category: str
    description: Optional[str]
    version: str
    enabled: bool
    properties_schema: Optional[dict]
    default_properties: Optional[dict]
    terraform_mapping: Optional[dict]
    metadata: Optional[dict] = Field(
        None,
        validation_alias="resource_metadata",
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime


class ResourceCatalogDetailResponse(BaseModel):
    """Schema for detailed resource catalog response including dependencies and hierarchy."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    id: UUID
    provider: str
    resource_type: str
    display_name: str
    category: str
    description: Optional[str]
    version: str
    enabled: bool
    properties_schema: Optional[dict]
    default_properties: Optional[dict]
    terraform_mapping: Optional[dict]
    metadata: Optional[dict] = Field(
        None,
        validation_alias="resource_metadata",
        serialization_alias="metadata",
    )
    required_dependencies: List[CatalogDependencyResponse]
    recommended_dependencies: List[CatalogDependencyResponse]
    optional_dependencies: List[CatalogDependencyResponse]
    valid_parent_types: List[str]
    valid_child_types: List[str]
    created_at: datetime
    updated_at: datetime


class ResourceCatalogListResponse(BaseModel):
    """Schema for listing resource catalogs."""

    total: int
    resources: List[ResourceCatalogResponse]


class CatalogDependenciesResponse(BaseModel):
    """Schema for dependencies of a resource type."""

    resource_type: str
    required: List[CatalogDependencyResponse]
    recommended: List[CatalogDependencyResponse]
    optional: List[CatalogDependencyResponse]


class CatalogCategoriesResponse(BaseModel):
    """Schema for listing categories."""

    categories: List[str]


# ==================== Dependency Analysis Schemas ====================


class DependencyFindingResponse(BaseModel):
    """Schema for a single dependency finding from the Dependency Engine."""

    architecture_id: UUID
    architecture_version_id: UUID
    source_resource_id: UUID
    source_resource_key: str
    source_resource_type: str
    dependency_resource_type: Optional[str]  # Null for CATALOG_RESOURCE_TYPE_UNKNOWN
    classification: str  # "REQUIRED", "RECOMMENDED", "OPTIONAL", "UNKNOWN"
    status: str  # "SATISFIED", "MISSING", "CATALOG_RESOURCE_TYPE_UNKNOWN"
    reason: Optional[str] = None
    matched_resource_id: Optional[UUID] = None  # The resource that satisfies the dependency, if satisfied
    matched_resource_key: Optional[str] = None
    catalog_dependency_id: Optional[UUID] = None


class ArchitectureDependencyAnalysisResponse(BaseModel):
    """Schema for full dependency analysis of an architecture version."""

    architecture_id: UUID
    architecture_version_id: UUID
    total_findings: int
    required_findings: int
    recommended_findings: int
    optional_findings: int
    satisfied_count: int
    missing_count: int
    findings: List[DependencyFindingResponse]

    class Config:
        from_attributes = True


# ==================== VALIDATION ENGINE SCHEMAS ====================


class ValidationFindingResponse(BaseModel):
    """Schema for a single validation finding."""
    
    architecture_id: UUID
    architecture_version_id: UUID
    severity: str  # "ERROR", "WARNING", "INFO"
    category: str  # "RESOURCE", "HIERARCHY", "DEPENDENCY", "RELATIONSHIP", "CATALOG"
    code: str  # Machine-readable code (e.g., "RESOURCE_TYPE_NOT_IN_CATALOG")
    message: str  # Human-readable message
    resource_id: Optional[UUID] = None  # The primary resource involved
    related_resource_id: Optional[UUID] = None  # Secondary resource if applicable
    details: Optional[dict] = None  # Additional structured data
    
    class Config:
        from_attributes = True


class ArchitectureValidationResponse(BaseModel):
    """Schema for architecture version validation results."""
    
    architecture_id: UUID
    architecture_version_id: UUID
    status: str  # "VALID" or "INVALID"
    error_count: int
    warning_count: int
    info_count: int
    total_findings: int
    findings: List[ValidationFindingResponse]
    
    class Config:
        from_attributes = True


# ==================== COMPLIANCE ENGINE SCHEMAS ====================


class ComplianceFrameworkResponse(BaseModel):
    """Schema for compliance framework metadata."""
    
    id: UUID
    framework_name: str
    framework_version: str
    display_name: str
    description: Optional[str]
    enabled: bool
    
    class Config:
        from_attributes = True


class ComplianceControlResponse(BaseModel):
    """Schema for compliance control metadata."""
    
    id: UUID
    framework_id: UUID
    control_code: str
    title: str
    description: Optional[str]
    category: str
    evaluation_type: str
    rule_version: str
    enabled: bool
    
    class Config:
        from_attributes = True


class ComplianceFindingResponse(BaseModel):
    """Schema for a single compliance control finding."""
    
    framework_id: UUID
    framework_name: str
    framework_version: str
    control_id: UUID
    control_code: str
    title: str
    category: str
    outcome: str  # PASS, FAIL, WARNING, RECOMMENDATION, NOT_EVALUATED
    policy_level: str  # BLOCK, REQUIRED, RECOMMENDATION
    message: str
    resource_id: Optional[UUID] = None
    related_resource_id: Optional[UUID] = None
    evidence: Optional[dict] = None
    rule_version: str
    
    class Config:
        from_attributes = True


class ComplianceFrameworkEvaluationResponse(BaseModel):
    """Schema for compliance evaluation results for a single framework."""
    
    architecture_id: UUID
    architecture_version_id: UUID
    framework_id: UUID
    framework_name: str
    framework_version: str
    overall_status: str  # PASSED, FAILED, REVIEW, BLOCKED, VALIDATION_BLOCKED
    total_controls: int
    passed_controls: int
    failed_controls: int
    warning_controls: int
    recommendation_controls: int
    not_evaluated_controls: int
    findings: List[ComplianceFindingResponse]
    
    class Config:
        from_attributes = True


class ComplianceEvaluationRequest(BaseModel):
    """Schema for compliance evaluation request."""
    
    frameworks: List[str]  # Framework names: HIPAA, GDPR, etc.


class ComplianceEvaluationResponse(BaseModel):
    """Schema for compliance evaluation results (multiple frameworks)."""
    
    architecture_id: UUID
    architecture_version_id: UUID
    requested_frameworks: List[str]
    evaluations: List[ComplianceFrameworkEvaluationResponse]
    timestamp: datetime
    
    class Config:
        from_attributes = True


# ==================== TERRAFORM GENERATOR SCHEMAS ====================


class TerraformGenerationRequest(BaseModel):
    """Optional comparison input for Terraform generation."""

    compare_to_version_id: Optional[UUID] = None


class TerraformGenerationFindingResponse(BaseModel):
    """Structured warning or error produced during generation."""

    code: str
    severity: str
    message: str
    resource_id: Optional[UUID] = None
    resource_type: Optional[str] = None
    details: Optional[dict] = None


class TerraformFileResponse(BaseModel):
    """A deterministic generated Terraform file."""

    path: str
    content: str
    resource_keys: List[str] = Field(default_factory=list)


class TerraformGenerationResponse(BaseModel):
    """Complete result for one architecture version generation."""

    architecture_id: UUID
    architecture_version_id: UUID
    generator_version: str
    status: str
    validation_status: str
    validation_findings: List[ValidationFindingResponse] = Field(default_factory=list)
    files: List[TerraformFileResponse] = Field(default_factory=list)
    warnings: List[TerraformGenerationFindingResponse] = Field(default_factory=list)
    errors: List[TerraformGenerationFindingResponse] = Field(default_factory=list)
    resources_processed: int
    resources_unsupported: List[UUID] = Field(default_factory=list)
    changed_files: List[str] = Field(default_factory=list)


class TerraformResourceChangeResponse(BaseModel):
    """Architecture resource change and its Terraform impact."""

    resource_key: str
    change_type: str
    from_resource_id: Optional[UUID] = None
    to_resource_id: Optional[UUID] = None
    affected_files: List[str] = Field(default_factory=list)


class TerraformChangeAnalysisResponse(BaseModel):
    """Deterministic generated-file comparison between two versions."""

    architecture_id: UUID
    from_version_id: UUID
    to_version_id: UUID
    added_resources: List[str] = Field(default_factory=list)
    removed_resources: List[str] = Field(default_factory=list)
    modified_resources: List[str] = Field(default_factory=list)
    unchanged_resources: List[str] = Field(default_factory=list)
    resource_changes: List[TerraformResourceChangeResponse] = Field(default_factory=list)
    affected_files: List[str] = Field(default_factory=list)
    unchanged_files: List[str] = Field(default_factory=list)
