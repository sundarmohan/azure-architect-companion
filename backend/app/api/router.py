"""
FastAPI routes for the API.
"""

from typing import List, Optional, Union
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..services import (
    ArchitectureService,
    ArchitectureVersionService,
    ResourceService,
    RelationshipService,
    DependencyService,
    CatalogService,
    DependencyEngine,
    ValidationEngine,
    ComplianceFrameworkService,
    ComplianceEngine,
    TerraformGenerator,
    TerraformExecutionError,
    TerraformExecutionService,
    ArchitectureVersioningError,
    ArchitectureVersioningService,
    AzureIntelligenceError,
    AzureResourceIntelligenceService,
    ConformanceEngine,
    ConformanceError,
)
from ..schemas import (
    ArchitectureCreate,
    ArchitectureUpdate,
    ArchitectureResponse,
    ArchitectureVersionCreate,
    ArchitectureSnapshotCreate,
    ArchitectureVersionActivateRequest,
    ArchitectureVersionRevertRequest,
    ArchitectureVersionResponse,
    ArchitectureVersionComparisonResponse,
    ArchitectureVersionEventResponse,
    ResourceCreate,
    ResourceUpdate,
    ResourceResponse,
    RelationshipCreate,
    RelationshipUpdate,
    RelationshipResponse,
    DependencyCreate,
    DependencyUpdate,
    DependencyResponse,
    ResourceCatalogResponse,
    ResourceCatalogDetailResponse,
    ResourceCatalogListResponse,
    CatalogDependenciesResponse,
    ArchitectureDependencyAnalysisResponse,
    DependencyFindingResponse,
    CatalogDependencyResponse,
    CatalogCategoriesResponse,
    TerraformMappingResponse,
    ArchitectureValidationResponse,
    ComplianceFrameworkResponse,
    ComplianceControlResponse,
    ComplianceFindingResponse,
    ComplianceFrameworkEvaluationResponse,
    ComplianceEvaluationRequest,
    ComplianceEvaluationResponse,
    TerraformGenerationRequest,
    TerraformGenerationResponse,
    TerraformChangeAnalysisResponse,
    TerraformExecutionPrepareRequest,
    TerraformApprovalRequest,
    TerraformRejectionRequest,
    TerraformExecutionResponse,
    TerraformExecutionEventResponse,
    AzureIntelligenceRefreshRequest,
    AzurePreflightRequest,
    AzureConnectionStatusResponse,
    AzureIntelligenceSnapshotResponse,
    AzureIntelligenceEvidenceResponse,
    AzureProviderResponse,
    AzurePreflightResultResponse,
    ConformanceAssessmentRequest,
    ConformanceAssessmentResponse,
    DriftHistoryComparisonResponse,
)

router = APIRouter()


# ==================== Architecture Endpoints ====================


@router.post("/architectures", response_model=ArchitectureResponse, status_code=status.HTTP_201_CREATED)
def create_architecture(
    architecture: ArchitectureCreate,
    db: Session = Depends(get_db),
) -> ArchitectureResponse:
    """Create a new architecture."""
    return ArchitectureService.create(db, architecture)


@router.get("/architectures/{architecture_id}", response_model=ArchitectureResponse)
def get_architecture(
    architecture_id: UUID,
    db: Session = Depends(get_db),
) -> ArchitectureResponse:
    """Get an architecture by ID."""
    architecture = ArchitectureService.get(db, architecture_id)
    if not architecture:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture not found",
        )
    return architecture


@router.get("/architectures", response_model=List[ArchitectureResponse])
def list_architectures(
    db: Session = Depends(get_db),
) -> List[ArchitectureResponse]:
    """List all architectures."""
    return ArchitectureService.list_all(db)


@router.put("/architectures/{architecture_id}", response_model=ArchitectureResponse)
def update_architecture(
    architecture_id: UUID,
    architecture: ArchitectureUpdate,
    db: Session = Depends(get_db),
) -> ArchitectureResponse:
    """Update an architecture."""
    updated = ArchitectureService.update(db, architecture_id, architecture)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture not found",
        )
    return updated


@router.delete("/architectures/{architecture_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_architecture(
    architecture_id: UUID,
    db: Session = Depends(get_db),
) -> None:
    """Delete an architecture."""
    if not ArchitectureService.delete(db, architecture_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture not found",
        )


# ==================== Architecture Version Endpoints ====================


@router.post(
    "/architectures/{architecture_id}/versions",
    response_model=ArchitectureVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_version(
    architecture_id: UUID,
    version: Union[ArchitectureSnapshotCreate, ArchitectureVersionCreate],
    db: Session = Depends(get_db),
) -> ArchitectureVersionResponse:
    """Create a new version of an architecture."""
    if isinstance(version, ArchitectureSnapshotCreate):
        try:
            return ArchitectureVersioningService.create_version(
                db,
                architecture_id,
                version.source_version_id,
                version.change_description,
                version.created_by,
                version.metadata,
            )
        except ArchitectureVersioningError as error:
            raise _versioning_http_error(error) from error
    try:
        db_version = ArchitectureVersionService.create(db, architecture_id, version)
    except ArchitectureVersioningError as error:
        raise _versioning_http_error(error) from error
    if not db_version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture not found",
        )
    return db_version


@router.post(
    "/architectures/{architecture_id}/versions/{version_id}/activate",
    response_model=ArchitectureVersionResponse,
)
def activate_version(
    architecture_id: UUID,
    version_id: UUID,
    request: ArchitectureVersionActivateRequest,
    db: Session = Depends(get_db),
) -> ArchitectureVersionResponse:
    """Finalize and activate an architecture snapshot."""
    try:
        return ArchitectureVersioningService.activate(
            db, architecture_id, version_id, request.actor
        )
    except ArchitectureVersioningError as error:
        raise _versioning_http_error(error) from error


