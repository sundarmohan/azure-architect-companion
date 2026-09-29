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
    ResourceCatalog,
    CatalogDependency,
    CatalogHierarchy,
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


# ============================================================================
# CATALOG SERVICE - Resource Catalog management
# ============================================================================


class CatalogService:
    """Service for managing the Resource Catalog."""

    @staticmethod
    def register_resource_type(
        db: Session,
        provider: str,
        resource_type: str,
        display_name: str,
        category: str,
        description: Optional[str] = None,
        version: str = "1.0",
        properties_schema: Optional[dict] = None,
        default_properties: Optional[dict] = None,
        terraform_mapping: Optional[dict] = None,
        metadata: Optional[dict] = None,
    ) -> "ResourceCatalog":
        """Register a new resource type in the catalog."""
        from ..models import ResourceCatalog

        db_resource = ResourceCatalog(
            provider=provider,
            resource_type=resource_type,
            display_name=display_name,
            category=category,
            description=description,
            version=version,
            properties_schema=properties_schema,
            default_properties=default_properties,
            terraform_mapping=terraform_mapping,
            metadata=metadata,
            enabled=True,
        )
        db.add(db_resource)
        db.commit()
        db.refresh(db_resource)
        return db_resource

    @staticmethod
    def get_resource_type(db: Session, resource_type: str) -> Optional["ResourceCatalog"]:
        """Get a resource type by its type name."""
        from ..models import ResourceCatalog

        return db.query(ResourceCatalog).filter(
            ResourceCatalog.resource_type == resource_type,
            ResourceCatalog.enabled == True,
        ).first()

    @staticmethod
    def list_all_resources(db: Session) -> List["ResourceCatalog"]:
        """List all enabled resource types."""
        from ..models import ResourceCatalog

        return db.query(ResourceCatalog).filter(
            ResourceCatalog.enabled == True
        ).order_by(ResourceCatalog.category, ResourceCatalog.display_name).all()

    @staticmethod
    def list_by_provider(db: Session, provider: str) -> List["ResourceCatalog"]:
        """List all resource types for a specific provider."""
        from ..models import ResourceCatalog

        return db.query(ResourceCatalog).filter(
            ResourceCatalog.provider == provider,
            ResourceCatalog.enabled == True,
        ).order_by(ResourceCatalog.category, ResourceCatalog.display_name).all()

    @staticmethod
    def list_by_category(db: Session, category: str) -> List["ResourceCatalog"]:
        """List all resource types in a specific category."""
        from ..models import ResourceCatalog

        return db.query(ResourceCatalog).filter(
            ResourceCatalog.category == category,
            ResourceCatalog.enabled == True,
        ).order_by(ResourceCatalog.display_name).all()

    @staticmethod
    def resource_type_exists(db: Session, resource_type: str) -> bool:
        """Check if a resource type exists in the catalog."""
        from ..models import ResourceCatalog

        return db.query(ResourceCatalog).filter(
            ResourceCatalog.resource_type == resource_type,
            ResourceCatalog.enabled == True,
        ).first() is not None

    @staticmethod
    def get_required_dependencies(
        db: Session, resource_type: str
    ) -> List["CatalogDependency"]:
        """Get required dependencies for a resource type."""
        from ..models import ResourceCatalog, CatalogDependency

        resource = db.query(ResourceCatalog).filter(
            ResourceCatalog.resource_type == resource_type
        ).first()

        if not resource:
            return []

        return db.query(CatalogDependency).filter(
            CatalogDependency.resource_type_id == resource.id,
            CatalogDependency.dependency_classification == "REQUIRED",
        ).all()

    @staticmethod
    def get_recommended_dependencies(
        db: Session, resource_type: str
    ) -> List["CatalogDependency"]:
        """Get recommended dependencies for a resource type."""
        from ..models import ResourceCatalog, CatalogDependency

        resource = db.query(ResourceCatalog).filter(
            ResourceCatalog.resource_type == resource_type
        ).first()

        if not resource:
            return []

        return db.query(CatalogDependency).filter(
            CatalogDependency.resource_type_id == resource.id,
            CatalogDependency.dependency_classification == "RECOMMENDED",
        ).all()

    @staticmethod
    def get_optional_dependencies(
        db: Session, resource_type: str
    ) -> List["CatalogDependency"]:
        """Get optional dependencies for a resource type."""
        from ..models import ResourceCatalog, CatalogDependency

        resource = db.query(ResourceCatalog).filter(
            ResourceCatalog.resource_type == resource_type
        ).first()

        if not resource:
            return []

        return db.query(CatalogDependency).filter(
            CatalogDependency.resource_type_id == resource.id,
            CatalogDependency.dependency_classification == "OPTIONAL",
        ).all()

    @staticmethod
    def get_all_dependencies(
        db: Session, resource_type: str
    ) -> dict:
        """Get all dependencies (required, recommended, optional) for a resource type."""
        from ..models import ResourceCatalog

        resource = db.query(ResourceCatalog).filter(
            ResourceCatalog.resource_type == resource_type
        ).first()

        if not resource:
            return {
                "resource_type": resource_type,
                "required": [],
                "recommended": [],
                "optional": [],
            }

        return {
            "resource_type": resource_type,
            "required": CatalogService.get_required_dependencies(db, resource_type),
            "recommended": CatalogService.get_recommended_dependencies(db, resource_type),
            "optional": CatalogService.get_optional_dependencies(db, resource_type),
        }

    @staticmethod
    def get_valid_parent_types(db: Session, child_resource_type: str) -> List[str]:
        """Get valid parent types for a resource type."""
        from ..models import ResourceCatalog, CatalogHierarchy

        child = db.query(ResourceCatalog).filter(
            ResourceCatalog.resource_type == child_resource_type
        ).first()

        if not child:
            return []

        parents = db.query(CatalogHierarchy).filter(
            CatalogHierarchy.child_resource_type_id == child.id
        ).all()

        parent_types = []
        for parent_rel in parents:
            parent_resource = db.query(ResourceCatalog).filter(
                ResourceCatalog.id == parent_rel.parent_resource_type_id
            ).first()
            if parent_resource:
                parent_types.append(parent_resource.resource_type)

        return parent_types

    @staticmethod
    def get_valid_child_types(db: Session, parent_resource_type: str) -> List[str]:
        """Get valid child types for a resource type."""
        from ..models import ResourceCatalog, CatalogHierarchy

        parent = db.query(ResourceCatalog).filter(
            ResourceCatalog.resource_type == parent_resource_type
        ).first()

        if not parent:
            return []

        children = db.query(CatalogHierarchy).filter(
            CatalogHierarchy.parent_resource_type_id == parent.id
        ).all()

        child_types = []
        for child_rel in children:
            child_resource = db.query(ResourceCatalog).filter(
                ResourceCatalog.id == child_rel.child_resource_type_id
            ).first()
            if child_resource:
                child_types.append(child_resource.resource_type)

        return child_types

    @staticmethod
    def add_required_dependency(
        db: Session,
        resource_type: str,
        depends_on_type: str,
        reason: Optional[str] = None,
    ) -> "CatalogDependency":
        """Add a required dependency between two resource types."""
        from ..models import ResourceCatalog, CatalogDependency

        resource = db.query(ResourceCatalog).filter(
            ResourceCatalog.resource_type == resource_type
        ).first()

        if not resource:
            raise ValueError(f"Resource type {resource_type} not found")

        db_dependency = CatalogDependency(
            resource_type_id=resource.id,
            depends_on_resource_type=depends_on_type,
            dependency_classification="REQUIRED",
            reason=reason,
        )
        db.add(db_dependency)
        db.commit()
        db.refresh(db_dependency)
        return db_dependency

    @staticmethod
    def add_recommended_dependency(
        db: Session,
        resource_type: str,
        depends_on_type: str,
        reason: Optional[str] = None,
    ) -> "CatalogDependency":
        """Add a recommended dependency between two resource types."""
        from ..models import ResourceCatalog, CatalogDependency

        resource = db.query(ResourceCatalog).filter(
            ResourceCatalog.resource_type == resource_type
        ).first()

        if not resource:
            raise ValueError(f"Resource type {resource_type} not found")

        db_dependency = CatalogDependency(
            resource_type_id=resource.id,
            depends_on_resource_type=depends_on_type,
            dependency_classification="RECOMMENDED",
            reason=reason,
        )
        db.add(db_dependency)
        db.commit()
        db.refresh(db_dependency)
        return db_dependency

    @staticmethod
    def add_optional_dependency(
        db: Session,
        resource_type: str,
        depends_on_type: str,
        reason: Optional[str] = None,
    ) -> "CatalogDependency":
        """Add an optional dependency between two resource types."""
        from ..models import ResourceCatalog, CatalogDependency

        resource = db.query(ResourceCatalog).filter(
            ResourceCatalog.resource_type == resource_type
        ).first()

        if not resource:
            raise ValueError(f"Resource type {resource_type} not found")

        db_dependency = CatalogDependency(
            resource_type_id=resource.id,
            depends_on_resource_type=depends_on_type,
            dependency_classification="OPTIONAL",
            reason=reason,
        )
        db.add(db_dependency)
        db.commit()
        db.refresh(db_dependency)
        return db_dependency

    @staticmethod
    def add_hierarchy(
        db: Session,
        parent_resource_type: str,
        child_resource_type: str,
        description: Optional[str] = None,
    ) -> "CatalogHierarchy":
        """Add a containment (hierarchy) relationship between two resource types."""
        from ..models import ResourceCatalog, CatalogHierarchy

        parent = db.query(ResourceCatalog).filter(
            ResourceCatalog.resource_type == parent_resource_type
        ).first()
        child = db.query(ResourceCatalog).filter(
            ResourceCatalog.resource_type == child_resource_type
        ).first()

        if not parent:
            raise ValueError(f"Parent resource type {parent_resource_type} not found")
        if not child:
            raise ValueError(f"Child resource type {child_resource_type} not found")

        db_hierarchy = CatalogHierarchy(
            parent_resource_type_id=parent.id,
            child_resource_type_id=child.id,
            description=description,
        )
        db.add(db_hierarchy)
        db.commit()
        db.refresh(db_hierarchy)
        return db_hierarchy

    @staticmethod
    def get_terraform_mapping(db: Session, resource_type: str) -> Optional[dict]:
        """Get Terraform mapping for a resource type."""
        resource = CatalogService.get_resource_type(db, resource_type)
        if resource:
            return resource.terraform_mapping
        return None

    @staticmethod
    def get_categories(db: Session) -> List[str]:
        """Get all categories of resources."""
        from ..models import ResourceCatalog

        categories = db.query(ResourceCatalog.category).filter(
            ResourceCatalog.enabled == True
        ).distinct().order_by(ResourceCatalog.category).all()

        return [cat[0] for cat in categories]


