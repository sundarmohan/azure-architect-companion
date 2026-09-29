"""
Tests for Resource Catalog API endpoints.
"""

from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.db.session import get_db
from app.services import CatalogService


@pytest.fixture
def client(db):
    """Create a test client."""
    app = create_app()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def setup_catalog(db):
    """Setup catalog with sample resource types."""
    # Create Resource Group
    rg = CatalogService.register_resource_type(
        db,
        provider="azure",
        resource_type="microsoft.resources/resourcegroups",
        display_name="Resource Group",
        category="management",
        description="Azure Resource Group",
        terraform_mapping={"terraform_type": "azurerm_resource_group", "provider": "azurerm"},
        metadata={"scope": "subscription"},
        metadata={"scope": "subscription"},
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
    )

    # Create Public IP
    pip = CatalogService.register_resource_type(
        db,
        provider="azure",
        resource_type="microsoft.network/publicipaddresses",
        display_name="Public IP",
        category="networking",
        description="Azure Public IP",
    )

    # Create Network Interface
    nic = CatalogService.register_resource_type(
        db,
        provider="azure",
        resource_type="microsoft.network/networkinterfaces",
        display_name="Network Interface",
        category="networking",
        description="Azure Network Interface",
    )

    # Create App Service Plan
    asp = CatalogService.register_resource_type(
        db,
        provider="azure",
        resource_type="microsoft.web/serverfarms",
        display_name="App Service Plan",
        category="compute",
        description="Azure App Service Plan",
    )

    # Create App Service
    app = CatalogService.register_resource_type(
        db,
        provider="azure",
        resource_type="microsoft.web/sites",
        display_name="App Service",
        category="compute",
        description="Azure App Service",
    )

    # Create Key Vault
    kv = CatalogService.register_resource_type(
        db,
        provider="azure",
        resource_type="microsoft.keyvault/vaults",
        display_name="Key Vault",
        category="security",
        description="Azure Key Vault",
    )

    # Create PostgreSQL Flexible Server
    postgres = CatalogService.register_resource_type(
        db,
        provider="azure",
        resource_type="microsoft.dbforpostgresql/flexibleservers",
        display_name="PostgreSQL Flexible Server",
        category="database",
        description="Azure PostgreSQL Flexible Server",
    )

    # Create SQL Database
    sql_db = CatalogService.register_resource_type(
        db,
        provider="azure",
        resource_type="microsoft.sql/servers/databases",
        display_name="SQL Database",
        category="database",
        description="Azure SQL Database",
    )

    # Create Log Analytics Workspace
    law = CatalogService.register_resource_type(
        db,
        provider="azure",
        resource_type="microsoft.operationalinsights/workspaces",
        display_name="Log Analytics Workspace",
        category="monitoring",
        description="Azure Log Analytics Workspace",
    )

    # Add dependencies for VM
    CatalogService.add_required_dependency(
        db,
        "microsoft.compute/virtualmachines",
        "microsoft.network/networkinterfaces",
        reason="VM requires a NIC",
    )

    # Add hierarchy relationships
    CatalogService.add_hierarchy(
        db,
        "microsoft.resources/resourcegroups",
        "microsoft.network/virtualnetworks",
    )
    CatalogService.add_hierarchy(
        db,
        "microsoft.network/virtualnetworks",
        "microsoft.network/virtualnetworks/subnets",
    )

    return {
        "rg": rg,
        "vnet": vnet,
        "subnet": subnet,
        "nsg": nsg,
        "vm": vm,
        "storage": storage,
        "pip": pip,
        "nic": nic,
        "asp": asp,
        "app": app,
        "kv": kv,
        "postgres": postgres,
        "sql_db": sql_db,
        "law": law,
    }


class TestCatalogListEndpoint:
    """Test GET /catalog/resources endpoint."""

    def test_list_all_resources(self, client: TestClient, setup_catalog):
        """Test listing all resources."""
        response = client.get("/catalog/resources")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 14
        assert len(data["resources"]) == 14

    def test_list_resources_filter_by_provider(self, client: TestClient, setup_catalog):
        """Test filtering resources by provider."""
        response = client.get("/catalog/resources?provider=azure")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 14
        assert all(r["provider"] == "azure" for r in data["resources"])

    def test_list_resources_filter_by_category(self, client: TestClient, setup_catalog):
        """Test filtering resources by category."""
        response = client.get("/catalog/resources?category=networking")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert all(r["category"] == "networking" for r in data["resources"])

    def test_list_resources_category_compute(self, client: TestClient, setup_catalog):
        """Test listing compute resources."""
        response = client.get("/catalog/resources?category=compute")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3