@router.post(
    "/architectures/{architecture_id}/versions/{target_version_id}/revert",
    response_model=ArchitectureVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
def revert_version(
    architecture_id: UUID,
    target_version_id: UUID,
    request: ArchitectureVersionRevertRequest,
    db: Session = Depends(get_db),
) -> ArchitectureVersionResponse:
    """Create a new draft snapshot equivalent to an earlier version."""
    if request.target_version_id != target_version_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "TARGET_VERSION_MISMATCH", "message": "Path and request target versions differ"},
        )
    try:
        return ArchitectureVersioningService.revert(
            db,
            architecture_id,
            target_version_id,
            request.change_description,
            request.created_by,
        )
    except ArchitectureVersioningError as error:
        raise _versioning_http_error(error) from error


@router.get(
    "/architectures/{architecture_id}/versions/{from_version_id}/compare/{to_version_id}",
    response_model=ArchitectureVersionComparisonResponse,
)
def compare_architecture_versions(
    architecture_id: UUID,
    from_version_id: UUID,
    to_version_id: UUID,
    db: Session = Depends(get_db),
) -> ArchitectureVersionComparisonResponse:
    """Compare two complete canonical architecture snapshots."""
    try:
        return ArchitectureVersioningService.compare_versions(
            db, architecture_id, from_version_id, to_version_id
        )
    except ArchitectureVersioningError as error:
        raise _versioning_http_error(error) from error


@router.get(
    "/architectures/{architecture_id}/versions/{version_id}/events",
    response_model=List[ArchitectureVersionEventResponse],
)
def list_version_events(
    architecture_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
) -> List[ArchitectureVersionEventResponse]:
    """List append-only audit events for an architecture version."""
    try:
        return ArchitectureVersioningService.list_events(
            db, architecture_id, version_id
        )
    except ArchitectureVersioningError as error:
        raise _versioning_http_error(error) from error


def _versioning_http_error(error: ArchitectureVersioningError) -> HTTPException:
    if error.code in {"ARCHITECTURE_NOT_FOUND", "VERSION_NOT_FOUND"}:
        status_code = status.HTTP_404_NOT_FOUND
    elif error.code in {
        "NO_CHANGES",
        "VERSION_IMMUTABLE",
        "VERSION_NOT_DRAFT",
        "VERSION_ACTIVATION_CONFLICT",
        "VERSION_NUMBER_CONFLICT",
    }:
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(
        status_code=status_code,
        detail={
            "code": error.code,
            "message": error.message,
            **({"details": error.details} if error.details is not None else {}),
        },
    )


@router.get(
    "/architectures/{architecture_id}/versions/{version_id}",
    response_model=ArchitectureVersionResponse,
)
def get_version(
    architecture_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
) -> ArchitectureVersionResponse:
    """Get a specific version of an architecture."""
    version = ArchitectureVersionService.get(db, version_id)
    if not version or version.architecture_id != architecture_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found",
        )
    return version


@router.get(
    "/architectures/{architecture_id}/versions",
    response_model=List[ArchitectureVersionResponse],
)
def list_versions(
    architecture_id: UUID,
    db: Session = Depends(get_db),
) -> List[ArchitectureVersionResponse]:
    """List all versions of an architecture."""
    # Verify architecture exists
    if not ArchitectureService.get(db, architecture_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture not found",
        )
    return ArchitectureVersionService.list_by_architecture(db, architecture_id)


# ==================== Resource Endpoints ====================


@router.post(
    "/architectures/{architecture_id}/versions/{version_id}/resources",
    response_model=ResourceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_resource(
    architecture_id: UUID,
    version_id: UUID,
    resource: ResourceCreate,
    db: Session = Depends(get_db),
) -> ResourceResponse:
    """Create a new resource in a version."""
    version = ArchitectureVersionService.get(db, version_id)
    if not version or version.architecture_id != architecture_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found",
        )
    
    try:
        db_resource = ResourceService.create(db, version_id, resource)
        if not db_resource:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create resource",
            )
        return db_resource
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/architectures/{architecture_id}/versions/{version_id}/resources/{resource_id}",
    response_model=ResourceResponse,
)
def get_resource(
    architecture_id: UUID,
    version_id: UUID,
    resource_id: UUID,
    db: Session = Depends(get_db),
) -> ResourceResponse:
    """Get a specific resource."""
    version = ArchitectureVersionService.get(db, version_id)
    if not version or version.architecture_id != architecture_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found",
        )
    
    resource = ResourceService.get(db, resource_id)
    if not resource or resource.architecture_version_id != version_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        )
    return resource


@router.get(
    "/architectures/{architecture_id}/versions/{version_id}/resources",
    response_model=List[ResourceResponse],
)
def list_resources(
    architecture_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
) -> List[ResourceResponse]:
    """List all resources in a version."""
    version = ArchitectureVersionService.get(db, version_id)
    if not version or version.architecture_id != architecture_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found",
        )
    return ResourceService.list_by_version(db, version_id)


