"""
Tests for Resource Catalog service.
"""

import pytest
from sqlalchemy.orm import Session

from app.models import ResourceCatalog, CatalogDependency, CatalogHierarchy
from app.models import Relationship
from app.services import CatalogService


@pytest.fixture
def sample_resources(db: Session):
    """Create sample resource types for testing."""
    # Create Resource Group
    rg = CatalogService.register_resource_type(
        db,
        provider="azure",
        resource_type="microsoft.resources/resourcegroups",
        display_name="Resource Group",
        category="management",
        description="Azure Resource Group",
        terraform_mapping={"terraform_type": "azurerm_resource_group", "provider": "azurerm"},
    )

    # Create Virtual Network
    vnet = CatalogService.register_resource_type(
        db,
        provider="azure",
        resource_type="microsoft.network/virtualnetworks",
        display_name="Virtual Network",
        category="networking",
        description="Azure Virtual Network",
        terraform_mapping={"terraform_type": "azurerm_virtual_network", "provider": "azurerm"},
    )

    # Create Subnet
    subnet = CatalogService.register_resource_type(
        db,
        provider="azure",
        resource_type="microsoft.network/virtualnetworks/subnets",
        display_name="Subnet",
        category="networking",
        description="Azure Subnet",
        terraform_mapping={"terraform_type": "azurerm_subnet", "provider": "azurerm"},
    )

    # Create Network Security Group
    nsg = CatalogService.register_resource_type(
        db,
        provider="azure",
        resource_type="microsoft.network/networksecuritygroups",
        display_name="Network Security Group",
        category="networking",
        description="Azure Network Security Group",
        terraform_mapping={"terraform_type": "azurerm_network_security_group", "provider": "azurerm"},
    )

    # Create Virtual Machine
    vm = CatalogService.register_resource_type(
        db,
        provider="azure",
        resource_type="microsoft.compute/virtualmachines",
        display_name="Virtual Machine",
        category="compute",
        description="Azure Virtual Machine",
        terraform_mapping={"terraform_type": "azurerm_windows_virtual_machine", "provider": "azurerm"},
    )

    # Create Storage Account
    storage = CatalogService.register_resource_type(
        db,
        provider="azure",
        resource_type="microsoft.storage/storageaccounts",
        display_name="Storage Account",
        category="storage",
        description="Azure Storage Account",
        terraform_mapping={"terraform_type": "azurerm_storage_account", "provider": "azurerm"},
    )

    return {
        "rg": rg,
        "vnet": vnet,
        "subnet": subnet,
        "nsg": nsg,
        "vm": vm,
        "storage": storage,
    }


class TestCatalogRegistration:
    """Test resource catalog registration."""

    def test_metadata_columns_use_safe_python_attributes(self):
        """Model imports preserve metadata columns without reserved attributes."""
        assert hasattr(Relationship, "relationship_metadata")
        assert hasattr(ResourceCatalog, "resource_metadata")
        assert "metadata" in Relationship.__table__.columns
        assert "metadata" in ResourceCatalog.__table__.columns

    def test_register_resource_type(self, db: Session):
        """Test registering a resource type."""
        metadata = {"service_tier": "platform"}
        resource = CatalogService.register_resource_type(
            db,
            provider="azure",
            resource_type="microsoft.compute/virtualmachines",
            display_name="Virtual Machine",
            category="compute",
            description="A virtual machine",
            metadata=metadata,
        )

        assert resource.provider == "azure"
        assert resource.resource_type == "microsoft.compute/virtualmachines"
        assert resource.display_name == "Virtual Machine"
        assert resource.category == "compute"
        assert resource.resource_metadata == metadata
        assert resource.enabled is True

    def test_register_resource_with_terraform_mapping(self, db: Session):
        """Test registering a resource with Terraform mapping."""
        terraform_mapping = {
            "terraform_type": "azurerm_windows_virtual_machine",
            "provider": "azurerm",
            "additional_mapping": {"key": "value"},
        }

        resource = CatalogService.register_resource_type(
            db,
            provider="azure",
            resource_type="microsoft.compute/virtualmachines",
            display_name="Virtual Machine",
            category="compute",
            terraform_mapping=terraform_mapping,
        )

        assert resource.terraform_mapping == terraform_mapping


