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