@router.put(
    "/architectures/{architecture_id}/versions/{version_id}/resources/{resource_id}",
    response_model=ResourceResponse,
)
def update_resource(
    architecture_id: UUID,
    version_id: UUID,
    resource_id: UUID,
    resource: ResourceUpdate,
    db: Session = Depends(get_db),
) -> ResourceResponse:
    version = ArchitectureVersionService.get(db, version_id)
    if not version or version.architecture_id != architecture_id:
        raise HTTPException(status_code=404, detail="Version not found")
    try:
        updated = ResourceService.update(db, version_id, resource_id, resource)
    except ArchitectureVersioningError as error:
        raise _versioning_http_error(error) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not updated:
        raise HTTPException(status_code=404, detail="Resource not found")
    return updated


@router.delete(
    "/architectures/{architecture_id}/versions/{version_id}/resources/{resource_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_resource(
    architecture_id: UUID,
    version_id: UUID,
    resource_id: UUID,
    db: Session = Depends(get_db),
) -> None:
    version = ArchitectureVersionService.get(db, version_id)
    if not version or version.architecture_id != architecture_id:
        raise HTTPException(status_code=404, detail="Version not found")
    try:
        deleted = ResourceService.delete(db, version_id, resource_id)
    except ArchitectureVersioningError as error:
        raise _versioning_http_error(error) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not deleted:
        raise HTTPException(status_code=404, detail="Resource not found")


# ==================== Relationship Endpoints ====================


@router.post(
    "/architectures/{architecture_id}/versions/{version_id}/relationships",
    response_model=RelationshipResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_relationship(
    architecture_id: UUID,
    version_id: UUID,
    relationship: RelationshipCreate,
    db: Session = Depends(get_db),
) -> RelationshipResponse:
    """Create a new relationship in a version."""
    version = ArchitectureVersionService.get(db, version_id)
    if not version or version.architecture_id != architecture_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found",
        )
    
    try:
        db_relationship = RelationshipService.create(db, version_id, relationship)
        if not db_relationship:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create relationship",
            )
        return db_relationship
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/architectures/{architecture_id}/versions/{version_id}/relationships",
    response_model=List[RelationshipResponse],
)
def list_relationships(
    architecture_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
) -> List[RelationshipResponse]:
    """List all relationships in a version."""
    version = ArchitectureVersionService.get(db, version_id)
    if not version or version.architecture_id != architecture_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found",
        )
    return RelationshipService.list_by_version(db, version_id)


@router.put(
    "/architectures/{architecture_id}/versions/{version_id}/relationships/{relationship_id}",
    response_model=RelationshipResponse,
)
def update_relationship(
    architecture_id: UUID,
    version_id: UUID,
    relationship_id: UUID,
    relationship: RelationshipUpdate,
    db: Session = Depends(get_db),
) -> RelationshipResponse:
    version = ArchitectureVersionService.get(db, version_id)
    if not version or version.architecture_id != architecture_id:
        raise HTTPException(status_code=404, detail="Version not found")
    try:
        updated = RelationshipService.update(db, version_id, relationship_id, relationship)
    except ArchitectureVersioningError as error:
        raise _versioning_http_error(error) from error
    if not updated:
        raise HTTPException(status_code=404, detail="Relationship not found")
    return updated


@router.delete(
    "/architectures/{architecture_id}/versions/{version_id}/relationships/{relationship_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_relationship(
    architecture_id: UUID,
    version_id: UUID,
    relationship_id: UUID,
    db: Session = Depends(get_db),
) -> None:
    version = ArchitectureVersionService.get(db, version_id)
    if not version or version.architecture_id != architecture_id:
        raise HTTPException(status_code=404, detail="Version not found")
    try:
        deleted = RelationshipService.delete(db, version_id, relationship_id)
    except ArchitectureVersioningError as error:
        raise _versioning_http_error(error) from error
    if not deleted:
        raise HTTPException(status_code=404, detail="Relationship not found")


# ==================== Dependency Endpoints ====================


@router.post(
    "/architectures/{architecture_id}/versions/{version_id}/dependencies",
    response_model=DependencyResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_dependency(
    architecture_id: UUID,
    version_id: UUID,
    dependency: DependencyCreate,
    db: Session = Depends(get_db),
) -> DependencyResponse:
    """Create a new dependency in a version."""
    version = ArchitectureVersionService.get(db, version_id)
    if not version or version.architecture_id != architecture_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found",
        )
    
    try:
        db_dependency = DependencyService.create(db, version_id, dependency)
        if not db_dependency:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create dependency",
            )
        return db_dependency
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/architectures/{architecture_id}/versions/{version_id}/dependencies",
    response_model=List[DependencyResponse],
)
def list_dependencies(
    architecture_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
) -> List[DependencyResponse]:
    """List all dependencies in a version."""
    version = ArchitectureVersionService.get(db, version_id)
    if not version or version.architecture_id != architecture_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found",
        )
    return DependencyService.list_by_version(db, version_id)


@router.put(
    "/architectures/{architecture_id}/versions/{version_id}/dependencies/{dependency_id}",
    response_model=DependencyResponse,
)
def update_dependency(
    architecture_id: UUID,
    version_id: UUID,
    dependency_id: UUID,
    dependency: DependencyUpdate,
    db: Session = Depends(get_db),
) -> DependencyResponse:
    version = ArchitectureVersionService.get(db, version_id)
    if not version or version.architecture_id != architecture_id:
        raise HTTPException(status_code=404, detail="Version not found")
    try:
        updated = DependencyService.update(db, version_id, dependency_id, dependency)
    except ArchitectureVersioningError as error:
        raise _versioning_http_error(error) from error
    if not updated:
        raise HTTPException(status_code=404, detail="Dependency not found")
    return updated


