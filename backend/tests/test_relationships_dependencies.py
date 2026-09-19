"""
Tests for relationships and dependencies.
"""

from uuid import uuid4
import pytest
from sqlalchemy.orm import Session

from app.services import (
    ArchitectureService,
    ArchitectureVersionService,
    ResourceService,
    RelationshipService,
    DependencyService,
)
from app.schemas import (
    ArchitectureCreate,
    ArchitectureVersionCreate,
    ResourceCreate,
    RelationshipCreate,
    DependencyCreate,
)


@pytest.fixture
def setup_resources(db: Session, architecture_data, version_data, resource_group_data, vnet_data, subnet_data):
    """Setup architecture, version, and multiple resources for testing."""
    # Create architecture and version
    arch_schema = ArchitectureCreate(**architecture_data)
    architecture = ArchitectureService.create(db, arch_schema)

    version_schema = ArchitectureVersionCreate(**version_data)
    version = ArchitectureVersionService.create(db, architecture.id, version_schema)

    # Create resource group
    rg_schema = ResourceCreate(**resource_group_data)
    resource_group = ResourceService.create(db, version.id, rg_schema)

    # Create vnet
    vnet_data_with_parent = {**vnet_data, "parent_resource_id": resource_group.id}
    vnet_schema = ResourceCreate(**vnet_data_with_parent)
    vnet = ResourceService.create(db, version.id, vnet_schema)

    # Create subnet
    subnet_data_with_parent = {**subnet_data, "parent_resource_id": vnet.id}
    subnet_schema = ResourceCreate(**subnet_data_with_parent)
    subnet = ResourceService.create(db, version.id, subnet_schema)

    return {
        "version": version,
        "resource_group": resource_group,
        "vnet": vnet,
        "subnet": subnet,
    }


class TestRelationshipService:
    """Tests for RelationshipService."""

    def test_create_relationship(self, db: Session, setup_resources):
        """Test creating a relationship."""
        resources = setup_resources
        vnet = resources["vnet"]
        subnet = resources["subnet"]

        rel_data = {
            "source_resource_id": vnet.id,
            "target_resource_id": subnet.id,
            "relationship_type": "contains",
        }
        schema = RelationshipCreate(**rel_data)
        relationship = RelationshipService.create(db, resources["version"].id, schema)

        assert relationship is not None
        assert relationship.source_resource_id == vnet.id
        assert relationship.target_resource_id == subnet.id
        assert relationship.relationship_type == "contains"

    def test_get_relationship(self, db: Session, setup_resources):
        """Test getting a relationship by ID."""
        resources = setup_resources
        vnet = resources["vnet"]
        subnet = resources["subnet"]

        rel_data = {
            "source_resource_id": vnet.id,
            "target_resource_id": subnet.id,
            "relationship_type": "contains",
        }
        schema = RelationshipCreate(**rel_data)
        created = RelationshipService.create(db, resources["version"].id, schema)

        retrieved = RelationshipService.get(db, created.id)
        assert retrieved is not None
        assert retrieved.id == created.id

    def test_list_relationships(self, db: Session, setup_resources):
        """Test listing relationships in a version."""
        resources = setup_resources
        rg = resources["resource_group"]
        vnet = resources["vnet"]
        subnet = resources["subnet"]

        # Create multiple relationships
        rel1_data = {
            "source_resource_id": rg.id,
            "target_resource_id": vnet.id,
            "relationship_type": "contains",
        }
        RelationshipService.create(db, resources["version"].id, RelationshipCreate(**rel1_data))

        rel2_data = {
            "source_resource_id": vnet.id,
            "target_resource_id": subnet.id,
            "relationship_type": "contains",
        }
        RelationshipService.create(db, resources["version"].id, RelationshipCreate(**rel2_data))

        relationships = RelationshipService.list_by_version(db, resources["version"].id)
        assert len(relationships) == 2

    def test_relationship_with_metadata(self, db: Session, setup_resources):
        """Test relationship with metadata."""
        resources = setup_resources
        vnet = resources["vnet"]
        subnet = resources["subnet"]

        rel_data = {
            "source_resource_id": vnet.id,
            "target_resource_id": subnet.id,
            "relationship_type": "contains",
            "metadata": {"connection_type": "direct", "bandwidth": "10Gbps"},
        }
        schema = RelationshipCreate(**rel_data)
        relationship = RelationshipService.create(db, resources["version"].id, schema)

        retrieved = RelationshipService.get(db, relationship.id)
        assert retrieved.metadata["connection_type"] == "direct"
        assert retrieved.metadata["bandwidth"] == "10Gbps"

    def test_relationship_same_source_target_error(self, db: Session, setup_resources):
        """Test that a resource cannot relate to itself."""
        resources = setup_resources
        vnet = resources["vnet"]

        rel_data = {
            "source_resource_id": vnet.id,
            "target_resource_id": vnet.id,
            "relationship_type": "contains",
        }
        schema = RelationshipCreate(**rel_data)

        with pytest.raises(ValueError, match="cannot be the same"):
            RelationshipService.create(db, resources["version"].id, schema)

    def test_relationship_invalid_resource(self, db: Session, setup_resources):
        """Test creating relationship with invalid resource."""
        resources = setup_resources
        vnet = resources["vnet"]
        invalid_id = uuid4()

        rel_data = {
            "source_resource_id": vnet.id,
            "target_resource_id": invalid_id,
            "relationship_type": "contains",
        }
        schema = RelationshipCreate(**rel_data)

        with pytest.raises(ValueError, match="not found or belongs to different version"):
            RelationshipService.create(db, resources["version"].id, schema)