# ============================================================================
# DEPENDENCY ENGINE - Analyzes whether architecture satisfies catalog requirements
# ============================================================================


class DependencyEngine:
    """
    Analyzes whether an architecture's resources satisfy their catalog dependencies.
    
    Core Principle:
    - Canonical Architecture Model = WHAT resources exist
    - Resource Catalog = WHAT each resource type requires/recommends/allows
    - Dependency Engine = WHETHER the current architecture satisfies those requirements
    
    The Dependency Engine does NOT modify the architecture.
    It only analyzes and returns findings.
    """

    @staticmethod
    def analyze_version(db: Session, architecture_id: UUID, version_id: UUID) -> dict:
        """
        Analyze an entire architecture version for dependency satisfaction.
        
        Returns a dictionary with:
        - total_findings
        - required_findings, recommended_findings, optional_findings
        - satisfied_count, missing_count
        - findings list
        """
        from ..models import ArchitectureVersion, Resource, ResourceCatalog, CatalogDependency, Relationship

        # Load and verify the architecture version
        version = db.query(ArchitectureVersion).filter(
            ArchitectureVersion.id == version_id,
            ArchitectureVersion.architecture_id == architecture_id,
        ).first()

        if not version:
            raise ValueError("Architecture version not found or does not belong to this architecture")

        # Load all resources in this version
        resources = db.query(Resource).filter(
            Resource.architecture_version_id == version_id
        ).all()

        # Index resources by type for fast lookup
        resources_by_type = {}
        resource_by_id = {r.id: r for r in resources}
        for resource in resources:
            if resource.resource_type not in resources_by_type:
                resources_by_type[resource.resource_type] = []
            resources_by_type[resource.resource_type].append(resource)

        # Index relationships for dependency resolution
        relationships = db.query(Relationship).filter(
            Relationship.architecture_version_id == version_id
        ).all()
        relationships_map = {}  # (source_id, target_id, relationship_type) -> Relationship
        for rel in relationships:
            key = (rel.source_resource_id, rel.target_resource_id, rel.relationship_type)
            relationships_map[key] = rel

        findings = []

        # Analyze each resource
        for resource in resources:
            # Look up the catalog entry for this resource type
            catalog_entry = db.query(ResourceCatalog).filter(
                ResourceCatalog.resource_type == resource.resource_type,
                ResourceCatalog.enabled == True,
            ).first()

            # If no catalog entry, generate UNKNOWN finding
            if not catalog_entry:
                findings.append({
                    "architecture_id": architecture_id,
                    "architecture_version_id": version_id,
                    "source_resource_id": resource.id,
                    "source_resource_key": resource.resource_key,
                    "source_resource_type": resource.resource_type,
                    "dependency_resource_type": None,
                    "classification": "UNKNOWN",
                    "status": "CATALOG_RESOURCE_TYPE_UNKNOWN",
                    "reason": f"Resource type {resource.resource_type} not found in Resource Catalog",
                    "matched_resource_id": None,
                    "matched_resource_key": None,
                    "catalog_dependency_id": None,
                })
                continue

            # Load all dependencies for this resource type
            catalog_deps = db.query(CatalogDependency).filter(
                CatalogDependency.resource_type_id == catalog_entry.id
            ).all()

            # Analyze each dependency
            for dep in catalog_deps:
                finding = DependencyEngine._resolve_dependency(
                    db,
                    architecture_id,
                    version_id,
                    resource,
                    catalog_entry,
                    dep,
                    resources_by_type,
                    relationships_map,
                )
                if finding:
                    findings.append(finding)

        # Aggregate findings
        total = len(findings)
        required = sum(1 for f in findings if f["classification"] == "REQUIRED")
        recommended = sum(1 for f in findings if f["classification"] == "RECOMMENDED")
        optional = sum(1 for f in findings if f["classification"] == "OPTIONAL")
        satisfied = sum(1 for f in findings if f["status"] == "SATISFIED")
        missing = sum(1 for f in findings if f["status"] == "MISSING")

        return {
            "architecture_id": architecture_id,
            "architecture_version_id": version_id,
            "total_findings": total,
            "required_findings": required,
            "recommended_findings": recommended,
            "optional_findings": optional,
            "satisfied_count": satisfied,
            "missing_count": missing,
            "findings": findings,
        }

    @staticmethod
    def _resolve_dependency(
        db: Session,
        architecture_id: UUID,
        version_id: UUID,
        source_resource: "Resource",
        catalog_entry: "ResourceCatalog",
        catalog_dependency: "CatalogDependency",
        resources_by_type: dict,
        relationships_map: dict,
    ) -> Optional[dict]:
        """
        Resolve a single dependency to determine if it's satisfied.
        
        MATCHING LOGIC (relationship-aware):
        
        1. Get target resource type from catalog dependency
        2. Query Relationship table: does source_resource have a relationship
           to ANY resource of the target type in the same version?
        3. If yes: SATISFIED (matched_resource = the related resource)
        4. If no: MISSING
        
        Returns a finding dict or None if dependency cannot be analyzed.
        """
        from ..models import Relationship

        # Get the target resource type this dependency requires
        target_resource_type = catalog_dependency.depends_on_resource_type

        # Get target resources available in this version
        target_resources = resources_by_type.get(target_resource_type, [])
        
        if not target_resources:
            # No resources of required type exist in this version
            return {
                "architecture_id": architecture_id,
                "architecture_version_id": version_id,
                "source_resource_id": source_resource.id,
                "source_resource_key": source_resource.resource_key,
                "source_resource_type": source_resource.resource_type,
                "dependency_resource_type": target_resource_type,
                "classification": catalog_dependency.dependency_classification,
                "status": "MISSING",
                "reason": catalog_dependency.reason,
                "matched_resource_id": None,
                "matched_resource_key": None,
                "catalog_dependency_id": catalog_dependency.id,
            }

        # Target resources exist. Now check if source_resource is related to any of them.
        # Query for any relationship from source to a target of the required type
        related_resource = db.query(Relationship).filter(
            Relationship.architecture_version_id == source_resource.architecture_version_id,
            Relationship.source_resource_id == source_resource.id,
            Relationship.target_resource_id.in_([r.id for r in target_resources]),
        ).first()

        if related_resource:
            # Found a relationship to a resource of the required type
            matched = db.query("Resource").filter(
                "Resource.id" == related_resource.target_resource_id
            ).first()
            # Re-fetch to get actual ORM object
            from ..models import Resource
            matched = db.query(Resource).filter(
                Resource.id == related_resource.target_resource_id
            ).first()
            
            return {
                "architecture_id": architecture_id,
                "architecture_version_id": version_id,
                "source_resource_id": source_resource.id,
                "source_resource_key": source_resource.resource_key,
                "source_resource_type": source_resource.resource_type,
                "dependency_resource_type": target_resource_type,
                "classification": catalog_dependency.dependency_classification,
                "status": "SATISFIED",
                "reason": catalog_dependency.reason,
                "matched_resource_id": matched.id,
                "matched_resource_key": matched.resource_key,
                "catalog_dependency_id": catalog_dependency.id,
            }
        
        # No relationship found to any target resource
        return {
            "architecture_id": architecture_id,
            "architecture_version_id": version_id,
            "source_resource_id": source_resource.id,
            "source_resource_key": source_resource.resource_key,
            "source_resource_type": source_resource.resource_type,
            "dependency_resource_type": target_resource_type,
            "classification": catalog_dependency.dependency_classification,
            "status": "MISSING",
            "reason": catalog_dependency.reason,
            "matched_resource_id": None,
            "matched_resource_key": None,
            "catalog_dependency_id": catalog_dependency.id,
        }