class TestCatalogLookup:
    """Test resource catalog lookup operations."""

    def test_get_resource_type(self, db: Session, sample_resources):
        """Test getting a resource type by name."""
        resource = CatalogService.get_resource_type(db, "microsoft.compute/virtualmachines")
        assert resource is None  # VM not in sample_resources

        resource = CatalogService.get_resource_type(db, "microsoft.resources/resourcegroups")
        assert resource is not None
        assert resource.display_name == "Resource Group"

    def test_get_nonexistent_resource_type(self, db: Session):
        """Test getting a nonexistent resource type."""
        resource = CatalogService.get_resource_type(db, "nonexistent.type/resource")
        assert resource is None

    def test_resource_type_exists(self, db: Session, sample_resources):
        """Test checking if a resource type exists."""
        exists = CatalogService.resource_type_exists(db, "microsoft.resources/resourcegroups")
        assert exists is True

        exists = CatalogService.resource_type_exists(db, "nonexistent.type/resource")
        assert exists is False


class TestCatalogListing:
    """Test resource catalog listing operations."""

    def test_list_all_resources(self, db: Session, sample_resources):
        """Test listing all resources."""
        resources = CatalogService.list_all_resources(db)
        assert len(resources) == 6

    def test_list_by_provider(self, db: Session, sample_resources):
        """Test filtering resources by provider."""
        azure_resources = CatalogService.list_by_provider(db, "azure")
        assert len(azure_resources) == 6
        assert all(r.provider == "azure" for r in azure_resources)

    def test_list_by_category(self, db: Session, sample_resources):
        """Test filtering resources by category."""
        networking = CatalogService.list_by_category(db, "networking")
        assert len(networking) == 3
        assert all(r.category == "networking" for r in networking)

        compute = CatalogService.list_by_category(db, "compute")
        assert len(compute) == 1
        assert compute[0].resource_type == "microsoft.compute/virtualmachines"


class TestCatalogDependencies:
    """Test dependency classification."""

    def test_add_required_dependency(self, db: Session, sample_resources):
        """Test adding a required dependency."""
        dep = CatalogService.add_required_dependency(
            db,
            "microsoft.compute/virtualmachines",
            "microsoft.network/networkinterfaces",
            reason="VM requires a NIC",
        )

        assert dep.dependency_classification == "REQUIRED"
        assert dep.depends_on_resource_type == "microsoft.network/networkinterfaces"
        assert dep.reason == "VM requires a NIC"

    def test_add_recommended_dependency(self, db: Session, sample_resources):
        """Test adding a recommended dependency."""
        dep = CatalogService.add_recommended_dependency(
            db,
            "microsoft.compute/virtualmachines",
            "microsoft.network/networksecuritygroups",
            reason="Recommended for network security",
        )

        assert dep.dependency_classification == "RECOMMENDED"

    def test_add_optional_dependency(self, db: Session, sample_resources):
        """Test adding an optional dependency."""
        dep = CatalogService.add_optional_dependency(
            db,
            "microsoft.compute/virtualmachines",
            "microsoft.storage/storageaccounts",
            reason="Optional boot diagnostics storage",
        )

        assert dep.dependency_classification == "OPTIONAL"

    def test_get_required_dependencies(self, db: Session, sample_resources):
        """Test getting required dependencies for a resource type."""
        CatalogService.add_required_dependency(
            db,
            "microsoft.compute/virtualmachines",
            "microsoft.network/networkinterfaces",
        )
        CatalogService.add_required_dependency(
            db,
            "microsoft.compute/virtualmachines",
            "microsoft.compute/disks",
        )

        required = CatalogService.get_required_dependencies(db, "microsoft.compute/virtualmachines")
        assert len(required) == 2
        assert all(d.dependency_classification == "REQUIRED" for d in required)

    def test_get_recommended_dependencies(self, db: Session, sample_resources):
        """Test getting recommended dependencies for a resource type."""
        CatalogService.add_recommended_dependency(
            db,
            "microsoft.compute/virtualmachines",
            "microsoft.network/networksecuritygroups",
        )

        recommended = CatalogService.get_recommended_dependencies(db, "microsoft.compute/virtualmachines")
        assert len(recommended) == 1
        assert recommended[0].dependency_classification == "RECOMMENDED"

    def test_get_optional_dependencies(self, db: Session, sample_resources):
        """Test getting optional dependencies for a resource type."""
        CatalogService.add_optional_dependency(
            db,
            "microsoft.compute/virtualmachines",
            "microsoft.storage/storageaccounts",
        )

        optional = CatalogService.get_optional_dependencies(db, "microsoft.compute/virtualmachines")
        assert len(optional) == 1
        assert optional[0].dependency_classification == "OPTIONAL"

    def test_get_all_dependencies(self, db: Session, sample_resources):
        """Test getting all classifications of dependencies."""
        CatalogService.add_required_dependency(
            db,
            "microsoft.compute/virtualmachines",
            "microsoft.network/networkinterfaces",
        )
        CatalogService.add_recommended_dependency(
            db,
            "microsoft.compute/virtualmachines",
            "microsoft.network/networksecuritygroups",
        )
        CatalogService.add_optional_dependency(
            db,
            "microsoft.compute/virtualmachines",
            "microsoft.storage/storageaccounts",
        )

        all_deps = CatalogService.get_all_dependencies(db, "microsoft.compute/virtualmachines")
        assert len(all_deps["required"]) == 1
        assert len(all_deps["recommended"]) == 1
        assert len(all_deps["optional"]) == 1