class TestDependencyService:
    """Tests for DependencyService."""

    def test_create_dependency(self, db: Session, setup_resources):
        """Test creating a dependency."""
        resources = setup_resources
        vnet = resources["vnet"]
        subnet = resources["subnet"]

        dep_data = {
            "resource_id": subnet.id,
            "depends_on_resource_id": vnet.id,
            "dependency_type": "requires",
            "required": True,
            "reason": "Subnet must exist in a VNet",
        }
        schema = DependencyCreate(**dep_data)
        dependency = DependencyService.create(db, resources["version"].id, schema)

        assert dependency is not None
        assert dependency.resource_id == subnet.id
        assert dependency.depends_on_resource_id == vnet.id
        assert dependency.dependency_type == "requires"
        assert dependency.required is True
        assert dependency.reason == "Subnet must exist in a VNet"

    def test_get_dependency(self, db: Session, setup_resources):
        """Test getting a dependency by ID."""
        resources = setup_resources
        vnet = resources["vnet"]
        subnet = resources["subnet"]

        dep_data = {
            "resource_id": subnet.id,
            "depends_on_resource_id": vnet.id,
            "dependency_type": "requires",
            "required": True,
        }
        schema = DependencyCreate(**dep_data)
        created = DependencyService.create(db, resources["version"].id, schema)

        retrieved = DependencyService.get(db, created.id)
        assert retrieved is not None
        assert retrieved.id == created.id

    def test_list_dependencies(self, db: Session, setup_resources):
        """Test listing dependencies in a version."""
        resources = setup_resources
        rg = resources["resource_group"]
        vnet = resources["vnet"]
        subnet = resources["subnet"]

        # Create multiple dependencies
        dep1_data = {
            "resource_id": vnet.id,
            "depends_on_resource_id": rg.id,
            "dependency_type": "requires",
            "required": True,
        }
        DependencyService.create(db, resources["version"].id, DependencyCreate(**dep1_data))

        dep2_data = {
            "resource_id": subnet.id,
            "depends_on_resource_id": vnet.id,
            "dependency_type": "requires",
            "required": True,
        }
        DependencyService.create(db, resources["version"].id, DependencyCreate(**dep2_data))

        dependencies = DependencyService.list_by_version(db, resources["version"].id)
        assert len(dependencies) == 2

    def test_list_dependencies_by_resource(self, db: Session, setup_resources):
        """Test listing dependencies for a specific resource."""
        resources = setup_resources
        rg = resources["resource_group"]
        vnet = resources["vnet"]
        subnet = resources["subnet"]

        # Create dependencies
        dep1_data = {
            "resource_id": vnet.id,
            "depends_on_resource_id": rg.id,
            "dependency_type": "requires",
            "required": True,
        }
        DependencyService.create(db, resources["version"].id, DependencyCreate(**dep1_data))

        dep2_data = {
            "resource_id": subnet.id,
            "depends_on_resource_id": vnet.id,
            "dependency_type": "requires",
            "required": True,
        }
        DependencyService.create(db, resources["version"].id, DependencyCreate(**dep2_data))

        # List dependencies for subnet
        subnet_deps = DependencyService.list_by_resource(db, subnet.id)
        assert len(subnet_deps) == 1
        assert subnet_deps[0].resource_id == subnet.id

    def test_required_vs_optional_dependency(self, db: Session, setup_resources):
        """Test required vs optional dependencies."""
        resources = setup_resources
        vnet = resources["vnet"]
        subnet = resources["subnet"]

        # Required dependency
        req_dep_data = {
            "resource_id": subnet.id,
            "depends_on_resource_id": vnet.id,
            "dependency_type": "requires",
            "required": True,
        }
        req_dep = DependencyService.create(db, resources["version"].id, DependencyCreate(**req_dep_data))
        assert req_dep.required is True

        # Optional dependency (e.g., monitoring)
        opt_dep_data = {
            "resource_id": subnet.id,
            "depends_on_resource_id": vnet.id,
            "dependency_type": "can_use",
            "required": False,
        }
        opt_dep = DependencyService.create(db, resources["version"].id, DependencyCreate(**opt_dep_data))
        assert opt_dep.required is False

    def test_dependency_same_resource_error(self, db: Session, setup_resources):
        """Test that a resource cannot depend on itself."""
        resources = setup_resources
        subnet = resources["subnet"]

        dep_data = {
            "resource_id": subnet.id,
            "depends_on_resource_id": subnet.id,
            "dependency_type": "requires",
            "required": True,
        }
        schema = DependencyCreate(**dep_data)

        with pytest.raises(ValueError, match="cannot depend on itself"):
            DependencyService.create(db, resources["version"].id, schema)

    def test_dependency_invalid_resource(self, db: Session, setup_resources):
        """Test creating dependency with invalid resource."""
        resources = setup_resources
        subnet = resources["subnet"]
        invalid_id = uuid4()

        dep_data = {
            "resource_id": subnet.id,
            "depends_on_resource_id": invalid_id,
            "dependency_type": "requires",
            "required": True,
        }
        schema = DependencyCreate(**dep_data)

        with pytest.raises(ValueError, match="not found or belongs to different version"):
            DependencyService.create(db, resources["version"].id, schema)