# ==================== VALIDATION ENGINE ====================


class ValidationEngine:
    """
    Deterministic Architecture Validation Engine.
    
    Validates architecture structural and technical correctness without:
    - Compliance checks (M5)
    - Azure live validation
    - Terraform validation
    - AI inference or recommendations
    """
    
    @staticmethod
    def validate_version(
        db: Session,
        architecture_id: UUID,
        version_id: UUID,
    ) -> dict:
        """
        Validate an architecture version.
        
        Returns:
        {
            "architecture_id": UUID,
            "architecture_version_id": UUID,
            "status": "VALID|INVALID",
            "error_count": int,
            "warning_count": int,
            "info_count": int,
            "total_findings": int,
            "findings": [ValidationFinding, ...]
        }
        """
        findings = []
        
        # Verify architecture and version exist
        version = db.query(ArchitectureVersion).filter(
            ArchitectureVersion.id == version_id,
            ArchitectureVersion.architecture_id == architecture_id,
        ).first()
        
        if not version:
            raise ValueError(f"Architecture version {version_id} not found")
        
        # Load all resources for this version
        resources = db.query(Resource).filter(
            Resource.architecture_version_id == version_id
        ).all()
        
        # Validate resources
        findings.extend(ValidationEngine._validate_resources(db, architecture_id, version_id, resources))
        
        # Validate hierarchy
        findings.extend(ValidationEngine._validate_hierarchy(db, architecture_id, version_id, resources))
        
        # Validate relationships
        findings.extend(ValidationEngine._validate_relationships(db, architecture_id, version_id))
        
        # Validate dependencies (consume M3 output)
        findings.extend(ValidationEngine._validate_dependencies(db, architecture_id, version_id))
        
        # Aggregate results
        error_count = sum(1 for f in findings if f["severity"] == "ERROR")
        warning_count = sum(1 for f in findings if f["severity"] == "WARNING")
        info_count = sum(1 for f in findings if f["severity"] == "INFO")
        
        # Determine overall status
        status = "INVALID" if error_count > 0 else "VALID"
        
        return {
            "architecture_id": architecture_id,
            "architecture_version_id": version_id,
            "status": status,
            "error_count": error_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "total_findings": len(findings),
            "findings": findings,
        }
    
    @staticmethod
    def _validate_resources(
        db: Session,
        architecture_id: UUID,
        version_id: UUID,
        resources: List[Resource],
    ) -> List[dict]:
        """Validate resource-level constraints."""
        findings = []
        seen_keys = set()
        
        for resource in resources:
            # Check for empty resource_type
            if not resource.resource_type or not resource.resource_type.strip():
                findings.append({
                    "architecture_id": architecture_id,
                    "architecture_version_id": version_id,
                    "severity": "ERROR",
                    "category": "RESOURCE",
                    "code": "INVALID_RESOURCE_TYPE",
                    "message": f"Resource {resource.resource_key} has empty resource_type",
                    "resource_id": resource.id,
                    "related_resource_id": None,
                    "details": {"resource_key": resource.resource_key},
                })
                continue
            
            # Check if resource_type is in catalog
            catalog_entry = db.query(ResourceCatalog).filter(
                ResourceCatalog.resource_type == resource.resource_type
            ).first()
            
            if not catalog_entry:
                findings.append({
                    "architecture_id": architecture_id,
                    "architecture_version_id": version_id,
                    "severity": "ERROR",
                    "category": "CATALOG",
                    "code": "RESOURCE_TYPE_NOT_IN_CATALOG",
                    "message": f"Resource type {resource.resource_type} is not in Resource Catalog",
                    "resource_id": resource.id,
                    "related_resource_id": None,
                    "details": {"resource_type": resource.resource_type, "resource_key": resource.resource_key},
                })
            
            # Check for missing required identity (resource_key)
            if not resource.resource_key or not resource.resource_key.strip():
                findings.append({
                    "architecture_id": architecture_id,
                    "architecture_version_id": version_id,
                    "severity": "ERROR",
                    "category": "RESOURCE",
                    "code": "RESOURCE_MISSING_REQUIRED_IDENTITY",
                    "message": f"Resource is missing required resource_key",
                    "resource_id": resource.id,
                    "related_resource_id": None,
                    "details": None,
                })
            
            # Check for missing name
            if not resource.name or not resource.name.strip():
                findings.append({
                    "architecture_id": architecture_id,
                    "architecture_version_id": version_id,
                    "severity": "ERROR",
                    "category": "RESOURCE",
                    "code": "RESOURCE_MISSING_NAME",
                    "message": f"Resource {resource.resource_key} is missing name",
                    "resource_id": resource.id,
                    "related_resource_id": None,
                    "details": {"resource_key": resource.resource_key},
                })
            
            # Check for duplicate resource keys
            if resource.resource_key:
                if resource.resource_key in seen_keys:
                    findings.append({
                        "architecture_id": architecture_id,
                        "architecture_version_id": version_id,
                        "severity": "ERROR",
                        "category": "RESOURCE",
                        "code": "DUPLICATE_RESOURCE_KEY",
                        "message": f"Duplicate resource_key: {resource.resource_key}",
                        "resource_id": resource.id,
                        "related_resource_id": None,
                        "details": {"resource_key": resource.resource_key},
                    })
                else:
                    seen_keys.add(resource.resource_key)
        
        return findings
    
    @staticmethod
    def _validate_hierarchy(
        db: Session,
        architecture_id: UUID,
        version_id: UUID,
        resources: List[Resource],
    ) -> List[dict]:
        """Validate hierarchy constraints using CatalogHierarchy."""
        findings = []
        resources_by_id = {r.id: r for r in resources}
        
        # Collect all unique resource types used in this version
        resource_types = set()
        for resource in resources:
            resource_types.add(resource.resource_type)
        
        # Bulk load all required catalog entries (single query)
        catalogs = db.query(ResourceCatalog).filter(
            ResourceCatalog.resource_type.in_(resource_types)
        ).all()
        
        # Build in-memory catalog lookup by type
        catalog_by_type = {cat.resource_type: cat for cat in catalogs}
        
        # Bulk load all hierarchy rules (single query)
        hierarchy_rules = db.query(CatalogHierarchy).all()
        
        # Build in-memory hierarchy lookup (parent_id, child_id) -> rule
        hierarchy_by_pair = {
            (rule.parent_resource_type_id, rule.child_resource_type_id): rule
            for rule in hierarchy_rules
        }
        
        # Validate each resource using in-memory structures
        for resource in resources:
            if resource.parent_resource_id is None:
                continue  # No parent, skip
            
            # Check if parent resource exists
            parent = resources_by_id.get(resource.parent_resource_id)
            if not parent:
                findings.append({
                    "architecture_id": architecture_id,
                    "architecture_version_id": version_id,
                    "severity": "ERROR",
                    "category": "HIERARCHY",
                    "code": "INVALID_HIERARCHY_PARENT",
                    "message": f"Parent resource {resource.parent_resource_id} does not exist",
                    "resource_id": resource.id,
                    "related_resource_id": resource.parent_resource_id,
                    "details": {"child_key": resource.resource_key},
                })
                continue
            
            # Check if parent-child relationship is valid in catalog (in-memory lookup)
            parent_catalog = catalog_by_type.get(parent.resource_type)
            child_catalog = catalog_by_type.get(resource.resource_type)
            
            if parent_catalog and child_catalog:
                # Check if this parent-child pair is valid using in-memory structure
                valid_hierarchy = hierarchy_by_pair.get(
                    (parent_catalog.id, child_catalog.id)
                )
                
                if not valid_hierarchy:
                    findings.append({
                        "architecture_id": architecture_id,
                        "architecture_version_id": version_id,
                        "severity": "ERROR",
                        "category": "HIERARCHY",
                        "code": "INVALID_PARENT_TYPE",
                        "message": f"Cannot contain {resource.resource_type} under {parent.resource_type}",
                        "resource_id": resource.id,
                        "related_resource_id": resource.parent_resource_id,
                        "details": {
                            "child_type": resource.resource_type,
                            "parent_type": parent.resource_type,
                        },
                    })
        
        return findings