@router.delete(
    "/architectures/{architecture_id}/versions/{version_id}/dependencies/{dependency_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_dependency(
    architecture_id: UUID,
    version_id: UUID,
    dependency_id: UUID,
    db: Session = Depends(get_db),
) -> None:
    version = ArchitectureVersionService.get(db, version_id)
    if not version or version.architecture_id != architecture_id:
        raise HTTPException(status_code=404, detail="Version not found")
    try:
        deleted = DependencyService.delete(db, version_id, dependency_id)
    except ArchitectureVersioningError as error:
        raise _versioning_http_error(error) from error
    if not deleted:
        raise HTTPException(status_code=404, detail="Dependency not found")


# ==================== Resource Catalog Endpoints ====================


@router.get("/catalog/resources", response_model=ResourceCatalogListResponse)
def list_catalog_resources(
    provider: str = None,
    category: str = None,
    db: Session = Depends(get_db),
) -> ResourceCatalogListResponse:
    """List resource types from the catalog, optionally filtered by provider or category."""
    if provider:
        resources = CatalogService.list_by_provider(db, provider)
    elif category:
        resources = CatalogService.list_by_category(db, category)
    else:
        resources = CatalogService.list_all_resources(db)

    return ResourceCatalogListResponse(total=len(resources), resources=resources)


@router.get("/catalog/resources/{resource_type:path}/dependencies", response_model=CatalogDependenciesResponse)
def get_resource_dependencies(
    resource_type: str,
    db: Session = Depends(get_db),
) -> CatalogDependenciesResponse:
    """Get dependencies for a resource type."""
    if not CatalogService.resource_type_exists(db, resource_type):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource type {resource_type} not found in catalog",
        )

    required = CatalogService.get_required_dependencies(db, resource_type)
    recommended = CatalogService.get_recommended_dependencies(db, resource_type)
    optional = CatalogService.get_optional_dependencies(db, resource_type)

    return CatalogDependenciesResponse(
        resource_type=resource_type,
        required=[CatalogDependencyResponse.model_validate(dep) for dep in required],
        recommended=[CatalogDependencyResponse.model_validate(dep) for dep in recommended],
        optional=[CatalogDependencyResponse.model_validate(dep) for dep in optional],
    )


@router.get("/catalog/resources/{resource_type:path}/terraform", response_model=TerraformMappingResponse)
def get_resource_terraform_mapping(
    resource_type: str,
    db: Session = Depends(get_db),
) -> TerraformMappingResponse:
    """Get Terraform mapping for a resource type."""
    resource = CatalogService.get_resource_type(db, resource_type)
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource type {resource_type} not found in catalog",
        )

    terraform_mapping = resource.terraform_mapping or {}
    return TerraformMappingResponse(
        resource_type=resource_type,
        terraform_type=terraform_mapping.get("terraform_type"),
        provider=terraform_mapping.get("provider"),
        additional_mapping=terraform_mapping.get("additional_mapping"),
    )


@router.get("/catalog/resources/{resource_type:path}", response_model=ResourceCatalogDetailResponse)
def get_catalog_resource(
    resource_type: str,
    db: Session = Depends(get_db),
) -> ResourceCatalogDetailResponse:
    """Get detailed information about a resource type from the catalog."""
    resource = CatalogService.get_resource_type(db, resource_type)
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource type {resource_type} not found in catalog",
        )

    required = CatalogService.get_required_dependencies(db, resource_type)
    recommended = CatalogService.get_recommended_dependencies(db, resource_type)
    optional = CatalogService.get_optional_dependencies(db, resource_type)
    valid_parents = CatalogService.get_valid_parent_types(db, resource_type)
    valid_children = CatalogService.get_valid_child_types(db, resource_type)

    return ResourceCatalogDetailResponse(
        id=resource.id,
        provider=resource.provider,
        resource_type=resource.resource_type,
        display_name=resource.display_name,
        category=resource.category,
        description=resource.description,
        version=resource.version,
        enabled=resource.enabled,
        properties_schema=resource.properties_schema,
        default_properties=resource.default_properties,
        terraform_mapping=resource.terraform_mapping,
        metadata=resource.resource_metadata,
        required_dependencies=[CatalogDependencyResponse.model_validate(dep) for dep in required],
        recommended_dependencies=[CatalogDependencyResponse.model_validate(dep) for dep in recommended],
        optional_dependencies=[CatalogDependencyResponse.model_validate(dep) for dep in optional],
        valid_parent_types=valid_parents,
        valid_child_types=valid_children,
        networking_requirements=[item.requirement for item in resource.networking_requirements],
        security_requirements=[item.requirement for item in resource.security_requirements],
        monitoring_requirements=[item.requirement for item in resource.monitoring_requirements],
        backup_requirements=[item.requirement for item in resource.backup_requirements],
        created_at=resource.created_at,
        updated_at=resource.updated_at,
    )


@router.get("/catalog/categories", response_model=CatalogCategoriesResponse)
def list_catalog_categories(
    db: Session = Depends(get_db),
) -> CatalogCategoriesResponse:
    """List all categories of resources in the catalog."""
    categories = CatalogService.get_categories(db)
    return CatalogCategoriesResponse(categories=categories)


# ==================== Dependency Analysis Endpoints ====================


