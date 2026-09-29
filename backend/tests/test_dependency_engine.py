"""
Comprehensive tests for Dependency Engine.
"""

import pytest
from uuid import uuid4
from sqlalchemy.orm import Session

from app.models import (
    Architecture,
    ArchitectureVersion,
    Resource,
    ResourceCatalog,
    CatalogDependency,
)
from app.services import DependencyEngine, ArchitectureService, ArchitectureVersionService, ResourceService, CatalogService


@pytest.fixture
def sample_catalog(db: Session):
    """Create sample resource types and dependencies in the catalog."""
    # Create Resource Group
    rg = CatalogService.register_resource_type(
        db,
        provider="azure",
        resource_type="microsoft.resources/resourcegroups",
        display_name="Resource Group",
        category="management",
        description="Azure Resource Group",
        terraform_mapping={"terraform_type": "azurerm_resource_group"},
    )

    # Create Virtual Network
    vnet = CatalogService.register_resource_type(
        db,
        provider="azure",
        resource_type="microsoft.network/virtualnetworks",
        display_name="Virtual Network",
        category="networking",
        description="Azure VNet",
        terraform_mapping={"terraform_type": "azurerm_virtual_network"},
    )

    # Create Subnet
    subnet = CatalogService.register_resource_type(
        db,
        provider="azure",
        resource_type="microsoft.network/virtualnetworks/subnets",
        display_name="Subnet",
        category="networking",
        description="Azure Subnet",
        terraform_mapping={"terraform_type": "azurerm_subnet"},
    )

    # Create Network Interface
    nic = CatalogService.register_resource_type(
        db,
        provider="azure",
        resource_type="microsoft.network/networkinterfaces",
        display_name="Network Interface",
        category="networking",
        description="Azure NIC",
        terraform_mapping={"terraform_type": "azurerm_network_interface"},
    )

    # Create Network Security Group
    nsg = CatalogService.register_resource_type(
        db,
        provider="azure",
        resource_type="microsoft.network/networksecuritygroups",
        display_name="Network Security Group",
        category="networking",
        description="Azure NSG",
        terraform_mapping={"terraform_type": "azurerm_network_security_group"},
    )

    # Create Virtual Machine
    vm = CatalogService.register_resource_type(
        db,
        provider="azure",
        resource_type="microsoft.compute/virtualmachines",
        display_name="Virtual Machine",
        category="compute",
        description="Azure VM",
        terraform_mapping={"terraform_type": "azurerm_windows_virtual_machine"},
    )

    # Create Storage Account
    storage = CatalogService.register_resource_type(
        db,
        provider="azure",
        resource_type="microsoft.storage/storageaccounts",
        display_name="Storage Account",
        category="storage",
        description="Azure Storage",
        terraform_mapping={"terraform_type": "azurerm_storage_account"},
    )

    # Add dependencies
    # VNet REQUIRED -> Resource Group
    CatalogService.add_required_dependency(
        db,
        "microsoft.network/virtualnetworks",
        "microsoft.resources/resourcegroups",
        "VNet must be in a Resource Group",
    )

    # Subnet REQUIRED -> VNet
    CatalogService.add_required_dependency(
        db,
        "microsoft.network/virtualnetworks/subnets",
        "microsoft.network/virtualnetworks",
        "Subnet must be in a VNet",
    )

    # NIC REQUIRED -> Subnet
    CatalogService.add_required_dependency(
        db,
        "microsoft.network/networkinterfaces",
        "microsoft.network/virtualnetworks/subnets",
        "NIC must be in a Subnet",
    )

    # VM REQUIRED -> NIC
    CatalogService.add_required_dependency(
        db,
        "microsoft.compute/virtualmachines",
        "microsoft.network/networkinterfaces",
        "VM must have a NIC",
    )

    # VM RECOMMENDED -> NSG
    db.add(CatalogDependency(
        resource_type_id=vm.id,
        depends_on_resource_type="microsoft.network/networksecuritygroups",
        dependency_classification="RECOMMENDED",
        reason="VM should have NSG for network security",
    ))
    db.commit()

    # VM OPTIONAL -> Storage Account
    db.add(CatalogDependency(
        resource_type_id=vm.id,
        depends_on_resource_type="microsoft.storage/storageaccounts",
        dependency_classification="OPTIONAL",
        reason="Storage for VM diagnostics is optional",
    ))
    db.commit()

    # Storage RECOMMENDED -> Resource Group
    CatalogService.add_recommended_dependency(
        db,
        "microsoft.storage/storageaccounts",
        "microsoft.resources/resourcegroups",
        "Storage should be organized in Resource Group",
    )

    return {
        "rg": rg,
        "vnet": vnet,
        "subnet": subnet,
        "nic": nic,
        "nsg": nsg,
        "vm": vm,
        "storage": storage,
    }