# ==================== COMPLIANCE ENGINE SERVICES ====================


class ComplianceFrameworkService:
    """Service for managing compliance frameworks and controls."""

    # Framework definitions - Milestone 5 Phase 1
    FRAMEWORKS = {
        "HIPAA": {
            "display_name": "HIPAA (Health Insurance Portability and Accountability Act)",
            "version": "technical-profile-v1",
            "description": "Technical controls for healthcare data protection",
        },
        "GDPR": {
            "display_name": "GDPR (General Data Protection Regulation)",
            "version": "technical-profile-v1",
            "description": "Technical controls for personal data protection",
        },
        "SOC2": {
            "display_name": "SOC 2 (Service Organization Control 2)",
            "version": "technical-profile-v1",
            "description": "Technical controls for service organization security",
        },
        "ISO27001": {
            "display_name": "ISO/IEC 27001",
            "version": "technical-profile-v1",
            "description": "Technical controls for information security management",
        },
        "NIST": {
            "display_name": "NIST Cybersecurity Framework",
            "version": "technical-profile-v1",
            "description": "Technical controls for cybersecurity practices",
        },
        "HITRUST": {
            "display_name": "HITRUST CSF (Common Security Framework)",
            "version": "technical-profile-v1",
            "description": "Technical controls for healthcare information security",
        },
    }

    # Control definitions covering representative technical areas
    CONTROLS = {
        # Encryption Controls
        "HIPAA-ENC-001": {
            "framework": "HIPAA",
            "title": "Storage encryption",
            "description": "Storage services should use encryption",
            "category": "ENCRYPTION",
            "evaluation_type": "PROPERTY_CHECK",
            "rule_version": "1.0",
            "policy_level": "REQUIRED",
        },
        "GDPR-ENC-001": {
            "framework": "GDPR",
            "title": "Data encryption at rest",
            "description": "Personal data storage should use encryption",
            "category": "ENCRYPTION",
            "evaluation_type": "PROPERTY_CHECK",
            "rule_version": "1.0",
            "policy_level": "REQUIRED",
        },
        "SOC2-ENC-001": {
            "framework": "SOC2",
            "title": "Encryption controls",
            "description": "Data should be protected with encryption",
            "category": "ENCRYPTION",
            "evaluation_type": "PROPERTY_CHECK",
            "rule_version": "1.0",
            "policy_level": "REQUIRED",
        },

        # Network Isolation Controls
        "HIPAA-NET-001": {
            "framework": "HIPAA",
            "title": "Network isolation",
            "description": "Compute resources should be protected with network isolation",
            "category": "NETWORK_SECURITY",
            "evaluation_type": "RESOURCE_TYPE_CHECK",
            "rule_version": "1.0",
            "policy_level": "REQUIRED",
        },
        "GDPR-NET-001": {
            "framework": "GDPR",
            "title": "Network access controls",
            "description": "Systems should implement network segmentation",
            "category": "NETWORK_SECURITY",
            "evaluation_type": "RESOURCE_TYPE_CHECK",
            "rule_version": "1.0",
            "policy_level": "REQUIRED",
        },

        # Identity and Access Controls
        "ISO27001-IAM-001": {
            "framework": "ISO27001",
            "title": "Identity and access management",
            "description": "Systems should implement IAM mechanisms",
            "category": "IDENTITY",
            "evaluation_type": "RESOURCE_TYPE_CHECK",
            "rule_version": "1.0",
            "policy_level": "REQUIRED",
        },
        "NIST-IAM-001": {
            "framework": "NIST",
            "title": "Identity verification",
            "description": "Identity services should be configured",
            "category": "IDENTITY",
            "evaluation_type": "RESOURCE_TYPE_CHECK",
            "rule_version": "1.0",
            "policy_level": "REQUIRED",
        },

        # Logging and Monitoring Controls
        "HIPAA-LOG-001": {
            "framework": "HIPAA",
            "title": "Activity logging",
            "description": "Systems should implement audit logging",
            "category": "LOGGING",
            "evaluation_type": "RESOURCE_TYPE_CHECK",
            "rule_version": "1.0",
            "policy_level": "REQUIRED",
        },
        "SOC2-MON-001": {
            "framework": "SOC2",
            "title": "Monitoring and alerting",
            "description": "Systems should have monitoring configured",
            "category": "MONITORING",
            "evaluation_type": "RESOURCE_TYPE_CHECK",
            "rule_version": "1.0",
            "policy_level": "REQUIRED",
        },

        # Backup and Recovery Controls
        "HITRUST-BAK-001": {
            "framework": "HITRUST",
            "title": "Data backup capability",
            "description": "Critical data should have backup capability",
            "category": "BACKUP",
            "evaluation_type": "RESOURCE_TYPE_CHECK",
            "rule_version": "1.0",
            "policy_level": "REQUIRED",
        },
        "ISO27001-BAK-001": {
            "framework": "ISO27001",
            "title": "Backup and recovery",
            "description": "Systems should support backup operations",
            "category": "BACKUP",
            "evaluation_type": "RESOURCE_TYPE_CHECK",
            "rule_version": "1.0",
            "policy_level": "RECOMMENDATION",
        },

        # Secrets Management Controls
        "HIPAA-SEC-001": {
            "framework": "HIPAA",
            "title": "Secrets management",
            "description": "Sensitive secrets should use secure management",
            "category": "SECRETS",
            "evaluation_type": "RESOURCE_TYPE_CHECK",
            "rule_version": "1.0",
            "policy_level": "REQUIRED",
        },
        "GDPR-SEC-001": {
            "framework": "GDPR",
            "title": "Credential protection",
            "description": "Credentials should be managed securely",
            "category": "SECRETS",
            "evaluation_type": "RESOURCE_TYPE_CHECK",
            "rule_version": "1.0",
            "policy_level": "REQUIRED",
        },
    }

    @staticmethod
    def get_frameworks(db: Session) -> List[dict]:
        """Get all available compliance frameworks."""
        from ..models import ComplianceFramework
        
        frameworks = db.query(ComplianceFramework).all()
        return [
            {
                "id": f.id,
                "framework_name": f.framework_name,
                "framework_version": f.framework_version,
                "display_name": f.display_name,
                "description": f.description,
                "enabled": f.enabled,
            }
            for f in frameworks
        ]

    @staticmethod
    def get_framework_by_name(db: Session, framework_name: str) -> Optional[dict]:
        """Get a framework by name."""
        from ..models import ComplianceFramework
        
        framework = db.query(ComplianceFramework).filter(
            ComplianceFramework.framework_name == framework_name
        ).first()
        
        if not framework:
            return None
        
        return {
            "id": framework.id,
            "framework_name": framework.framework_name,
            "framework_version": framework.framework_version,
            "display_name": framework.display_name,
            "description": framework.description,
            "enabled": framework.enabled,
        }

    @staticmethod
    def bootstrap_frameworks(db: Session) -> None:
        """Bootstrap compliance frameworks and controls into database."""
        from ..models import ComplianceFramework, ComplianceControl, ComplianceControlPolicy
        
        for framework_name, framework_info in ComplianceFrameworkService.FRAMEWORKS.items():
            # Check if framework already exists
            existing = db.query(ComplianceFramework).filter(
                ComplianceFramework.framework_name == framework_name
            ).first()
            
            if existing:
                continue
            
            # Create framework
            framework = ComplianceFramework(
                framework_name=framework_name,
                framework_version=framework_info["version"],
                display_name=framework_info["display_name"],
                description=framework_info["description"],
                enabled=True,
            )
            db.add(framework)
            db.flush()
            
            # Add controls for this framework
            for control_code, control_info in ComplianceFrameworkService.CONTROLS.items():
                if control_info["framework"] == framework_name:
                    control = ComplianceControl(
                        framework_id=framework.id,
                        control_code=control_code,
                        title=control_info["title"],
                        description=control_info["description"],
                        category=control_info["category"],
                        evaluation_type=control_info["evaluation_type"],
                        rule_version=control_info["rule_version"],
                        enabled=True,
                    )
                    db.add(control)
                    db.flush()
                    
                    # Add policy level for control
                    policy = ComplianceControlPolicy(
                        control_id=control.id,
                        policy_level=control_info["policy_level"],
                        default_enabled=True,
                    )
                    db.add(policy)
        
        db.commit()