@router.get(
    "/architectures/{architecture_id}/versions/{version_id}/dependency-analysis",
    response_model=ArchitectureDependencyAnalysisResponse,
)
def analyze_architecture_dependencies(
    architecture_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
) -> ArchitectureDependencyAnalysisResponse:
    """
    Analyze an architecture version for dependency satisfaction.
    
    Returns findings for all dependencies of resources in the architecture,
    indicating whether each dependency is satisfied or missing.
    """
    # Verify the architecture exists
    architecture = ArchitectureService.get(db, architecture_id)
    if not architecture:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture not found",
        )

    # Verify the version belongs to this architecture
    version = ArchitectureVersionService.get(db, version_id)
    if not version or version.architecture_id != architecture_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture version not found",
        )

    # Analyze dependencies
    try:
        analysis = DependencyEngine.analyze_version(db, architecture_id, version_id)
        return ArchitectureDependencyAnalysisResponse(**analysis)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ==================== VALIDATION ENDPOINTS ====================


@router.get(
    "/architectures/{architecture_id}/versions/{version_id}/validation",
    response_model=ArchitectureValidationResponse,
)
def validate_architecture(
    architecture_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
) -> ArchitectureValidationResponse:
    """
    Validate an architecture version for structural and technical correctness.
    
    Performs:
    - Resource validation (type, identity, duplicates)
    - Hierarchy validation (using CatalogHierarchy)
    - Relationship validation
    - Dependency validation (using Dependency Engine)
    - Catalog validation
    
    Returns validation findings with severity levels:
    - ERROR: Blocking issue (architecture is INVALID)
    - WARNING: Non-blocking concern
    - INFO: Informational finding
    
    Overall status is INVALID if any ERROR exists, otherwise VALID.
    
    Does NOT perform:
    - Compliance checks (see Milestone 5)
    - Azure live validation
    - Terraform validation
    - AI-based recommendations
    """
    # Verify the architecture exists
    architecture = ArchitectureService.get(db, architecture_id)
    if not architecture:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture not found",
        )

    # Verify the version belongs to this architecture
    version = ArchitectureVersionService.get(db, version_id)
    if not version or version.architecture_id != architecture_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture version not found",
        )

    # Validate the version
    try:
        validation = ValidationEngine.validate_version(db, architecture_id, version_id)
        return ArchitectureValidationResponse(**validation)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ==================== TERRAFORM GENERATOR ENDPOINTS ====================


@router.post(
    "/architectures/{architecture_id}/versions/{version_id}/terraform/generate",
    response_model=TerraformGenerationResponse,
)
def generate_terraform(
    architecture_id: UUID,
    version_id: UUID,
    request: Optional[TerraformGenerationRequest] = None,
    db: Session = Depends(get_db),
) -> TerraformGenerationResponse:
    """Generate Terraform without executing Terraform or contacting Azure."""
    try:
        result = TerraformGenerator.generate(
            db,
            architecture_id,
            version_id,
            request.compare_to_version_id if request else None,
            request.mode if request else "STATIC_ONLY",
            request.azure_preflight_id if request else None,
        )
        return TerraformGenerationResponse(**result)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        )


@router.get(
    "/architectures/{architecture_id}/versions/{version_id}/terraform",
    response_model=TerraformGenerationResponse,
)
def get_generated_terraform(
    architecture_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
) -> TerraformGenerationResponse:
    """Retrieve generated Terraform by deterministically regenerating it."""
    try:
        return TerraformGenerationResponse(
            **TerraformGenerator.generate(db, architecture_id, version_id)
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        )


@router.get(
    "/architectures/{architecture_id}/versions/{from_version_id}/terraform/changes/{to_version_id}",
    response_model=TerraformChangeAnalysisResponse,
)
def analyze_terraform_changes(
    architecture_id: UUID,
    from_version_id: UUID,
    to_version_id: UUID,
    db: Session = Depends(get_db),
) -> TerraformChangeAnalysisResponse:
    """Compare canonical resources and generated files across two versions."""
    try:
        result = TerraformGenerator.compare_versions(
            db, architecture_id, from_version_id, to_version_id
        )
        return TerraformChangeAnalysisResponse(**result)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


# ==================== TERRAFORM EXECUTION ENDPOINTS ====================


def _raise_execution_http_error(error: TerraformExecutionError) -> None:
    status_code = (
        status.HTTP_404_NOT_FOUND
        if error.code == "EXECUTION_NOT_FOUND"
        else status.HTTP_409_CONFLICT
        if error.code
        in {
            "DESTRUCTIVE_APPROVAL_REQUIRED",
            "EXECUTION_LOCKED",
            "INVALID_EXECUTION_STATE",
        }
        else status.HTTP_400_BAD_REQUEST
    )
    raise HTTPException(
        status_code=status_code,
        detail={"code": error.code, "message": error.message},
    )


@router.post(
    "/architectures/{architecture_id}/versions/{version_id}/terraform/executions",
    response_model=TerraformExecutionResponse,
    status_code=status.HTTP_201_CREATED,
)
def prepare_terraform_execution(
    architecture_id: UUID,
    version_id: UUID,
    request: TerraformExecutionPrepareRequest,
    db: Session = Depends(get_db),
) -> TerraformExecutionResponse:
    """Generate Terraform and prepare an isolated execution workspace."""
    try:
        return TerraformExecutionService.prepare_workspace(
            db,
            architecture_id,
            version_id,
            request.compliance_frameworks,
            request.azure_preflight_id,
        )
    except TerraformExecutionError as error:
        _raise_execution_http_error(error)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


@router.get(
    "/terraform/executions/{execution_id}",
    response_model=TerraformExecutionResponse,
)
def get_terraform_execution(
    execution_id: UUID,
    db: Session = Depends(get_db),
) -> TerraformExecutionResponse:
    execution = TerraformExecutionService.get_execution(db, execution_id)
    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Terraform execution not found",
        )
    return execution