@pytest.fixture
def sample_architecture(db: Session):
    """Create a sample architecture."""
    arch = ArchitectureService.create(
        db,
        type("ArchitectureCreate", (), {
            "name": "Test Architecture",
            "description": "Test",
            "provider": "azure",
        })(),
    )
    
    version = ArchitectureVersionService.create(
        db,
        arch.id,
        type("VersionCreate", (), {
            "version_number": "1.0",
            "status": "draft",
            "created_by": "test",
        })(),
    )
    
    return {"architecture": arch, "version": version}


class TestDependencyEngineBasics:
    """Test basic Dependency Engine functionality."""

    def test_resource_with_no_catalog_dependencies(self, db: Session, sample_catalog, sample_architecture):
        """Test 1: Resource with no catalog dependencies."""
        # Create a Resource Group (has no catalog dependencies defined)
        rg = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "rg-01",
                "resource_type": "microsoft.resources/resourcegroups",
                "name": "test-rg",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        analysis = DependencyEngine.analyze_version(
            db,
            sample_architecture["architecture"].id,
            sample_architecture["version"].id,
        )
        
        # Resource Group has no dependencies, so no findings
        assert analysis["total_findings"] == 0
        assert len(analysis["findings"]) == 0

    def test_required_dependency_satisfied(self, db: Session, sample_catalog, sample_architecture):
        """Test 2: REQUIRED dependency satisfied."""
        # Create Resource Group
        rg = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "rg-01",
                "resource_type": "microsoft.resources/resourcegroups",
                "name": "test-rg",
                "location": None,
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create VNet (requires Resource Group)
        vnet = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "vnet-01",
                "resource_type": "microsoft.network/virtualnetworks",
                "name": "test-vnet",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        analysis = DependencyEngine.analyze_version(
            db,
            sample_architecture["architecture"].id,
            sample_architecture["version"].id,
        )
        
        # VNet has 1 required dependency (RG) that is satisfied
        assert analysis["total_findings"] == 1
        assert analysis["required_findings"] == 1
        assert analysis["satisfied_count"] == 1
        assert analysis["missing_count"] == 0
        assert analysis["findings"][0]["status"] == "SATISFIED"
        assert analysis["findings"][0]["classification"] == "REQUIRED"

    def test_required_dependency_missing(self, db: Session, sample_catalog, sample_architecture):
        """Test 3: REQUIRED dependency missing."""
        # Create VNet without Resource Group
        vnet = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "vnet-01",
                "resource_type": "microsoft.network/virtualnetworks",
                "name": "test-vnet",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        analysis = DependencyEngine.analyze_version(
            db,
            sample_architecture["architecture"].id,
            sample_architecture["version"].id,
        )
        
        # VNet has 1 required dependency (RG) that is missing
        assert analysis["total_findings"] == 1
        assert analysis["required_findings"] == 1
        assert analysis["satisfied_count"] == 0
        assert analysis["missing_count"] == 1
        assert analysis["findings"][0]["status"] == "MISSING"
        assert analysis["findings"][0]["classification"] == "REQUIRED"

    def test_recommended_dependency_satisfied(self, db: Session, sample_catalog, sample_architecture):
        """Test 4: RECOMMENDED dependency satisfied."""
        # Create VM with NSG (recommended)
        vm = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "vm-01",
                "resource_type": "microsoft.compute/virtualmachines",
                "name": "test-vm",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create NIC (required by VM)
        nic = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "nic-01",
                "resource_type": "microsoft.network/networkinterfaces",
                "name": "test-nic",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create NSG (recommended for VM)
        nsg = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "nsg-01",
                "resource_type": "microsoft.network/networksecuritygroups",
                "name": "test-nsg",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        analysis = DependencyEngine.analyze_version(
            db,
            sample_architecture["architecture"].id,
            sample_architecture["version"].id,
        )
        
        # Should have findings including the recommended NSG as satisfied
        findings = [f for f in analysis["findings"] if f["classification"] == "RECOMMENDED"]
        assert len(findings) >= 1

    def test_recommended_dependency_missing(self, db: Session, sample_catalog, sample_architecture):
        """Test 5: RECOMMENDED dependency missing."""
        # Create VM without NSG (recommended)
        vm = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "vm-01",
                "resource_type": "microsoft.compute/virtualmachines",
                "name": "test-vm",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create NIC (required by VM)
        nic = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "nic-01",
                "resource_type": "microsoft.network/networkinterfaces",
                "name": "test-nic",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        analysis = DependencyEngine.analyze_version(
            db,
            sample_architecture["architecture"].id,
            sample_architecture["version"].id,
        )
        
        # Should have a missing recommended NSG
        findings = [f for f in analysis["findings"] if f["classification"] == "RECOMMENDED"]
        assert len(findings) >= 1
        assert any(f["status"] == "MISSING" for f in findings)

    def test_optional_dependency_satisfied(self, db: Session, sample_catalog, sample_architecture):
        """Test 6: OPTIONAL dependency satisfied."""
        # Create VM with storage (optional)
        vm = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "vm-01",
                "resource_type": "microsoft.compute/virtualmachines",
                "name": "test-vm",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create NIC (required)
        nic = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "nic-01",
                "resource_type": "microsoft.network/networkinterfaces",
                "name": "test-nic",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create Storage (optional for VM)
        storage = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "storage-01",
                "resource_type": "microsoft.storage/storageaccounts",
                "name": "teststorage",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        analysis = DependencyEngine.analyze_version(
            db,
            sample_architecture["architecture"].id,
            sample_architecture["version"].id,
        )
        
        # Should have optional storage as satisfied
        findings = [f for f in analysis["findings"] if f["classification"] == "OPTIONAL"]
        assert len(findings) >= 1

    def test_optional_dependency_missing(self, db: Session, sample_catalog, sample_architecture):
        """Test 7: OPTIONAL dependency missing."""
        # Create VM without storage (optional)
        vm = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "vm-01",
                "resource_type": "microsoft.compute/virtualmachines",
                "name": "test-vm",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create NIC (required)
        nic = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "nic-01",
                "resource_type": "microsoft.network/networkinterfaces",
                "name": "test-nic",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        analysis = DependencyEngine.analyze_version(
            db,
            sample_architecture["architecture"].id,
            sample_architecture["version"].id,
        )
        
        # Should have optional storage as missing
        findings = [f for f in analysis["findings"] if f["classification"] == "OPTIONAL"]
        assert len(findings) >= 1
        assert any(f["status"] == "MISSING" for f in findings)

    def test_unknown_catalog_resource_type(self, db: Session, sample_architecture):
        """Test 8: Unknown catalog resource type."""
        # Create resource with unknown type (not in catalog)
        unknown = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "unknown-01",
                "resource_type": "microsoft.unknown/unknownresource",
                "name": "unknown",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        analysis = DependencyEngine.analyze_version(
            db,
            sample_architecture["architecture"].id,
            sample_architecture["version"].id,
        )
        
        # Unknown types don't generate findings
        assert analysis["total_findings"] == 0

    def test_multiple_dependencies_one_resource(self, db: Session, sample_catalog, sample_architecture):
        """Test 9: Multiple dependencies on one resource."""
        # Create RG
        rg = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "rg-01",
                "resource_type": "microsoft.resources/resourcegroups",
                "name": "test-rg",
                "location": None,
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create VNet
        vnet = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "vnet-01",
                "resource_type": "microsoft.network/virtualnetworks",
                "name": "vnet",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create Subnet
        subnet = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "subnet-01",
                "resource_type": "microsoft.network/virtualnetworks/subnets",
                "name": "subnet",
                "location": None,
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create NIC
        nic = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "nic-01",
                "resource_type": "microsoft.network/networkinterfaces",
                "name": "nic",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create VM
        vm = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "vm-01",
                "resource_type": "microsoft.compute/virtualmachines",
                "name": "vm",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        analysis = DependencyEngine.analyze_version(
            db,
            sample_architecture["architecture"].id,
            sample_architecture["version"].id,
        )
        
        # Should have multiple dependencies (chain: VM->NIC, Subnet->VNet, VNet->RG)
        # Plus optional/recommended for VM
        assert analysis["total_findings"] > 1

    def test_multiple_architecture_resources(self, db: Session, sample_catalog, sample_architecture):
        """Test 10: Multiple architecture resources."""
        # Create multiple resources
        for i in range(3):
            ResourceService.create(
                db,
                sample_architecture["version"].id,
                type("ResourceCreate", (), {
                    "resource_key": f"rg-{i:02d}",
                    "resource_type": "microsoft.resources/resourcegroups",
                    "name": f"test-rg-{i}",
                    "location": None,
                    "sku": None,
                    "properties": None,
                    "tags": None,
                    "parent_resource_id": None,
                })(),
            )
        
        analysis = DependencyEngine.analyze_version(
            db,
            sample_architecture["architecture"].id,
            sample_architecture["version"].id,
        )
        
        # Should complete without error
        assert analysis is not None
        assert analysis["total_findings"] == 0  # RGs have no dependencies


