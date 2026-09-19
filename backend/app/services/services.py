"""
Service classes for business logic.
"""

from typing import Optional, List
from uuid import UUID

from sqlalchemy.orm import Session

from ..models import (
    Architecture,
    ArchitectureVersion,
    Resource,
    Relationship,
    Dependency,
)
from ..schemas import (
    ArchitectureCreate,
    ArchitectureUpdate,
    ArchitectureVersionCreate,
    ResourceCreate,
    RelationshipCreate,
    DependencyCreate,
)


class ArchitectureService:
    """Service for managing architectures."""

    @staticmethod
    def create(db: Session, architecture: ArchitectureCreate) -> Architecture:
        """Create a new architecture."""
        db_architecture = Architecture(
            name=architecture.name,
            description=architecture.description,
            provider=architecture.provider,
        )
        db.add(db_architecture)
        db.commit()
        db.refresh(db_architecture)
        return db_architecture

    @staticmethod
    def get(db: Session, architecture_id: UUID) -> Optional[Architecture]:
        """Get an architecture by ID."""
        return db.query(Architecture).filter(Architecture.id == architecture_id).first()

    @staticmethod
    def list_all(db: Session) -> List[Architecture]:
        """List all architectures."""
        return db.query(Architecture).all()

    @staticmethod
    def update(db: Session, architecture_id: UUID, update_data: ArchitectureUpdate) -> Optional[Architecture]:
        """Update an architecture."""
        db_architecture = ArchitectureService.get(db, architecture_id)
        if not db_architecture:
            return None
        
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(db_architecture, field, value)
        
        db.commit()
        db.refresh(db_architecture)
        return db_architecture

    @staticmethod
    def delete(db: Session, architecture_id: UUID) -> bool:
        """Delete an architecture."""
        db_architecture = ArchitectureService.get(db, architecture_id)
        if not db_architecture:
            return False
        
        db.delete(db_architecture)
        db.commit()
        return True


class ArchitectureVersionService:
    """Service for managing architecture versions."""

    @staticmethod
    def create(
        db: Session,
        architecture_id: UUID,
        version: ArchitectureVersionCreate,
    ) -> Optional[ArchitectureVersion]:
        """Create a new architecture version."""
        # Verify architecture exists
        architecture = ArchitectureService.get(db, architecture_id)
        if not architecture:
            return None

        db_version = ArchitectureVersion(
            architecture_id=architecture_id,
            version_number=version.version_number,
            status=version.status,
            created_by=version.created_by,
        )
        db.add(db_version)
        db.commit()
        db.refresh(db_version)
        return db_version

    @staticmethod
    def get(db: Session, version_id: UUID) -> Optional[ArchitectureVersion]:
        """Get an architecture version by ID."""
        return db.query(ArchitectureVersion).filter(ArchitectureVersion.id == version_id).first()

    @staticmethod
    def list_by_architecture(db: Session, architecture_id: UUID) -> List[ArchitectureVersion]:
        """List all versions of an architecture."""
        return db.query(ArchitectureVersion).filter(
            ArchitectureVersion.architecture_id == architecture_id
        ).order_by(ArchitectureVersion.version_number).all()


class ResourceService:
    """Service for managing resources."""

    @staticmethod
    def create(
        db: Session,
        architecture_version_id: UUID,
        resource: ResourceCreate,
    ) -> Optional[Resource]:
        """Create a new resource."""
        # Verify architecture version exists
        version = ArchitectureVersionService.get(db, architecture_version_id)
        if not version:
            return None

        # If parent_resource_id is specified, verify it exists and belongs to same version
        if resource.parent_resource_id:
            parent = db.query(Resource).filter(
                Resource.id == resource.parent_resource_id,
                Resource.architecture_version_id == architecture_version_id,
            ).first()
            if not parent:
                raise ValueError("Parent resource not found or belongs to different version")

        db_resource = Resource(
            architecture_version_id=architecture_version_id,
            resource_key=resource.resource_key,
            resource_type=resource.resource_type,
            name=resource.name,
            location=resource.location,
            sku=resource.sku,
            properties=resource.properties,
            tags=resource.tags,
            parent_resource_id=resource.parent_resource_id,
        )
        db.add(db_resource)
        db.commit()
        db.refresh(db_resource)
        return db_resource

    @staticmethod
    def get(db: Session, resource_id: UUID) -> Optional[Resource]:
        """Get a resource by ID."""
        return db.query(Resource).filter(Resource.id == resource_id).first()

    @staticmethod
    def list_by_version(db: Session, architecture_version_id: UUID) -> List[Resource]:
        """List all resources in an architecture version."""
        return db.query(Resource).filter(
            Resource.architecture_version_id == architecture_version_id
        ).all()

    @staticmethod
    def list_by_type(db: Session, architecture_version_id: UUID, resource_type: str) -> List[Resource]:
        """List resources of a specific type in a version."""
        return db.query(Resource).filter(
            Resource.architecture_version_id == architecture_version_id,
            Resource.resource_type == resource_type,
        ).all()