@router.post(
    "/terraform/executions/{execution_id}/initialize",
    response_model=TerraformExecutionResponse,
)
def initialize_terraform(
    execution_id: UUID,
    db: Session = Depends(get_db),
) -> TerraformExecutionResponse:
    try:
        return TerraformExecutionService.initialize(db, execution_id)
    except TerraformExecutionError as error:
        _raise_execution_http_error(error)


@router.post(
    "/terraform/executions/{execution_id}/validate",
    response_model=TerraformExecutionResponse,
)
def validate_terraform(
    execution_id: UUID,
    db: Session = Depends(get_db),
) -> TerraformExecutionResponse:
    try:
        return TerraformExecutionService.validate(db, execution_id)
    except TerraformExecutionError as error:
        _raise_execution_http_error(error)


@router.post(
    "/terraform/executions/{execution_id}/plan",
    response_model=TerraformExecutionResponse,
)
def create_terraform_plan(
    execution_id: UUID,
    db: Session = Depends(get_db),
) -> TerraformExecutionResponse:
    try:
        return TerraformExecutionService.create_plan(db, execution_id)
    except TerraformExecutionError as error:
        _raise_execution_http_error(error)


@router.post(
    "/terraform/executions/{execution_id}/approve",
    response_model=TerraformExecutionResponse,
)
def approve_terraform_plan(
    execution_id: UUID,
    request: TerraformApprovalRequest,
    db: Session = Depends(get_db),
) -> TerraformExecutionResponse:
    try:
        return TerraformExecutionService.approve_plan(
            db,
            execution_id,
            request.approved_by,
            request.confirm_destructive,
        )
    except TerraformExecutionError as error:
        _raise_execution_http_error(error)


@router.post(
    "/terraform/executions/{execution_id}/reject",
    response_model=TerraformExecutionResponse,
)
def reject_terraform_plan(
    execution_id: UUID,
    request: TerraformRejectionRequest,
    db: Session = Depends(get_db),
) -> TerraformExecutionResponse:
    try:
        return TerraformExecutionService.reject_plan(
            db, execution_id, request.rejected_by, request.reason
        )
    except TerraformExecutionError as error:
        _raise_execution_http_error(error)


@router.post(
    "/terraform/executions/{execution_id}/apply",
    response_model=TerraformExecutionResponse,
)
def apply_terraform_plan(
    execution_id: UUID,
    db: Session = Depends(get_db),
) -> TerraformExecutionResponse:
    try:
        return TerraformExecutionService.apply_approved_plan(db, execution_id)
    except TerraformExecutionError as error:
        _raise_execution_http_error(error)


@router.get(
    "/terraform/executions/{execution_id}/events",
    response_model=List[TerraformExecutionEventResponse],
)
def list_terraform_execution_events(
    execution_id: UUID,
    db: Session = Depends(get_db),
) -> List[TerraformExecutionEventResponse]:
    if TerraformExecutionService.get_execution(db, execution_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Terraform execution not found",
        )
    return TerraformExecutionService.list_events(db, execution_id)


# ==================== AZURE RESOURCE INTELLIGENCE ENDPOINTS ====================


def _raise_azure_http_error(error: AzureIntelligenceError) -> None:
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": str(error)},
    )


def _azure_snapshot_response(snapshot) -> dict:
    return {
        "id": snapshot.id,
        "connection_id": snapshot.connection_id,
        "subscription_id": snapshot.subscription_id,
        "tenant_id": snapshot.tenant_id,
        "snapshot_sequence": snapshot.snapshot_sequence,
        "snapshot_hash": snapshot.snapshot_hash,
        "source_version": snapshot.source_version,
        "terraform_provider_version": snapshot.terraform_provider_version,
        "subscription_metadata": snapshot.subscription_metadata or {},
        "resource_groups": snapshot.resource_groups or [],
        "resource_types": snapshot.resource_types or [],
        "regions": snapshot.regions or [],
        "skus": snapshot.skus or [],
        "providers": snapshot.providers or [],
        "quotas": snapshot.quotas or [],
        "resources": snapshot.resources or [],
        "retrieved_at": snapshot.retrieved_at,
        "expires_at": snapshot.expires_at,
        **AzureResourceIntelligenceService.freshness(snapshot),
    }


def _latest_azure_snapshot(db: Session):
    snapshot = AzureResourceIntelligenceService.latest_snapshot(db)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "AZURE_SNAPSHOT_NOT_FOUND", "message": "No Azure intelligence snapshot is available"},
        )
    return snapshot


@router.get("/azure/intelligence/status", response_model=AzureConnectionStatusResponse)
def get_azure_intelligence_status() -> AzureConnectionStatusResponse:
    return AzureConnectionStatusResponse(**AzureResourceIntelligenceService.connection_status())


@router.post("/azure/intelligence/refresh", response_model=AzureIntelligenceSnapshotResponse, status_code=status.HTTP_201_CREATED)
def refresh_azure_intelligence(
    request: AzureIntelligenceRefreshRequest,
    db: Session = Depends(get_db),
) -> AzureIntelligenceSnapshotResponse:
    try:
        snapshot = AzureResourceIntelligenceService.refresh(
            db,
            regions=request.regions,
            terraform_provider_version=request.terraform_provider_version,
        )
        return AzureIntelligenceSnapshotResponse(**_azure_snapshot_response(snapshot))
    except AzureIntelligenceError as error:
        _raise_azure_http_error(error)


@router.get("/azure/intelligence/snapshots", response_model=List[AzureIntelligenceSnapshotResponse])
def list_azure_intelligence_snapshots(db: Session = Depends(get_db)) -> List[AzureIntelligenceSnapshotResponse]:
    return [AzureIntelligenceSnapshotResponse(**_azure_snapshot_response(item)) for item in AzureResourceIntelligenceService.list_snapshots(db)]