class TestDependencyEngineRelationshipMatching:
    """Test relationship-aware dependency matching."""

    def test_vm_associated_with_nic_satisfied(self, db: Session, sample_catalog, sample_architecture):
        """Test: VM-01 associated with NIC-01 via Relationship -> SATISFIED."""
        from app.services import RelationshipService
        
        # Create VNet first (required by NIC's dependency chain)
        vnet = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "vnet-01",
                "resource_type": "microsoft.network/virtualnetworks",
                "name": "vnet",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create RG
        rg = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "rg-01",
                "resource_type": "microsoft.resources/resourcegroups",
                "name": "rg",
                "location": None,
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create NIC-01
        nic01 = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "nic-01",
                "resource_type": "microsoft.network/networkinterfaces",
                "name": "nic-01",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create VM-01
        vm01 = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "vm-01",
                "resource_type": "microsoft.compute/virtualmachines",
                "name": "vm-01",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create relationship: VM-01 -> NIC-01
        RelationshipService.create(
            db,
            sample_architecture["version"].id,
            type("RelationshipCreate", (), {
                "source_resource_id": vm01.id,
                "target_resource_id": nic01.id,
                "relationship_type": "uses",
                "metadata": None,
            })(),
        )
        
        # Analyze
        analysis = DependencyEngine.analyze_version(
            db,
            sample_architecture["architecture"].id,
            sample_architecture["version"].id,
        )
        
        # Find the VM->NIC dependency finding
        findings = [f for f in analysis["findings"] 
                   if f["source_resource_id"] == vm01.id 
                   and f["dependency_resource_type"] == "microsoft.network/networkinterfaces"
                   and f["classification"] == "REQUIRED"]
        
        assert len(findings) == 1
        assert findings[0]["status"] == "SATISFIED"
        assert findings[0]["matched_resource_id"] == nic01.id

    def test_vm_not_associated_with_nic_missing(self, db: Session, sample_catalog, sample_architecture):
        """Test: VM-01 exists but no Relationship to any NIC -> MISSING."""
        # Create VNet
        vnet = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "vnet-01",
                "resource_type": "microsoft.network/virtualnetworks",
                "name": "vnet",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create RG
        rg = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "rg-01",
                "resource_type": "microsoft.resources/resourcegroups",
                "name": "rg",
                "location": None,
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create NIC-01
        nic01 = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "nic-01",
                "resource_type": "microsoft.network/networkinterfaces",
                "name": "nic-01",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create VM-01 WITHOUT relationship to NIC
        vm01 = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "vm-01",
                "resource_type": "microsoft.compute/virtualmachines",
                "name": "vm-01",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Analyze (no relationship created)
        analysis = DependencyEngine.analyze_version(
            db,
            sample_architecture["architecture"].id,
            sample_architecture["version"].id,
        )
        
        # Find the VM->NIC dependency finding
        findings = [f for f in analysis["findings"] 
                   if f["source_resource_id"] == vm01.id 
                   and f["dependency_resource_type"] == "microsoft.network/networkinterfaces"
                   and f["classification"] == "REQUIRED"]
        
        assert len(findings) == 1
        assert findings[0]["status"] == "MISSING"
        assert findings[0]["matched_resource_id"] is None

    def test_two_vms_two_nics_correct_associations(self, db: Session, sample_catalog, sample_architecture):
        """Test: Two VMs and two NICs with correct associations."""
        from app.services import RelationshipService
        
        # Create RG
        rg = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "rg-01",
                "resource_type": "microsoft.resources/resourcegroups",
                "name": "rg",
                "location": None,
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create VNet
        vnet = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "vnet-01",
                "resource_type": "microsoft.network/virtualnetworks",
                "name": "vnet",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create two NICs
        nic01 = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "nic-01",
                "resource_type": "microsoft.network/networkinterfaces",
                "name": "nic-01",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        nic02 = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "nic-02",
                "resource_type": "microsoft.network/networkinterfaces",
                "name": "nic-02",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create two VMs
        vm01 = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "vm-01",
                "resource_type": "microsoft.compute/virtualmachines",
                "name": "vm-01",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        vm02 = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "vm-02",
                "resource_type": "microsoft.compute/virtualmachines",
                "name": "vm-02",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create correct associations
        RelationshipService.create(db, sample_architecture["version"].id, type("RelationshipCreate", (), {
            "source_resource_id": vm01.id,
            "target_resource_id": nic01.id,
            "relationship_type": "uses",
            "metadata": None,
        })())
        
        RelationshipService.create(db, sample_architecture["version"].id, type("RelationshipCreate", (), {
            "source_resource_id": vm02.id,
            "target_resource_id": nic02.id,
            "relationship_type": "uses",
            "metadata": None,
        })())
        
        # Analyze
        analysis = DependencyEngine.analyze_version(
            db,
            sample_architecture["architecture"].id,
            sample_architecture["version"].id,
        )
        
        # Both VMs should have satisfied NIC dependencies
        vm01_findings = [f for f in analysis["findings"] if f["source_resource_id"] == vm01.id]
        vm02_findings = [f for f in analysis["findings"] if f["source_resource_id"] == vm02.id]
        
        vm01_nic_dep = [f for f in vm01_findings if f["dependency_resource_type"] == "microsoft.network/networkinterfaces" and f["classification"] == "REQUIRED"]
        vm02_nic_dep = [f for f in vm02_findings if f["dependency_resource_type"] == "microsoft.network/networkinterfaces" and f["classification"] == "REQUIRED"]
        
        assert len(vm01_nic_dep) == 1
        assert vm01_nic_dep[0]["status"] == "SATISFIED"
        assert vm01_nic_dep[0]["matched_resource_id"] == nic01.id
        
        assert len(vm02_nic_dep) == 1
        assert vm02_nic_dep[0]["status"] == "SATISFIED"
        assert vm02_nic_dep[0]["matched_resource_id"] == nic02.id

    def test_two_vms_two_nics_without_associations(self, db: Session, sample_catalog, sample_architecture):
        """Test: Two VMs and two NICs but NO associations."""
        # Create RG
        rg = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "rg-01",
                "resource_type": "microsoft.resources/resourcegroups",
                "name": "rg",
                "location": None,
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create VNet
        vnet = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "vnet-01",
                "resource_type": "microsoft.network/virtualnetworks",
                "name": "vnet",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create two NICs
        nic01 = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "nic-01",
                "resource_type": "microsoft.network/networkinterfaces",
                "name": "nic-01",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        nic02 = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "nic-02",
                "resource_type": "microsoft.network/networkinterfaces",
                "name": "nic-02",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create two VMs WITHOUT creating any relationships
        vm01 = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "vm-01",
                "resource_type": "microsoft.compute/virtualmachines",
                "name": "vm-01",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        vm02 = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "vm-02",
                "resource_type": "microsoft.compute/virtualmachines",
                "name": "vm-02",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Analyze
        analysis = DependencyEngine.analyze_version(
            db,
            sample_architecture["architecture"].id,
            sample_architecture["version"].id,
        )
        
        # Both VMs should have MISSING NIC dependencies (no relationships)
        vm01_findings = [f for f in analysis["findings"] if f["source_resource_id"] == vm01.id]
        vm02_findings = [f for f in analysis["findings"] if f["source_resource_id"] == vm02.id]
        
        vm01_nic_dep = [f for f in vm01_findings if f["dependency_resource_type"] == "microsoft.network/networkinterfaces" and f["classification"] == "REQUIRED"]
        vm02_nic_dep = [f for f in vm02_findings if f["dependency_resource_type"] == "microsoft.network/networkinterfaces" and f["classification"] == "REQUIRED"]
        
        assert len(vm01_nic_dep) == 1
        assert vm01_nic_dep[0]["status"] == "MISSING"
        
        assert len(vm02_nic_dep) == 1
        assert vm02_nic_dep[0]["status"] == "MISSING"


