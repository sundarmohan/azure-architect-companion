"""
Tests for resource service.
"""

from uuid import uuid4
import pytest
from sqlalchemy.orm import Session

from app.services import (
    ArchitectureService,
    ArchitectureVersionService,
    ResourceService,
)
from app.schemas import (
    ArchitectureCreate,
    ArchitectureVersionCreate,
    ResourceCreate,
)


class TestResourceService:
    """Tests for ResourceService."""

    @pytest.fixture
    def setup_architecture_version(self, db: Session, architecture_data, version_data):
        """Setup an architecture and version for testing."""
        arch_schema = ArchitectureCreate(**architecture_data)
        architecture = ArchitectureService.create(db, arch_schema)

        version_schema = ArchitectureVersionCreate(**version_data)
        version = ArchitectureVersionService.create(db, architecture.id, version_schema)

        return version

    def test_create_resource(self, db: Session, setup_architecture_version, resource_group_data):
        """Test creating a resource."""
        version = setup_architecture_version
        schema = ResourceCreate(**resource_group_data)
        resource = ResourceService.create(db, version.id, schema)

        assert resource is not None
        assert resource.id is not None
        assert resource.architecture_version_id == version.id
        assert resource.resource_key == resource_group_data["resource_key"]
        assert resource.resource_type == resource_group_data["resource_type"]
        assert resource.name == resource_group_data["name"]
        assert resource.location == resource_group_data["location"]

    def test_get_resource(self, db: Session, setup_architecture_version, resource_group_data):
        """Test getting a resource by ID."""
        version = setup_architecture_version
        schema = ResourceCreate(**resource_group_data)
        created = ResourceService.create(db, version.id, schema)

        retrieved = ResourceService.get(db, created.id)
        assert retrieved is not None
        assert retrieved.id == created.id

    def test_list_resources_by_version(self, db: Session, setup_architecture_version, resource_group_data):
        """Test listing resources in a version."""
        version = setup_architecture_version

        # Create multiple resources
        for i in range(3):
            data = {**resource_group_data, "resource_key": f"rg-{i}", "name": f"rg-{i}"}
            schema = ResourceCreate(**data)
            ResourceService.create(db, version.id, schema)

        resources = ResourceService.list_by_version(db, version.id)
        assert len(resources) == 3

    def test_list_resources_by_type(self, db: Session, setup_architecture_version, resource_group_data, vnet_data):
        """Test listing resources of a specific type."""
        version = setup_architecture_version

        # Create resource groups
        for i in range(2):
            data = {**resource_group_data, "resource_key": f"rg-{i}", "name": f"rg-{i}"}
            schema = ResourceCreate(**data)
            ResourceService.create(db, version.id, schema)

        # Create vnets
        for i in range(3):
            data = {**vnet_data, "resource_key": f"vnet-{i}", "name": f"vnet-{i}"}
            schema = ResourceCreate(**data)
            ResourceService.create(db, version.id, schema)

        rg_resources = ResourceService.list_by_type(db, version.id, resource_group_data["resource_type"])
        assert len(rg_resources) == 2

        vnet_resources = ResourceService.list_by_type(db, version.id, vnet_data["resource_type"])
        assert len(vnet_resources) == 3

    def test_parent_child_hierarchy(self, db: Session, setup_architecture_version, resource_group_data, vnet_data):
        """Test parent-child resource hierarchy."""
        version = setup_architecture_version

        # Create resource group
        rg_schema = ResourceCreate(**resource_group_data)
        resource_group = ResourceService.create(db, version.id, rg_schema)

        # Create vnet with resource group as parent
        vnet_data_with_parent = {**vnet_data, "parent_resource_id": resource_group.id}
        vnet_schema = ResourceCreate(**vnet_data_with_parent)
        vnet = ResourceService.create(db, version.id, vnet_schema)

        assert vnet.parent_resource_id == resource_group.id

        # Verify parent relationship
        retrieved_vnet = ResourceService.get(db, vnet.id)
        assert retrieved_vnet.parent_resource_id == resource_group.id

    def test_multiple_resource_groups(self, db: Session, setup_architecture_version, resource_group_data):
        """Test multiple resource groups in one version."""
        version = setup_architecture_version

        # Create multiple resource groups
        rg1_data = {**resource_group_data, "resource_key": "rg-1", "name": "rg-1", "location": "eastus"}
        rg2_data = {**resource_group_data, "resource_key": "rg-2", "name": "rg-2", "location": "westus"}
        rg3_data = {**resource_group_data, "resource_key": "rg-3", "name": "rg-3", "location": "northeurope"}

        rg1 = ResourceService.create(db, version.id, ResourceCreate(**rg1_data))
        rg2 = ResourceService.create(db, version.id, ResourceCreate(**rg2_data))
        rg3 = ResourceService.create(db, version.id, ResourceCreate(**rg3_data))

        assert rg1.location == "eastus"
        assert rg2.location == "westus"
        assert rg3.location == "northeurope"

        rg_resources = ResourceService.list_by_type(
            db,
            version.id,
            resource_group_data["resource_type"]
        )
        assert len(rg_resources) == 3

    def test_multiple_vnets(self, db: Session, setup_architecture_version, resource_group_data, vnet_data):
        """Test multiple VNets in one resource group."""
        version = setup_architecture_version

        # Create resource group
        rg_schema = ResourceCreate(**resource_group_data)
        resource_group = ResourceService.create(db, version.id, rg_schema)

        # Create multiple vnets
        vnet1_data = {**vnet_data, "resource_key": "vnet-1", "name": "vnet-1", "parent_resource_id": resource_group.id}
        vnet2_data = {**vnet_data, "resource_key": "vnet-2", "name": "vnet-2", "parent_resource_id": resource_group.id}
        vnet3_data = {**vnet_data, "resource_key": "vnet-3", "name": "vnet-3", "parent_resource_id": resource_group.id}

        vnet1 = ResourceService.create(db, version.id, ResourceCreate(**vnet1_data))
        vnet2 = ResourceService.create(db, version.id, ResourceCreate(**vnet2_data))
        vnet3 = ResourceService.create(db, version.id, ResourceCreate(**vnet3_data))

        # Verify all vnets have the resource group as parent
        assert vnet1.parent_resource_id == resource_group.id
        assert vnet2.parent_resource_id == resource_group.id
        assert vnet3.parent_resource_id == resource_group.id

    def test_multiple_subnets_per_vnet(self, db: Session, setup_architecture_version, resource_group_data, vnet_data, subnet_data):
        """Test multiple subnets in one VNet."""
        version = setup_architecture_version

        # Create resource group
        rg_schema = ResourceCreate(**resource_group_data)
        resource_group = ResourceService.create(db, version.id, rg_schema)

        # Create vnet
        vnet_data_with_parent = {**vnet_data, "parent_resource_id": resource_group.id}
        vnet_schema = ResourceCreate(**vnet_data_with_parent)
        vnet = ResourceService.create(db, version.id, vnet_schema)

        # Create multiple subnets
        subnet1_data = {**subnet_data, "resource_key": "subnet-1", "name": "subnet-1", "parent_resource_id": vnet.id}
        subnet2_data = {**subnet_data, "resource_key": "subnet-2", "name": "subnet-2", "parent_resource_id": vnet.id}
        subnet3_data = {**subnet_data, "resource_key": "subnet-3", "name": "subnet-3", "parent_resource_id": vnet.id}

        subnet1 = ResourceService.create(db, version.id, ResourceCreate(**subnet1_data))
        subnet2 = ResourceService.create(db, version.id, ResourceCreate(**subnet2_data))
        subnet3 = ResourceService.create(db, version.id, ResourceCreate(**subnet3_data))

        # Verify all subnets have the vnet as parent
        assert subnet1.parent_resource_id == vnet.id
        assert subnet2.parent_resource_id == vnet.id
        assert subnet3.parent_resource_id == vnet.id

    def test_invalid_parent_reference(self, db: Session, setup_architecture_version, resource_group_data):
        """Test that invalid parent reference raises error."""
        version = setup_architecture_version
        invalid_parent_id = uuid4()

        data = {**resource_group_data, "parent_resource_id": invalid_parent_id}
        schema = ResourceCreate(**data)

        with pytest.raises(ValueError, match="Parent resource not found"):
            ResourceService.create(db, version.id, schema)

    def test_invalid_version_reference(self, db: Session, resource_group_data):
        """Test creating resource with nonexistent version."""
        schema = ResourceCreate(**resource_group_data)
        result = ResourceService.create(db, uuid4(), schema)
        assert result is None