@router.get("/azure/intelligence/snapshots/{snapshot_id}", response_model=AzureIntelligenceSnapshotResponse)
def get_azure_intelligence_snapshot(snapshot_id: UUID, db: Session = Depends(get_db)) -> AzureIntelligenceSnapshotResponse:
    snapshot = AzureResourceIntelligenceService.get_snapshot(db, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "AZURE_SNAPSHOT_NOT_FOUND", "message": "Azure intelligence snapshot not found"})
    return AzureIntelligenceSnapshotResponse(**_azure_snapshot_response(snapshot))


@router.get("/azure/intelligence/resource-types", response_model=List[dict])
def list_azure_resource_types(db: Session = Depends(get_db)) -> List[dict]:
    snapshot = _latest_azure_snapshot(db)
    freshness = AzureResourceIntelligenceService.freshness(snapshot)
    return [{**item, **freshness} for item in (snapshot.resource_types or [])]


@router.get("/azure/intelligence/resource-types/{resource_type:path}/regions", response_model=Union[AzureIntelligenceEvidenceResponse, dict])
def get_azure_resource_type_region(resource_type: str, region: Optional[str] = None, db: Session = Depends(get_db)) -> Union[AzureIntelligenceEvidenceResponse, dict]:
    snapshot = _latest_azure_snapshot(db)
    if region is not None:
        return AzureIntelligenceEvidenceResponse(**AzureResourceIntelligenceService.region_intelligence(snapshot, resource_type, region))
    metadata = AzureResourceIntelligenceService._resource_type(snapshot, resource_type)
    return {"resource_type": resource_type, "regions": (metadata or {}).get("locations", []), **AzureResourceIntelligenceService.freshness(snapshot)}


@router.get("/azure/intelligence/resource-types/{resource_type:path}/skus", response_model=List[dict])
def list_azure_resource_type_skus(resource_type: str, region: Optional[str] = None, db: Session = Depends(get_db)) -> List[dict]:
    snapshot = _latest_azure_snapshot(db)
    items = [item for item in (snapshot.skus or []) if AzureResourceIntelligenceService._same(item.get("resource_type"), resource_type)]
    if region:
        items = [item for item in items if AzureResourceIntelligenceService._location_matches(region, item.get("locations") or [], snapshot.regions or [])]
    freshness = AzureResourceIntelligenceService.freshness(snapshot)
    return [{**item, **freshness} for item in items]


@router.get("/azure/intelligence/resource-types/{resource_type:path}", response_model=AzureIntelligenceEvidenceResponse)
def get_azure_resource_type(resource_type: str, region: Optional[str] = None, db: Session = Depends(get_db)) -> AzureIntelligenceEvidenceResponse:
    return AzureIntelligenceEvidenceResponse(**AzureResourceIntelligenceService.resource_type_intelligence(_latest_azure_snapshot(db), resource_type, region))


@router.get("/azure/intelligence/providers", response_model=List[AzureProviderResponse])
def list_azure_providers(db: Session = Depends(get_db)) -> List[AzureProviderResponse]:
    snapshot = _latest_azure_snapshot(db)
    return [AzureProviderResponse(**AzureResourceIntelligenceService.provider_intelligence(snapshot, item.get("namespace", ""))) for item in (snapshot.providers or [])]


@router.get("/azure/intelligence/quotas/{quota_name}", response_model=dict)
def get_azure_quota(quota_name: str, region: str, required: float = 0, db: Session = Depends(get_db)) -> dict:
    return AzureResourceIntelligenceService.quota_intelligence(_latest_azure_snapshot(db), quota_name, region, required)


@router.post("/architectures/{architecture_id}/versions/{version_id}/azure-preflight", response_model=AzurePreflightResultResponse, status_code=status.HTTP_201_CREATED)
def run_azure_preflight(
    architecture_id: UUID,
    version_id: UUID,
    request: AzurePreflightRequest,
    db: Session = Depends(get_db),
) -> AzurePreflightResultResponse:
    try:
        return AzureResourceIntelligenceService.preflight(db, architecture_id, version_id, request.snapshot_id)
    except AzureIntelligenceError as error:
        _raise_azure_http_error(error)


# ==================== CONFORMANCE AND DRIFT ENDPOINTS ====================


def _raise_conformance_http_error(error: ConformanceError) -> None:
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": str(error)},
    )