class TestCatalogHierarchy:
    """Test hierarchy (containment) relationships."""

    def test_add_hierarchy(self, db: Session, sample_resources):
        """Test adding a parent-child hierarchy."""
        hierarchy = CatalogService.add_hierarchy(
            db,
            "microsoft.resources/resourcegroups",
            "microsoft.network/virtualnetworks",
            description="VNet is contained in Resource Group",
        )

        assert hierarchy.description == "VNet is contained in Resource Group"

    def test_get_valid_parent_types(self, db: Session, sample_resources):
        """Test getting valid parent types for a resource."""
        CatalogService.add_hierarchy(db, "microsoft.resources/resourcegroups", "microsoft.network/virtualnetworks")
        CatalogService.add_hierarchy(db, "microsoft.network/virtualnetworks", "microsoft.network/virtualnetworks/subnets")

        # VNet has Resource Group as parent
        parents = CatalogService.get_valid_parent_types(db, "microsoft.network/virtualnetworks")
        assert "microsoft.resources/resourcegroups" in parents

        # Subnet has VNet as parent
        parents = CatalogService.get_valid_parent_types(db, "microsoft.network/virtualnetworks/subnets")
        assert "microsoft.network/virtualnetworks" in parents

    def test_get_valid_child_types(self, db: Session, sample_resources):
        """Test getting valid child types for a resource."""
        CatalogService.add_hierarchy(db, "microsoft.resources/resourcegroups", "microsoft.network/virtualnetworks")
        CatalogService.add_hierarchy(db, "microsoft.resources/resourcegroups", "microsoft.storage/storageaccounts")

        children = CatalogService.get_valid_child_types(db, "microsoft.resources/resourcegroups")
        assert "microsoft.network/virtualnetworks" in children
        assert "microsoft.storage/storageaccounts" in children


class TestCatalogTerraform:
    """Test Terraform mapping operations."""

    def test_get_terraform_mapping(self, db: Session, sample_resources):
        """Test getting Terraform mapping for a resource type."""
        mapping = CatalogService.get_terraform_mapping(db, "microsoft.compute/virtualmachines")
        # VM not in sample_resources, so should return None
        assert mapping is None

        mapping = CatalogService.get_terraform_mapping(db, "microsoft.resources/resourcegroups")
        assert mapping is not None
        assert mapping.get("terraform_type") == "azurerm_resource_group"


class TestCatalogCategories:
    """Test category operations."""

    def test_get_categories(self, db: Session, sample_resources):
        """Test getting all categories."""
        categories = CatalogService.get_categories(db)
        assert "compute" in categories
        assert "networking" in categories
        assert "storage" in categories
        assert "management" in categories
        assert len(categories) == 4