class ComplianceEngine:
    """Deterministic compliance evaluation engine."""

    # Evaluation outcomes
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    RECOMMENDATION = "RECOMMENDATION"
    NOT_EVALUATED = "NOT_EVALUATED"

    @staticmethod
    def evaluate_compliance(
        db: Session,
        architecture_id: UUID,
        version_id: UUID,
        framework_names: List[str],
    ) -> dict:
        """
        Evaluate architecture against selected compliance frameworks.
        
        Returns:
        {
            "architecture_id": UUID,
            "architecture_version_id": UUID,
            "requested_frameworks": List[str],
            "evaluations": List[framework evaluations],
            "timestamp": datetime,
        }
        """
        from datetime import datetime, timezone
        from ..models import (
            ComplianceFramework,
            ComplianceControl,
            ComplianceControlPolicy,
        )

        # Verify architecture and version
        arch = ArchitectureService.get(db, architecture_id)
        if not arch:
            return {"error": "Architecture not found", "status": 404}

        version = db.query(ArchitectureVersion).filter(
            ArchitectureVersion.id == version_id,
            ArchitectureVersion.architecture_id == architecture_id,
        ).first()

        if not version:
            return {"error": "Version not found", "status": 404}

        # Run validation engine to check for structural errors
        validation_result = ValidationEngine.validate_version(db, architecture_id, version_id)
        
        # Check if validation has ERROR findings
        has_errors = any(f["severity"] == "ERROR" for f in validation_result.get("findings", []))
        
        # Get all resources and catalog info once
        resources = db.query(Resource).filter(
            Resource.architecture_version_id == version_id
        ).all()
        
        resource_types = {r.resource_type for r in resources}
        catalogs = db.query(ResourceCatalog).filter(
            ResourceCatalog.resource_type.in_(resource_types)
        ).all() if resource_types else []
        catalog_by_type = {c.resource_type: c for c in catalogs}

        # Get dependency results
        dependency_result = DependencyEngine.analyze_version(db, architecture_id, version_id)

        # Evaluate each framework
        evaluations = []
        for framework_name in framework_names:
            if has_errors:
                # Validation failed - return VALIDATION_BLOCKED
                evaluation = {
                    "architecture_id": architecture_id,
                    "architecture_version_id": version_id,
                    "framework_id": None,
                    "framework_name": framework_name,
                    "framework_version": None,
                    "overall_status": "VALIDATION_BLOCKED",
                    "total_controls": 0,
                    "passed_controls": 0,
                    "failed_controls": 0,
                    "warning_controls": 0,
                    "recommendation_controls": 0,
                    "not_evaluated_controls": 0,
                    "findings": [{
                        "framework_id": None,
                        "framework_name": framework_name,
                        "framework_version": None,
                        "control_id": None,
                        "control_code": "VALIDATION_BLOCKED",
                        "title": "Architecture contains structural validation errors",
                        "category": "VALIDATION",
                        "outcome": NOT_EVALUATED,
                        "policy_level": "REQUIRED",
                        "message": "Cannot evaluate compliance: architecture validation contains errors",
                        "resource_id": None,
                        "related_resource_id": None,
                        "evidence": {"validation_errors": len([f for f in validation_result.get("findings", []) if f["severity"] == "ERROR"])},
                        "rule_version": "1.0",
                    }],
                }
                evaluations.append(evaluation)
                continue

            # Get framework from database
            framework = db.query(ComplianceFramework).filter(
                ComplianceFramework.framework_name == framework_name
            ).first()

            if not framework:
                # Unknown framework
                evaluations.append({
                    "error": f"Framework {framework_name} not found",
                    "status": 400,
                })
                continue

            # Get controls for this framework
            controls = db.query(ComplianceControl).filter(
                ComplianceControl.framework_id == framework.id,
                ComplianceControl.enabled == True,
            ).all()

            # Evaluate each control
            findings = []
            outcome_counts = {
                "PASS": 0,
                "FAIL": 0,
                "WARNING": 0,
                "RECOMMENDATION": 0,
                "NOT_EVALUATED": 0,
            }

            for control in controls:
                policy = db.query(ComplianceControlPolicy).filter(
                    ComplianceControlPolicy.control_id == control.id
                ).first()

                # Evaluate the control
                finding = ComplianceEngine._evaluate_control(
                    control,
                    policy,
                    resources,
                    catalog_by_type,
                    dependency_result,
                    validation_result,
                )

                outcome = finding["outcome"]
                outcome_counts[outcome] += 1
                findings.append(finding)

            # Determine overall status
            overall_status = ComplianceEngine._determine_overall_status(
                findings, outcome_counts
            )

            evaluation = {
                "architecture_id": architecture_id,
                "architecture_version_id": version_id,
                "framework_id": framework.id,
                "framework_name": framework.framework_name,
                "framework_version": framework.framework_version,
                "overall_status": overall_status,
                "total_controls": len(controls),
                "passed_controls": outcome_counts["PASS"],
                "failed_controls": outcome_counts["FAIL"],
                "warning_controls": outcome_counts["WARNING"],
                "recommendation_controls": outcome_counts["RECOMMENDATION"],
                "not_evaluated_controls": outcome_counts["NOT_EVALUATED"],
                "findings": findings,
            }
            evaluations.append(evaluation)

        return {
            "architecture_id": architecture_id,
            "architecture_version_id": version_id,
            "requested_frameworks": framework_names,
            "evaluations": evaluations,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _evaluate_control(
        control,
        policy,
        resources,
        catalog_by_type,
        dependency_result,
        validation_result,
    ) -> dict:
        """Evaluate a single compliance control against architecture."""
        
        # Map control codes to evaluation functions
        evaluation_map = {
            # Encryption controls
            "HIPAA-ENC-001": ComplianceEngine._eval_storage_encryption,
            "GDPR-ENC-001": ComplianceEngine._eval_storage_encryption,
            "SOC2-ENC-001": ComplianceEngine._eval_storage_encryption,
            
            # Network isolation controls
            "HIPAA-NET-001": ComplianceEngine._eval_network_isolation,
            "GDPR-NET-001": ComplianceEngine._eval_network_isolation,
            
            # Identity controls
            "ISO27001-IAM-001": ComplianceEngine._eval_identity_management,
            "NIST-IAM-001": ComplianceEngine._eval_identity_management,
            
            # Logging controls
            "HIPAA-LOG-001": ComplianceEngine._eval_logging,
            "SOC2-MON-001": ComplianceEngine._eval_monitoring,
            
            # Backup controls
            "HITRUST-BAK-001": ComplianceEngine._eval_backup_capability,
            "ISO27001-BAK-001": ComplianceEngine._eval_backup_capability,
            
            # Secrets controls
            "HIPAA-SEC-001": ComplianceEngine._eval_secrets_management,
            "GDPR-SEC-001": ComplianceEngine._eval_secrets_management,
        }

        # Get evaluation function
        eval_func = evaluation_map.get(control.control_code)
        if not eval_func:
            # Unknown control - cannot evaluate
            return {
                "framework_id": control.framework_id,
                "framework_name": control.framework.framework_name,
                "framework_version": control.framework.framework_version,
                "control_id": control.id,
                "control_code": control.control_code,
                "title": control.title,
                "category": control.category,
                "outcome": "NOT_EVALUATED",
                "policy_level": policy.policy_level if policy else "RECOMMENDATION",
                "message": f"Control evaluation not implemented: {control.control_code}",
                "resource_id": None,
                "related_resource_id": None,
                "evidence": {"reason": "not_implemented"},
                "rule_version": control.rule_version,
            }

        # Execute evaluation
        return eval_func(control, policy, resources, catalog_by_type)

    # Evaluation functions for specific control types
    @staticmethod
    def _eval_storage_encryption(control, policy, resources, catalog_by_type) -> dict:
        """Evaluate storage encryption control."""
        policy_level = policy.policy_level if policy else "RECOMMENDATION"
        
        # Find storage resources (StorageAccount type)
        storage_resources = [r for r in resources if r.resource_type == "StorageAccount"]
        
        if not storage_resources:
            return {
                "framework_id": control.framework_id,
                "framework_name": control.framework.framework_name,
                "framework_version": control.framework.framework_version,
                "control_id": control.id,
                "control_code": control.control_code,
                "title": control.title,
                "category": control.category,
                "outcome": "NOT_EVALUATED",
                "policy_level": policy_level,
                "message": "No storage services found in architecture",
                "resource_id": None,
                "related_resource_id": None,
                "evidence": {"storage_count": 0},
                "rule_version": control.rule_version,
            }

        # Check if any storage has encryption disabled
        failing_resources = []
        passing_resources = []
        
        for resource in storage_resources:
            encryption_enabled = resource.properties.get("encryption_enabled", None) if resource.properties else None
            
            if encryption_enabled is False:
                failing_resources.append(resource.id)
            elif encryption_enabled is True:
                passing_resources.append(resource.id)
            # None = property not specified = NOT_EVALUATED at resource level

        # Determine outcome
        if failing_resources and not passing_resources:
            outcome = "FAIL"
            message = f"Storage resource(s) have encryption disabled"
        elif failing_resources and passing_resources:
            outcome = "WARNING"
            message = f"Some storage resources have encryption disabled"
        elif passing_resources:
            outcome = "PASS"
            message = "All configured storage resources have encryption enabled"
        else:
            outcome = "NOT_EVALUATED"
            message = "Storage encryption configuration not specified"

        return {
            "framework_id": control.framework_id,
            "framework_name": control.framework.framework_name,
            "framework_version": control.framework.framework_version,
            "control_id": control.id,
            "control_code": control.control_code,
            "title": control.title,
            "category": control.category,
            "outcome": outcome,
            "policy_level": policy_level,
            "message": message,
            "resource_id": failing_resources[0] if failing_resources else (passing_resources[0] if passing_resources else None),
            "related_resource_id": None,
            "evidence": {
                "storage_count": len(storage_resources),
                "encrypted": len(passing_resources),
                "not_encrypted": len(failing_resources),
                "property_not_specified": len([r for r in storage_resources if (r.properties.get("encryption_enabled", None) if r.properties else None) is None]),
            },
            "rule_version": control.rule_version,
        }

    @staticmethod
    def _eval_network_isolation(control, policy, resources, catalog_by_type) -> dict:
        """Evaluate network isolation control."""
        policy_level = policy.policy_level if policy else "RECOMMENDATION"
        
        # Look for compute resources that should have network protection
        compute_resources = [r for r in resources if r.resource_type in ["VirtualMachine", "AppService", "AKS"]]
        
        if not compute_resources:
            return {
                "framework_id": control.framework_id,
                "framework_name": control.framework.framework_name,
                "framework_version": control.framework.framework_version,
                "control_id": control.id,
                "control_code": control.control_code,
                "title": control.title,
                "category": control.category,
                "outcome": "NOT_EVALUATED",
                "policy_level": policy_level,
                "message": "No compute resources found in architecture",
                "resource_id": None,
                "related_resource_id": None,
                "evidence": {"compute_count": 0},
                "rule_version": control.rule_version,
            }

        # Check for NSG or network security groups
        nsg_resources = [r for r in resources if r.resource_type == "NetworkSecurityGroup"]
        
        if nsg_resources:
            outcome = "PASS"
            message = "Network security groups are configured"
        else:
            outcome = "WARNING"
            message = "No network security groups found - network isolation may be incomplete"

        return {
            "framework_id": control.framework_id,
            "framework_name": control.framework.framework_name,
            "framework_version": control.framework.framework_version,
            "control_id": control.id,
            "control_code": control.control_code,
            "title": control.title,
            "category": control.category,
            "outcome": outcome,
            "policy_level": policy_level,
            "message": message,
            "resource_id": compute_resources[0].id if compute_resources else None,
            "related_resource_id": nsg_resources[0].id if nsg_resources else None,
            "evidence": {
                "compute_count": len(compute_resources),
                "nsg_count": len(nsg_resources),
            },
            "rule_version": control.rule_version,
        }

    @staticmethod
    def _eval_identity_management(control, policy, resources, catalog_by_type) -> dict:
        """Evaluate identity management control."""
        policy_level = policy.policy_level if policy else "RECOMMENDATION"
        
        # Look for identity services
        identity_resources = [r for r in resources if r.resource_type in ["EntraID", "ManagedIdentity", "KeyVault"]]
        
        if identity_resources:
            outcome = "PASS"
            message = "Identity management services are configured"
        else:
            outcome = "WARNING"
            message = "No dedicated identity services found - verify identity management approach"

        return {
            "framework_id": control.framework_id,
            "framework_name": control.framework.framework_name,
            "framework_version": control.framework.framework_version,
            "control_id": control.id,
            "control_code": control.control_code,
            "title": control.title,
            "category": control.category,
            "outcome": outcome,
            "policy_level": policy_level,
            "message": message,
            "resource_id": identity_resources[0].id if identity_resources else None,
            "related_resource_id": None,
            "evidence": {
                "identity_service_count": len(identity_resources),
                "services": [r.resource_type for r in identity_resources],
            },
            "rule_version": control.rule_version,
        }

    @staticmethod
    def _eval_logging(control, policy, resources, catalog_by_type) -> dict:
        """Evaluate logging control."""
        policy_level = policy.policy_level if policy else "RECOMMENDATION"
        
        # Look for logging services
        logging_resources = [r for r in resources if r.resource_type in ["LogAnalyticsWorkspace", "ApplicationInsights", "AuditLog"]]
        
        if logging_resources:
            outcome = "PASS"
            message = "Audit logging services are configured"
        else:
            outcome = "WARNING"
            message = "No audit logging services found - audit trail may be incomplete"

        return {
            "framework_id": control.framework_id,
            "framework_name": control.framework.framework_name,
            "framework_version": control.framework.framework_version,
            "control_id": control.id,
            "control_code": control.control_code,
            "title": control.title,
            "category": control.category,
            "outcome": outcome,
            "policy_level": policy_level,
            "message": message,
            "resource_id": logging_resources[0].id if logging_resources else None,
            "related_resource_id": None,
            "evidence": {
                "logging_service_count": len(logging_resources),
                "services": [r.resource_type for r in logging_resources],
            },
            "rule_version": control.rule_version,
        }

    @staticmethod
    def _eval_monitoring(control, policy, resources, catalog_by_type) -> dict:
        """Evaluate monitoring control."""
        policy_level = policy.policy_level if policy else "RECOMMENDATION"
        
        # Look for monitoring services
        monitoring_resources = [r for r in resources if r.resource_type in ["Monitor", "ApplicationInsights", "AlertRule"]]
        
        if monitoring_resources:
            outcome = "PASS"
            message = "Monitoring and alerting services are configured"
        else:
            outcome = "RECOMMENDATION"
            message = "No monitoring services found - monitoring is recommended for production"

        return {
            "framework_id": control.framework_id,
            "framework_name": control.framework.framework_name,
            "framework_version": control.framework.framework_version,
            "control_id": control.id,
            "control_code": control.control_code,
            "title": control.title,
            "category": control.category,
            "outcome": outcome,
            "policy_level": policy_level,
            "message": message,
            "resource_id": monitoring_resources[0].id if monitoring_resources else None,
            "related_resource_id": None,
            "evidence": {
                "monitoring_service_count": len(monitoring_resources),
                "services": [r.resource_type for r in monitoring_resources],
            },
            "rule_version": control.rule_version,
        }

    @staticmethod
    def _eval_backup_capability(control, policy, resources, catalog_by_type) -> dict:
        """Evaluate backup capability control."""
        policy_level = policy.policy_level if policy else "RECOMMENDATION"
        
        # Look for stateful data resources
        data_resources = [r for r in resources if r.resource_type in ["StorageAccount", "Database", "SQLServer", "CosmosDB"]]
        
        if not data_resources:
            return {
                "framework_id": control.framework_id,
                "framework_name": control.framework.framework_name,
                "framework_version": control.framework.framework_version,
                "control_id": control.id,
                "control_code": control.control_code,
                "title": control.title,
                "category": control.category,
                "outcome": "NOT_EVALUATED",
                "policy_level": policy_level,
                "message": "No stateful data services found",
                "resource_id": None,
                "related_resource_id": None,
                "evidence": {"data_resource_count": 0},
                "rule_version": control.rule_version,
            }

        # Check for backup resources
        backup_resources = [r for r in resources if r.resource_type in ["BackupVault", "RecoveryServicesVault"]]
        
        if backup_resources:
            outcome = "PASS"
            message = "Backup capability is configured"
        else:
            outcome = "WARNING"
            message = "No backup services found - data recovery capability may be limited"

        return {
            "framework_id": control.framework_id,
            "framework_name": control.framework.framework_name,
            "framework_version": control.framework.framework_version,
            "control_id": control.id,
            "control_code": control.control_code,
            "title": control.title,
            "category": control.category,
            "outcome": outcome,
            "policy_level": policy_level,
            "message": message,
            "resource_id": data_resources[0].id if data_resources else None,
            "related_resource_id": backup_resources[0].id if backup_resources else None,
            "evidence": {
                "data_resource_count": len(data_resources),
                "backup_service_count": len(backup_resources),
            },
            "rule_version": control.rule_version,
        }

    @staticmethod
    def _eval_secrets_management(control, policy, resources, catalog_by_type) -> dict:
        """Evaluate secrets management control."""
        policy_level = policy.policy_level if policy else "RECOMMENDATION"
        
        # Look for secrets management resources
        secrets_resources = [r for r in resources if r.resource_type in ["KeyVault", "SecretStore"]]
        
        if secrets_resources:
            outcome = "PASS"
            message = "Secrets management service is configured"
        else:
            outcome = "WARNING"
            message = "No secrets management services found - credentials may not be properly protected"

        return {
            "framework_id": control.framework_id,
            "framework_name": control.framework.framework_name,
            "framework_version": control.framework.framework_version,
            "control_id": control.id,
            "control_code": control.control_code,
            "title": control.title,
            "category": control.category,
            "outcome": outcome,
            "policy_level": policy_level,
            "message": message,
            "resource_id": secrets_resources[0].id if secrets_resources else None,
            "related_resource_id": None,
            "evidence": {
                "secrets_service_count": len(secrets_resources),
                "services": [r.resource_type for r in secrets_resources],
            },
            "rule_version": control.rule_version,
        }

    @staticmethod
    def _determine_overall_status(findings: list, outcome_counts: dict) -> str:
        """Determine overall compliance status from control findings."""
        # Collect policy levels of failed/blocked controls
        block_fails = [f for f in findings if f["outcome"] == "FAIL" and f["policy_level"] == "BLOCK"]
        required_fails = [f for f in findings if f["outcome"] == "FAIL" and f["policy_level"] == "REQUIRED"]
        
        if block_fails:
            return "BLOCKED"
        elif required_fails:
            return "FAILED"
        elif outcome_counts["WARNING"] > 0 or outcome_counts["NOT_EVALUATED"] > 0:
            return "REVIEW"
        else:
            return "PASSED"
    
    @staticmethod
    def _validate_relationships(
        db: Session,
        architecture_id: UUID,
        version_id: UUID,
    ) -> List[dict]:
        """Validate relationship constraints."""
        findings = []
        
        # Load all resources for this version
        resources_in_version = db.query(Resource).filter(
            Resource.architecture_version_id == version_id
        ).all()
        resource_ids = {r.id for r in resources_in_version}
        
        # Load all relationships for this version
        relationships = db.query(Relationship).filter(
            Relationship.architecture_version_id == version_id
        ).all()
        
        for rel in relationships:
            # Check if source resource exists in this version
            if rel.source_resource_id not in resource_ids:
                findings.append({
                    "architecture_id": architecture_id,
                    "architecture_version_id": version_id,
                    "severity": "ERROR",
                    "category": "RELATIONSHIP",
                    "code": "INVALID_RELATIONSHIP_SOURCE",
                    "message": f"Relationship source resource {rel.source_resource_id} does not exist",
                    "resource_id": rel.source_resource_id,
                    "related_resource_id": rel.target_resource_id,
                    "details": {"relationship_type": rel.relationship_type},
                })
                continue
            
            # Check if target resource exists in this version
            if rel.target_resource_id not in resource_ids:
                findings.append({
                    "architecture_id": architecture_id,
                    "architecture_version_id": version_id,
                    "severity": "ERROR",
                    "category": "RELATIONSHIP",
                    "code": "INVALID_RELATIONSHIP_TARGET",
                    "message": f"Relationship target resource {rel.target_resource_id} does not exist",
                    "resource_id": rel.source_resource_id,
                    "related_resource_id": rel.target_resource_id,
                    "details": {"relationship_type": rel.relationship_type},
                })
                continue
            
            # Check for self-referencing relationships
            if rel.source_resource_id == rel.target_resource_id:
                findings.append({
                    "architecture_id": architecture_id,
                    "architecture_version_id": version_id,
                    "severity": "ERROR",
                    "category": "RELATIONSHIP",
                    "code": "SELF_REFERENCING_RELATIONSHIP",
                    "message": f"Relationship cannot reference the same resource",
                    "resource_id": rel.source_resource_id,
                    "related_resource_id": None,
                    "details": {"relationship_type": rel.relationship_type},
                })
            
            # Check for empty relationship type
            if not rel.relationship_type or not rel.relationship_type.strip():
                findings.append({
                    "architecture_id": architecture_id,
                    "architecture_version_id": version_id,
                    "severity": "ERROR",
                    "category": "RELATIONSHIP",
                    "code": "INVALID_RELATIONSHIP_TYPE",
                    "message": f"Relationship has empty relationship_type",
                    "resource_id": rel.source_resource_id,
                    "related_resource_id": rel.target_resource_id,
                    "details": None,
                })
        
        return findings
    
    @staticmethod
    def _validate_dependencies(
        db: Session,
        architecture_id: UUID,
        version_id: UUID,
    ) -> List[dict]:
        """Validate dependencies using M3 Dependency Engine output."""
        findings = []
        
        # Use Dependency Engine to get findings
        dep_findings = DependencyEngine.analyze_version(db, architecture_id, version_id)
        
        for dep_finding in dep_findings.get("findings", []):
            # Skip already-generated unknown/catalog findings (they're handled by resource validation)
            if dep_finding.get("status") == "CATALOG_RESOURCE_TYPE_UNKNOWN":
                continue  # Already reported in _validate_resources
            
            # Map dependency findings to validation findings
            classification = dep_finding.get("classification")
            status = dep_finding.get("status")
            
            if status == "MISSING":
                if classification == "REQUIRED":
                    severity = "ERROR"
                    code = "REQUIRED_DEPENDENCY_MISSING"
                elif classification == "RECOMMENDED":
                    severity = "WARNING"
                    code = "RECOMMENDED_DEPENDENCY_MISSING"
                else:  # OPTIONAL
                    severity = "INFO"
                    code = "OPTIONAL_DEPENDENCY_MISSING"
                
                findings.append({
                    "architecture_id": architecture_id,
                    "architecture_version_id": version_id,
                    "severity": severity,
                    "category": "DEPENDENCY",
                    "code": code,
                    "message": f"Resource {dep_finding.get('source_resource_key')} requires {dep_finding.get('dependency_resource_type')}",
                    "resource_id": dep_finding.get("source_resource_id"),
                    "related_resource_id": None,
                    "details": {
                        "source_type": dep_finding.get("source_resource_type"),
                        "dependency_type": dep_finding.get("dependency_resource_type"),
                        "classification": classification,
                    },
                })
        
        return findings