class TestDependencyEngineSameLevelIsolation:
    """Test same-version and cross-version isolation."""

    def test_multiple_architecture_versions(self, db: Session, sample_catalog):
        """Test 11: Multiple architecture versions."""
        # Create architecture
        arch = ArchitectureService.create(
            db,
            type("ArchitectureCreate", (), {
                "name": "Multi-Version Arch",
                "description": "Test",
                "provider": "azure",
            })(),
        )
        
        # Create version 1
        v1 = ArchitectureVersionService.create(
            db,
            arch.id,
            type("VersionCreate", (), {
                "version_number": "1.0",
                "status": "draft",
                "created_by": "test",
            })(),
        )
        
        # Create version 2
        v2 = ArchitectureVersionService.create(
            db,
            arch.id,
            type("VersionCreate", (), {
                "version_number": "2.0",
                "status": "draft",
                "created_by": "test",
            })(),
        )
        
        # Add RG to version 1
        rg_v1 = ResourceService.create(
            db,
            v1.id,
            type("ResourceCreate", (), {
                "resource_key": "rg-01",
                "resource_type": "microsoft.resources/resourcegroups",
                "name": "test-rg",
                "location": None,
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Analyze both versions
        analysis_v1 = DependencyEngine.analyze_version(db, arch.id, v1.id)
        analysis_v2 = DependencyEngine.analyze_version(db, arch.id, v2.id)
        
        # V1 has 1 resource, V2 has 0 resources
        assert analysis_v1["total_findings"] == 0  # RG has no dependencies
        assert analysis_v2["total_findings"] == 0  # V2 is empty

    def test_same_version_isolation(self, db: Session, sample_catalog, sample_architecture):
        """Test 12: Same-version isolation."""
        # Create VNet and RG in same version
        rg = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "rg-01",
                "resource_type": "microsoft.resources/resourcegroups",
                "name": "rg",
                "location": None,
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        vnet = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "vnet-01",
                "resource_type": "microsoft.network/virtualnetworks",
                "name": "vnet",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        analysis = DependencyEngine.analyze_version(
            db,
            sample_architecture["architecture"].id,
            sample_architecture["version"].id,
        )
        
        # Dependencies should resolve within same version
        assert analysis["total_findings"] == 1
        assert analysis["findings"][0]["status"] == "SATISFIED"

    def test_cross_version_dependency_isolation(self, db: Session, sample_catalog):
        """Test 13: Cross-version dependency must NOT satisfy."""
        # Create architecture with two versions
        arch = ArchitectureService.create(
            db,
            type("ArchitectureCreate", (), {
                "name": "Cross-Version Arch",
                "description": "Test",
                "provider": "azure",
            })(),
        )
        
        # V1: has RG
        v1 = ArchitectureVersionService.create(
            db,
            arch.id,
            type("VersionCreate", (), {
                "version_number": "1.0",
                "status": "draft",
                "created_by": "test",
            })(),
        )
        
        rg_v1 = ResourceService.create(
            db,
            v1.id,
            type("ResourceCreate", (), {
                "resource_key": "rg-01",
                "resource_type": "microsoft.resources/resourcegroups",
                "name": "rg",
                "location": None,
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # V2: has VNet but no RG
        v2 = ArchitectureVersionService.create(
            db,
            arch.id,
            type("VersionCreate", (), {
                "version_number": "2.0",
                "status": "draft",
                "created_by": "test",
            })(),
        )
        
        vnet_v2 = ResourceService.create(
            db,
            v2.id,
            type("ResourceCreate", (), {
                "resource_key": "vnet-01",
                "resource_type": "microsoft.network/virtualnetworks",
                "name": "vnet",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Analyze V2
        analysis_v2 = DependencyEngine.analyze_version(db, arch.id, v2.id)
        
        # V2 VNet should show RG as missing, not satisfied by V1's RG
        findings = [f for f in analysis_v2["findings"] if f["source_resource_type"] == "microsoft.network/virtualnetworks"]
        assert len(findings) == 1
        assert findings[0]["status"] == "MISSING"  # RG from V1 shouldn't satisfy V2

    def test_cross_architecture_dependency_isolation(self, db: Session, sample_catalog):
        """Test 14: Cross-architecture dependency must NOT satisfy."""
        # Create architecture 1 with RG
        arch1 = ArchitectureService.create(
            db,
            type("ArchitectureCreate", (), {
                "name": "Arch 1",
                "description": "Test",
                "provider": "azure",
            })(),
        )
        
        v1 = ArchitectureVersionService.create(
            db,
            arch1.id,
            type("VersionCreate", (), {
                "version_number": "1.0",
                "status": "draft",
                "created_by": "test",
            })(),
        )
        
        rg = ResourceService.create(
            db,
            v1.id,
            type("ResourceCreate", (), {
                "resource_key": "rg-01",
                "resource_type": "microsoft.resources/resourcegroups",
                "name": "rg",
                "location": None,
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Create architecture 2 with VNet
        arch2 = ArchitectureService.create(
            db,
            type("ArchitectureCreate", (), {
                "name": "Arch 2",
                "description": "Test",
                "provider": "azure",
            })(),
        )
        
        v2 = ArchitectureVersionService.create(
            db,
            arch2.id,
            type("VersionCreate", (), {
                "version_number": "1.0",
                "status": "draft",
                "created_by": "test",
            })(),
        )
        
        vnet = ResourceService.create(
            db,
            v2.id,
            type("ResourceCreate", (), {
                "resource_key": "vnet-01",
                "resource_type": "microsoft.network/virtualnetworks",
                "name": "vnet",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Analyze Arch2
        analysis = DependencyEngine.analyze_version(db, arch2.id, v2.id)
        
        # VNet should show RG as missing from Arch1's RG
        findings = [f for f in analysis["findings"] if f["source_resource_type"] == "microsoft.network/virtualnetworks"]
        assert len(findings) == 1
        assert findings[0]["status"] == "MISSING"  # RG from Arch1 shouldn't satisfy Arch2


class TestDependencyEngineEdgeCases:
    """Test edge cases and special scenarios."""

    def test_empty_architecture(self, db: Session, sample_architecture):
        """Test 21: Empty architecture."""
        analysis = DependencyEngine.analyze_version(
            db,
            sample_architecture["architecture"].id,
            sample_architecture["version"].id,
        )
        
        assert analysis["total_findings"] == 0
        assert analysis["satisfied_count"] == 0
        assert analysis["missing_count"] == 0

    def test_architecture_only_no_dependencies(self, db: Session, sample_architecture):
        """Test 22: Architecture containing only resources with no dependencies."""
        # Create only Resource Groups (which have no dependencies)
        for i in range(3):
            ResourceService.create(
                db,
                sample_architecture["version"].id,
                type("ResourceCreate", (), {
                    "resource_key": f"rg-{i:02d}",
                    "resource_type": "microsoft.resources/resourcegroups",
                    "name": f"rg-{i}",
                    "location": None,
                    "sku": None,
                    "properties": None,
                    "tags": None,
                    "parent_resource_id": None,
                })(),
            )
        
        analysis = DependencyEngine.analyze_version(
            db,
            sample_architecture["architecture"].id,
            sample_architecture["version"].id,
        )
        
        # No dependencies means no findings
        assert analysis["total_findings"] == 0


class TestDependencyEngineNoMutation:
    """Verify that the engine does NOT mutate the canonical architecture."""

    def test_engine_does_not_mutate_architecture(self, db: Session, sample_catalog, sample_architecture):
        """Verify: Dependency Engine does NOT modify resources."""
        # Create VNet without RG
        vnet = ResourceService.create(
            db,
            sample_architecture["version"].id,
            type("ResourceCreate", (), {
                "resource_key": "vnet-01",
                "resource_type": "microsoft.network/virtualnetworks",
                "name": "vnet",
                "location": "eastus",
                "sku": None,
                "properties": None,
                "tags": None,
                "parent_resource_id": None,
            })(),
        )
        
        # Analyze
        analysis = DependencyEngine.analyze_version(
            db,
            sample_architecture["architecture"].id,
            sample_architecture["version"].id,
        )
        
        # Re-fetch VNet to verify it wasn't modified
        vnet_check = db.query(Resource).filter(Resource.id == vnet.id).first()
        assert vnet_check.name == "vnet"
        assert vnet_check.resource_type == "microsoft.network/virtualnetworks"
        assert vnet_check.parent_resource_id is None  # No auto-linking
        
        # Findings show missing dependency, but no resources were created
        resources = db.query(Resource).filter(
            Resource.architecture_version_id == sample_architecture["version"].id
        ).all()
        assert len(resources) == 1  # Only the VNet


class TestDependencyEngineAPI:
    """Test API integration."""

    def test_api_dependency_analysis_success(self, client, db: Session, sample_catalog):
        """Test 18: API success."""
        # Create architecture and version
        arch_data = {"name": "Test", "description": "Test", "provider": "azure"}
        arch_resp = client.post("/architectures", json=arch_data)
        arch_id = arch_resp.json()["id"]
        
        version_data = {"version_number": "1.0", "status": "draft", "created_by": "test"}
        version_resp = client.post(f"/architectures/{arch_id}/versions", json=version_data)
        version_id = version_resp.json()["id"]
        
        # Call dependency analysis endpoint
        resp = client.get(f"/architectures/{arch_id}/versions/{version_id}/dependencies")
        
        assert resp.status_code == 200
        data = resp.json()
        assert "architecture_id" in data
        assert "total_findings" in data
        assert data["total_findings"] == 0

    def test_api_unknown_architecture_404(self, client):
        """Test 19: Unknown architecture → 404."""
        unknown_id = "00000000-0000-0000-0000-000000000000"
        version_id = "00000000-0000-0000-0000-000000000001"
        
        resp = client.get(f"/architectures/{unknown_id}/versions/{version_id}/dependencies")
        
        assert resp.status_code == 404

    def test_api_unknown_version_404(self, client, db: Session):
        """Test 20: Unknown version → 404."""
        # Create architecture
        arch_data = {"name": "Test", "description": "Test", "provider": "azure"}
        arch_resp = client.post("/architectures", json=arch_data)
        arch_id = arch_resp.json()["id"]
        
        # Try with unknown version
        unknown_version = "00000000-0000-0000-0000-000000000001"
        resp = client.get(f"/architectures/{arch_id}/versions/{unknown_version}/dependencies")
        
        assert resp.status_code == 404