@router.post(
    "/architectures/{architecture_id}/versions/{version_id}/conformance",
    response_model=ConformanceAssessmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def run_conformance_assessment(
    architecture_id: UUID,
    version_id: UUID,
    request: ConformanceAssessmentRequest,
    db: Session = Depends(get_db),
) -> ConformanceAssessmentResponse:
    try:
        return ConformanceEngine.assess(
            db,
            architecture_id,
            version_id,
            request.azure_snapshot_id,
            request.terraform_execution_id,
        )
    except ConformanceError as error:
        _raise_conformance_http_error(error)


@router.get(
    "/architectures/{architecture_id}/versions/{version_id}/conformance",
    response_model=List[ConformanceAssessmentResponse],
)
def list_conformance_assessments(
    architecture_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
) -> List[ConformanceAssessmentResponse]:
    try:
        return ConformanceEngine.list_assessments(db, architecture_id, version_id)
    except ConformanceError as error:
        _raise_conformance_http_error(error)


@router.get(
    "/architectures/{architecture_id}/versions/{version_id}/drift",
    response_model=Optional[ConformanceAssessmentResponse],
)
def get_latest_drift_assessment(
    architecture_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
) -> Optional[ConformanceAssessmentResponse]:
    try:
        assessments = ConformanceEngine.list_assessments(db, architecture_id, version_id)
        return assessments[0] if assessments else None
    except ConformanceError as error:
        _raise_conformance_http_error(error)


@router.get(
    "/architectures/{architecture_id}/versions/{version_id}/drift/history",
    response_model=List[ConformanceAssessmentResponse],
)
def get_drift_history(
    architecture_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
) -> List[ConformanceAssessmentResponse]:
    try:
        return ConformanceEngine.list_assessments(db, architecture_id, version_id)
    except ConformanceError as error:
        _raise_conformance_http_error(error)


@router.get(
    "/architectures/{architecture_id}/versions/{version_id}/conformance/compare/{assessment_id}/{other_assessment_id}",
    response_model=DriftHistoryComparisonResponse,
)
def compare_conformance_assessments(
    architecture_id: UUID,
    version_id: UUID,
    assessment_id: UUID,
    other_assessment_id: UUID,
    db: Session = Depends(get_db),
) -> DriftHistoryComparisonResponse:
    try:
        return DriftHistoryComparisonResponse(**ConformanceEngine.compare_assessments(db, architecture_id, version_id, assessment_id, other_assessment_id))
    except ConformanceError as error:
        _raise_conformance_http_error(error)


@router.get(
    "/architectures/{architecture_id}/versions/{version_id}/conformance/{assessment_id}",
    response_model=ConformanceAssessmentResponse,
)
def get_conformance_assessment(
    architecture_id: UUID,
    version_id: UUID,
    assessment_id: UUID,
    db: Session = Depends(get_db),
) -> ConformanceAssessmentResponse:
    try:
        return ConformanceEngine.get(db, architecture_id, version_id, assessment_id)
    except ConformanceError as error:
        _raise_conformance_http_error(error)


# ==================== Compliance Engine Endpoints ====================


@router.get(
    "/compliance/frameworks",
    response_model=List[ComplianceFrameworkResponse],
)
def list_compliance_frameworks(
    db: Session = Depends(get_db),
) -> List[ComplianceFrameworkResponse]:
    """
    List all available compliance frameworks.
    """
    # Bootstrap frameworks on first access
    from ..models import ComplianceFramework
    
    count = db.query(ComplianceFramework).count()
    if count == 0:
        ComplianceFrameworkService.bootstrap_frameworks(db)
    
    frameworks = ComplianceFrameworkService.get_frameworks(db)
    return [ComplianceFrameworkResponse(**f) for f in frameworks]


@router.get(
    "/compliance/frameworks/{framework_name}",
    response_model=ComplianceFrameworkResponse,
)
def get_compliance_framework(
    framework_name: str,
    db: Session = Depends(get_db),
) -> ComplianceFrameworkResponse:
    """
    Get a specific compliance framework by name.
    """
    from ..models import ComplianceFramework, ComplianceControl
    
    # Bootstrap if needed
    count = db.query(ComplianceFramework).count()
    if count == 0:
        ComplianceFrameworkService.bootstrap_frameworks(db)
    
    framework = ComplianceFrameworkService.get_framework_by_name(db, framework_name)
    if not framework:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Framework {framework_name} not found",
        )
    
    # Get controls for this framework
    from ..models import ComplianceFramework
    db_framework = db.query(ComplianceFramework).filter(
        ComplianceFramework.framework_name == framework_name
    ).first()
    
    controls = db.query(ComplianceControl).filter(
        ComplianceControl.framework_id == db_framework.id
    ).all()
    
    framework_data = {
        **framework,
        "controls": [
            ComplianceControlResponse(
                id=c.id,
                framework_id=c.framework_id,
                control_code=c.control_code,
                title=c.title,
                description=c.description,
                category=c.category,
                evaluation_type=c.evaluation_type,
                rule_version=c.rule_version,
                enabled=c.enabled,
            )
            for c in controls
        ]
    }
    
    return ComplianceFrameworkResponse(**framework)


@router.post(
    "/architectures/{architecture_id}/versions/{version_id}/compliance",
    response_model=ComplianceEvaluationResponse,
)
def evaluate_architecture_compliance(
    architecture_id: UUID,
    version_id: UUID,
    request: ComplianceEvaluationRequest,
    db: Session = Depends(get_db),
) -> ComplianceEvaluationResponse:
    """
    Evaluate an architecture against selected compliance frameworks.
    
    Returns technical control evaluation results. This is NOT a legal
    or regulatory compliance certification.
    """
    from ..models import ComplianceFramework
    
    # Bootstrap frameworks if needed
    count = db.query(ComplianceFramework).count()
    if count == 0:
        ComplianceFrameworkService.bootstrap_frameworks(db)
    
    # Validate input
    if not request.frameworks or len(request.frameworks) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one framework must be selected",
        )

    # Verify architecture exists
    architecture = ArchitectureService.get(db, architecture_id)
    if not architecture:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture not found",
        )

    # Verify version exists
    version = ArchitectureVersionService.get(db, version_id)
    if not version or version.architecture_id != architecture_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture version not found",
        )

    # Evaluate compliance
    try:
        result = ComplianceEngine.evaluate_compliance(
            db,
            architecture_id,
            version_id,
            request.frameworks,
        )
        
        # Check for errors in result
        if "error" in result:
            if result.get("status") == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=result["error"],
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=result["error"],
                )
        
        return ComplianceEvaluationResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
