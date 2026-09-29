"""
FastAPI routes for the API.
"""

from typing import List
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
)
from ..schemas import (
    ArchitectureCreate,
    ArchitectureUpdate,
    ArchitectureResponse,
    ArchitectureVersionCreate,
    ArchitectureVersionResponse,
    ResourceCreate,
    ResourceResponse,
    RelationshipCreate,
    RelationshipResponse,
    DependencyCreate,
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
    version: ArchitectureVersionCreate,
    db: Session = Depends(get_db),
) -> ArchitectureVersionResponse:
    """Create a new version of an architecture."""
    db_version = ArchitectureVersionService.create(db, architecture_id, version)
    if not db_version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Architecture not found",
        )
    return db_version


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


@router.get("/catalog/resources/{resource_type}", response_model=ResourceCatalogDetailResponse)
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
        metadata=resource.metadata,
        required_dependencies=[CatalogDependencyResponse.model_validate(dep) for dep in required],
        recommended_dependencies=[CatalogDependencyResponse.model_validate(dep) for dep in recommended],
        optional_dependencies=[CatalogDependencyResponse.model_validate(dep) for dep in optional],
        valid_parent_types=valid_parents,
        valid_child_types=valid_children,
        created_at=resource.created_at,
        updated_at=resource.updated_at,
    )


@router.get("/catalog/resources/{resource_type}/dependencies", response_model=CatalogDependenciesResponse)
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


@router.get("/catalog/resources/{resource_type}/terraform", response_model=TerraformMappingResponse)
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


@router.get("/catalog/categories", response_model=CatalogCategoriesResponse)
def list_catalog_categories(
    db: Session = Depends(get_db),
) -> CatalogCategoriesResponse:
    """List all categories of resources in the catalog."""
    categories = CatalogService.get_categories(db)
    return CatalogCategoriesResponse(categories=categories)


# ==================== Dependency Analysis Endpoints ====================


@router.get(
    "/architectures/{architecture_id}/versions/{version_id}/dependencies",
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