class RelationshipService:
    """Service for managing relationships."""

    @staticmethod
    def create(
        db: Session,
        architecture_version_id: UUID,
        relationship: RelationshipCreate,
    ) -> Optional[Relationship]:
        """Create a new relationship."""
        # Verify both resources exist and belong to the same version
        source = db.query(Resource).filter(
            Resource.id == relationship.source_resource_id,
            Resource.architecture_version_id == architecture_version_id,
        ).first()
        target = db.query(Resource).filter(
            Resource.id == relationship.target_resource_id,
            Resource.architecture_version_id == architecture_version_id,
        ).first()

        if not source or not target:
            raise ValueError("Source or target resource not found or belongs to different version")

        if source.id == target.id:
            raise ValueError("Source and target resources cannot be the same")

        db_relationship = Relationship(
            architecture_version_id=architecture_version_id,
            source_resource_id=relationship.source_resource_id,
            target_resource_id=relationship.target_resource_id,
            relationship_type=relationship.relationship_type,
            metadata=relationship.metadata,
        )
        db.add(db_relationship)
        db.commit()
        db.refresh(db_relationship)
        return db_relationship

    @staticmethod
    def get(db: Session, relationship_id: UUID) -> Optional[Relationship]:
        """Get a relationship by ID."""
        return db.query(Relationship).filter(Relationship.id == relationship_id).first()

    @staticmethod
    def list_by_version(db: Session, architecture_version_id: UUID) -> List[Relationship]:
        """List all relationships in an architecture version."""
        return db.query(Relationship).filter(
            Relationship.architecture_version_id == architecture_version_id
        ).all()


class DependencyService:
    """Service for managing dependencies."""

    @staticmethod
    def create(
        db: Session,
        architecture_version_id: UUID,
        dependency: DependencyCreate,
    ) -> Optional[Dependency]:
        """Create a new dependency."""
        # Verify both resources exist and belong to the same version
        resource = db.query(Resource).filter(
            Resource.id == dependency.resource_id,
            Resource.architecture_version_id == architecture_version_id,
        ).first()
        depends_on = db.query(Resource).filter(
            Resource.id == dependency.depends_on_resource_id,
            Resource.architecture_version_id == architecture_version_id,
        ).first()

        if not resource or not depends_on:
            raise ValueError("Resource or dependency target not found or belongs to different version")

        if resource.id == depends_on.id:
            raise ValueError("Resource cannot depend on itself")

        db_dependency = Dependency(
            architecture_version_id=architecture_version_id,
            resource_id=dependency.resource_id,
            depends_on_resource_id=dependency.depends_on_resource_id,
            dependency_type=dependency.dependency_type,
            required=dependency.required,
            reason=dependency.reason,
        )
        db.add(db_dependency)
        db.commit()
        db.refresh(db_dependency)
        return db_dependency

    @staticmethod
    def get(db: Session, dependency_id: UUID) -> Optional[Dependency]:
        """Get a dependency by ID."""
        return db.query(Dependency).filter(Dependency.id == dependency_id).first()

    @staticmethod
    def list_by_version(db: Session, architecture_version_id: UUID) -> List[Dependency]:
        """List all dependencies in an architecture version."""
        return db.query(Dependency).filter(
            Dependency.architecture_version_id == architecture_version_id
        ).all()

    @staticmethod
    def list_by_resource(db: Session, resource_id: UUID) -> List[Dependency]:
        """List all dependencies for a specific resource."""
        return db.query(Dependency).filter(
            Dependency.resource_id == resource_id
        ).all()