class TestCatalogGetEndpoint:
    """Test GET /catalog/resources/{resource_type} endpoint."""

    def test_get_resource_type(self, client: TestClient, setup_catalog):
        """Test getting a single resource type."""
        response = client.get("/catalog/resources/microsoft.resources/resourcegroups")
        assert response.status_code == 200
        data = response.json()
        assert data["resource_type"] == "microsoft.resources/resourcegroups"
        assert data["display_name"] == "Resource Group"
        assert data["provider"] == "azure"
        assert data["category"] == "management"
        assert data["metadata"] == {"scope": "subscription"}
        assert data["metadata"] == {"scope": "subscription"}

    def test_get_resource_type_with_dependencies(self, client: TestClient, setup_catalog):
        """Test getting a resource type with dependencies."""
        response = client.get("/catalog/resources/microsoft.compute/virtualmachines")
        assert response.status_code == 200
        data = response.json()
        assert len(data["required_dependencies"]) == 1
        assert data["required_dependencies"][0]["depends_on_resource_type"] == "microsoft.network/networkinterfaces"

    def test_get_resource_type_with_hierarchy(self, client: TestClient, setup_catalog):
        """Test getting a resource type with hierarchy information."""
        response = client.get("/catalog/resources/microsoft.resources/resourcegroups")
        assert response.status_code == 200
        data = response.json()
        assert "microsoft.network/virtualnetworks" in data["valid_child_types"]

    def test_get_nonexistent_resource_type(self, client: TestClient, setup_catalog):
        """Test getting a nonexistent resource type."""
        response = client.get("/catalog/resources/nonexistent.type/resource")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestCatalogDependenciesEndpoint:
    """Test GET /catalog/resources/{resource_type}/dependencies endpoint."""

    def test_get_dependencies(self, client: TestClient, setup_catalog):
        """Test getting dependencies for a resource type."""
        response = client.get("/catalog/resources/microsoft.compute/virtualmachines/dependencies")
        assert response.status_code == 200
        data = response.json()
        assert data["resource_type"] == "microsoft.compute/virtualmachines"
        assert len(data["required"]) == 1
        assert data["required"][0]["dependency_classification"] == "REQUIRED"

    def test_get_dependencies_no_dependencies(self, client: TestClient, setup_catalog):
        """Test getting dependencies for resource with no dependencies."""
        response = client.get("/catalog/resources/microsoft.resources/resourcegroups/dependencies")
        assert response.status_code == 200
        data = response.json()
        assert len(data["required"]) == 0
        assert len(data["recommended"]) == 0
        assert len(data["optional"]) == 0

    def test_get_dependencies_nonexistent_resource(self, client: TestClient, setup_catalog):
        """Test getting dependencies for nonexistent resource."""
        response = client.get("/catalog/resources/nonexistent.type/resource/dependencies")
        assert response.status_code == 404


class TestCatalogTerraformEndpoint:
    """Test GET /catalog/resources/{resource_type}/terraform endpoint."""

    def test_get_terraform_mapping(self, client: TestClient, setup_catalog):
        """Test getting Terraform mapping for a resource type."""
        response = client.get("/catalog/resources/microsoft.resources/resourcegroups/terraform")
        assert response.status_code == 200
        data = response.json()
        assert data["resource_type"] == "microsoft.resources/resourcegroups"
        assert data["terraform_type"] == "azurerm_resource_group"
        assert data["provider"] == "azurerm"

    def test_get_terraform_mapping_no_mapping(self, client: TestClient, setup_catalog):
        """Test getting Terraform mapping when none exists."""
        response = client.get("/catalog/resources/microsoft.network/networksecuritygroups/terraform")
        assert response.status_code == 200
        data = response.json()
        assert data["terraform_type"] is None

    def test_get_terraform_mapping_nonexistent_resource(self, client: TestClient, setup_catalog):
        """Test getting Terraform mapping for nonexistent resource."""
        response = client.get("/catalog/resources/nonexistent.type/resource/terraform")
        assert response.status_code == 404


class TestCatalogCategoriesEndpoint:
    """Test GET /catalog/categories endpoint."""

    def test_list_categories(self, client: TestClient, setup_catalog):
        """Test listing all categories."""
        response = client.get("/catalog/categories")
        assert response.status_code == 200
        data = response.json()
        categories = data["categories"]
        assert "compute" in categories
        assert "networking" in categories
        assert "storage" in categories
        assert "management" in categories
        assert "security" in categories
        assert "database" in categories
        assert "monitoring" in categories
        assert len(categories) == 7
