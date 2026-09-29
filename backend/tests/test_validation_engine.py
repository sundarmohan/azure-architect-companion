"""
Comprehensive tests for the ValidationEngine.

Test categories:
1. Resource validation (type, identity, duplicates)
2. Hierarchy validation (using CatalogHierarchy)
3. Relationship validation
4. Dependency validation (consuming M3 output)
5. Overall status aggregation
6. Version isolation
7. API endpoint
"""

import pytest
from uuid import uuid4
from sqlalchemy.orm import Session

from app.models import (
    Architecture,
    ArchitectureVersion,
    Resource,
    Relationship,
    ResourceCatalog,
    CatalogDependency,
    CatalogHierarchy,
)
from app.services import ValidationEngine, DependencyEngine
from app.schemas import ArchitectureValidationResponse


# ==================== TEST FIXTURES ====================


@pytest.fixture
def architecture(db: Session):
    """Create a test architecture."""
    arch = Architecture(
        name="Test Architecture",
        description="Test architecture for validation",
        provider="azure",
    )
    db.add(arch)
    db.commit()
    db.refresh(arch)
    return arch


@pytest.fixture
def architecture_version(db: Session, architecture: Architecture):
    """Create a test architecture version."""
    version = ArchitectureVersion(
        architecture_id=architecture.id,
        version_number="1.0",
        status="draft",
        created_by="test",
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


@pytest.fixture
def resource_group_catalog(db: Session):
    """Create Resource Group in catalog."""
    catalog = ResourceCatalog(
        provider="azure",
        resource_type="microsoft.resources/resourcegroups",
        display_name="Resource Group",
        category="Infrastructure",
        enabled=True,
    )
    db.add(catalog)
    db.commit()
    db.refresh(catalog)
    return catalog


@pytest.fixture
def vnet_catalog(db: Session):
    """Create VNet in catalog."""
    catalog = ResourceCatalog(
        provider="azure",
        resource_type="microsoft.network/virtualnetworks",
        display_name="Virtual Network",
        category="Networking",
        enabled=True,
    )
    db.add(catalog)
    db.commit()
    db.refresh(catalog)
    return catalog


@pytest.fixture
def subnet_catalog(db: Session):
    """Create Subnet in catalog."""
    catalog = ResourceCatalog(
        provider="azure",
        resource_type="microsoft.network/virtualnetworks/subnets",
        display_name="Subnet",
        category="Networking",
        enabled=True,
    )
    db.add(catalog)
    db.commit()
    db.refresh(catalog)
    return catalog


@pytest.fixture
def nic_catalog(db: Session):
    """Create Network Interface in catalog."""
    catalog = ResourceCatalog(
        provider="azure",
        resource_type="microsoft.network/networkinterfaces",
        display_name="Network Interface",
        category="Networking",
        enabled=True,
    )
    db.add(catalog)
    db.commit()
    db.refresh(catalog)
    return catalog


@pytest.fixture
def vm_catalog(db: Session):
    """Create Virtual Machine in catalog."""
    catalog = ResourceCatalog(
        provider="azure",
        resource_type="microsoft.compute/virtualmachines",
        display_name="Virtual Machine",
        category="Compute",
        enabled=True,
    )
    db.add(catalog)
    db.commit()
    db.refresh(catalog)
    return catalog


@pytest.fixture
def setup_hierarchy(db: Session, resource_group_catalog, vnet_catalog, subnet_catalog):
    """Setup valid hierarchy relationships."""
    # ResourceGroup can contain VNet
    hierarchy1 = CatalogHierarchy(
        parent_resource_type_id=resource_group_catalog.id,
        child_resource_type_id=vnet_catalog.id,
        description="ResourceGroup contains VNet",
    )
    db.add(hierarchy1)
    
    # VNet can contain Subnet
    hierarchy2 = CatalogHierarchy(
        parent_resource_type_id=vnet_catalog.id,
        child_resource_type_id=subnet_catalog.id,
        description="VNet contains Subnet",
    )
    db.add(hierarchy2)
    db.commit()


@pytest.fixture
def setup_dependencies(db: Session, vm_catalog, nic_catalog):
    """Setup VM requires NIC dependency."""
    # VM requires NIC
    dependency = CatalogDependency(
        resource_type_id=vm_catalog.id,
        depends_on_resource_type="microsoft.network/networkinterfaces",
        dependency_classification="REQUIRED",
        reason="VM must have at least one NIC",
    )
    db.add(dependency)
    db.commit()


# ==================== TEST CASES ====================


class TestValidationEngineBasics:
    """Basic validation tests."""
    
    def test_empty_architecture_valid(self, db: Session, architecture_version):
        """Test: Empty architecture is VALID."""
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        assert result["status"] == "VALID"
        assert result["error_count"] == 0
        assert result["total_findings"] == 0
    
    def test_valid_resource_type_no_errors(self, db: Session, architecture_version, vm_catalog):
        """Test: Resource with valid type in catalog is VALID."""
        vm = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="vm-01",
            resource_type="microsoft.compute/virtualmachines",
            name="Test VM",
            location="eastus",
        )
        db.add(vm)
        db.commit()
        
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        assert result["status"] == "VALID"
        assert result["error_count"] == 0
    
    def test_unknown_resource_type_error(self, db: Session, architecture_version):
        """Test: Unknown resource type generates ERROR."""
        resource = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="unknown-01",
            resource_type="microsoft.unknown/unknowntype",
            name="Unknown Resource",
            location="eastus",
        )
        db.add(resource)
        db.commit()
        
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        assert result["status"] == "INVALID"
        assert result["error_count"] == 1
        
        finding = result["findings"][0]
        assert finding["code"] == "RESOURCE_TYPE_NOT_IN_CATALOG"
        assert finding["severity"] == "ERROR"
    
    def test_duplicate_resource_key_error(self, db: Session, architecture_version, vm_catalog):
        """Test: Duplicate resource keys generate ERROR."""
        vm1 = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="vm-01",
            resource_type="microsoft.compute/virtualmachines",
            name="VM 1",
            location="eastus",
        )
        vm2 = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="vm-01",  # Duplicate key
            resource_type="microsoft.compute/virtualmachines",
            name="VM 2",
            location="eastus",
        )
        db.add_all([vm1, vm2])
        db.commit()
        
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        assert result["status"] == "INVALID"
        assert any(f["code"] == "DUPLICATE_RESOURCE_KEY" for f in result["findings"])
    
    def test_empty_resource_type_error(self, db: Session, architecture_version):
        """Test: Empty resource type generates ERROR."""
        resource = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="bad-01",
            resource_type="",  # Empty
            name="Bad Resource",
            location="eastus",
        )
        db.add(resource)
        db.commit()
        
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        assert result["status"] == "INVALID"
        assert any(f["code"] == "INVALID_RESOURCE_TYPE" for f in result["findings"])
    
    def test_missing_resource_name_error(self, db: Session, architecture_version, vm_catalog):
        """Test: Missing resource name generates ERROR."""
        resource = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="vm-01",
            resource_type="microsoft.compute/virtualmachines",
            name="",  # Missing name
            location="eastus",
        )
        db.add(resource)
        db.commit()
        
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        assert result["status"] == "INVALID"
        assert any(f["code"] == "RESOURCE_MISSING_NAME" for f in result["findings"])


class TestValidationEngineHierarchy:
    """Hierarchy validation tests."""
    
    def test_valid_rg_vnet_hierarchy(
        self, db: Session, architecture_version, resource_group_catalog, vnet_catalog, setup_hierarchy
    ):
        """Test: Valid ResourceGroup -> VNet hierarchy is VALID."""
        rg = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="rg-01",
            resource_type="microsoft.resources/resourcegroups",
            name="Test RG",
            location="eastus",
        )
        db.add(rg)
        db.commit()
        
        vnet = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="vnet-01",
            resource_type="microsoft.network/virtualnetworks",
            name="Test VNet",
            location="eastus",
            parent_resource_id=rg.id,
        )
        db.add(vnet)
        db.commit()
        
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        assert result["status"] == "VALID"
        assert result["error_count"] == 0
    
    def test_valid_vnet_subnet_hierarchy(
        self, db: Session, architecture_version, vnet_catalog, subnet_catalog, setup_hierarchy
    ):
        """Test: Valid VNet -> Subnet hierarchy is VALID."""
        vnet = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="vnet-01",
            resource_type="microsoft.network/virtualnetworks",
            name="Test VNet",
            location="eastus",
        )
        db.add(vnet)
        db.commit()
        
        subnet = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="subnet-01",
            resource_type="microsoft.network/virtualnetworks/subnets",
            name="Test Subnet",
            location="eastus",
            parent_resource_id=vnet.id,
        )
        db.add(subnet)
        db.commit()
        
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        assert result["status"] == "VALID"
        assert result["error_count"] == 0
    
    def test_invalid_hierarchy_vm_under_subnet(
        self, db: Session, architecture_version, subnet_catalog, vm_catalog, setup_hierarchy
    ):
        """Test: Invalid VM under Subnet generates ERROR."""
        subnet = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="subnet-01",
            resource_type="microsoft.network/virtualnetworks/subnets",
            name="Test Subnet",
            location="eastus",
        )
        db.add(subnet)
        db.commit()
        
        vm = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="vm-01",
            resource_type="microsoft.compute/virtualmachines",
            name="Test VM",
            location="eastus",
            parent_resource_id=subnet.id,  # Invalid: VM under Subnet
        )
        db.add(vm)
        db.commit()
        
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        assert result["status"] == "INVALID"
        assert any(f["code"] == "INVALID_PARENT_TYPE" for f in result["findings"])
    
    def test_invalid_parent_not_exists(
        self, db: Session, architecture_version, vm_catalog
    ):
        """Test: Parent that doesn't exist generates ERROR."""
        fake_parent_id = uuid4()
        
        vm = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="vm-01",
            resource_type="microsoft.compute/virtualmachines",
            name="Test VM",
            location="eastus",
            parent_resource_id=fake_parent_id,  # Non-existent parent
        )
        db.add(vm)
        db.commit()
        
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        assert result["status"] == "INVALID"
        assert any(f["code"] == "INVALID_HIERARCHY_PARENT" for f in result["findings"])


class TestValidationEngineRelationships:
    """Relationship validation tests."""
    
    def test_valid_relationship(
        self, db: Session, architecture_version, vm_catalog, nic_catalog
    ):
        """Test: Valid relationship between resources is VALID."""
        vm = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="vm-01",
            resource_type="microsoft.compute/virtualmachines",
            name="Test VM",
            location="eastus",
        )
        nic = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="nic-01",
            resource_type="microsoft.network/networkinterfaces",
            name="Test NIC",
            location="eastus",
        )
        db.add_all([vm, nic])
        db.commit()
        
        rel = Relationship(
            architecture_version_id=architecture_version.id,
            source_resource_id=vm.id,
            target_resource_id=nic.id,
            relationship_type="uses",
        )
        db.add(rel)
        db.commit()
        
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        assert result["status"] == "VALID"
    
    def test_invalid_relationship_missing_source(
        self, db: Session, architecture_version, nic_catalog
    ):
        """Test: Relationship with non-existent source generates ERROR."""
        fake_source_id = uuid4()
        
        nic = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="nic-01",
            resource_type="microsoft.network/networkinterfaces",
            name="Test NIC",
            location="eastus",
        )
        db.add(nic)
        db.commit()
        
        rel = Relationship(
            architecture_version_id=architecture_version.id,
            source_resource_id=fake_source_id,  # Non-existent
            target_resource_id=nic.id,
            relationship_type="uses",
        )
        db.add(rel)
        db.commit()
        
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        assert result["status"] == "INVALID"
        assert any(f["code"] == "INVALID_RELATIONSHIP_SOURCE" for f in result["findings"])
    
    def test_invalid_relationship_missing_target(
        self, db: Session, architecture_version, vm_catalog
    ):
        """Test: Relationship with non-existent target generates ERROR."""
        fake_target_id = uuid4()
        
        vm = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="vm-01",
            resource_type="microsoft.compute/virtualmachines",
            name="Test VM",
            location="eastus",
        )
        db.add(vm)
        db.commit()
        
        rel = Relationship(
            architecture_version_id=architecture_version.id,
            source_resource_id=vm.id,
            target_resource_id=fake_target_id,  # Non-existent
            relationship_type="uses",
        )
        db.add(rel)
        db.commit()
        
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        assert result["status"] == "INVALID"
        assert any(f["code"] == "INVALID_RELATIONSHIP_TARGET" for f in result["findings"])
    
    def test_self_referencing_relationship_error(
        self, db: Session, architecture_version, vm_catalog
    ):
        """Test: Self-referencing relationship generates ERROR."""
        vm = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="vm-01",
            resource_type="microsoft.compute/virtualmachines",
            name="Test VM",
            location="eastus",
        )
        db.add(vm)
        db.commit()
        
        rel = Relationship(
            architecture_version_id=architecture_version.id,
            source_resource_id=vm.id,
            target_resource_id=vm.id,  # Self-referencing
            relationship_type="uses",
        )
        db.add(rel)
        db.commit()
        
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        assert result["status"] == "INVALID"
        assert any(f["code"] == "SELF_REFERENCING_RELATIONSHIP" for f in result["findings"])
    
    def test_empty_relationship_type_error(
        self, db: Session, architecture_version, vm_catalog, nic_catalog
    ):
        """Test: Empty relationship type generates ERROR."""
        vm = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="vm-01",
            resource_type="microsoft.compute/virtualmachines",
            name="Test VM",
            location="eastus",
        )
        nic = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="nic-01",
            resource_type="microsoft.network/networkinterfaces",
            name="Test NIC",
            location="eastus",
        )
        db.add_all([vm, nic])
        db.commit()
        
        rel = Relationship(
            architecture_version_id=architecture_version.id,
            source_resource_id=vm.id,
            target_resource_id=nic.id,
            relationship_type="",  # Empty
        )
        db.add(rel)
        db.commit()
        
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        assert result["status"] == "INVALID"
        assert any(f["code"] == "INVALID_RELATIONSHIP_TYPE" for f in result["findings"])


class TestValidationEngineDependencies:
    """Dependency validation tests."""
    
    def test_required_dependency_satisfied(
        self, db: Session, architecture_version, vm_catalog, nic_catalog, setup_dependencies
    ):
        """Test: REQUIRED dependency that is satisfied is VALID."""
        vm = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="vm-01",
            resource_type="microsoft.compute/virtualmachines",
            name="Test VM",
            location="eastus",
        )
        nic = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="nic-01",
            resource_type="microsoft.network/networkinterfaces",
            name="Test NIC",
            location="eastus",
        )
        db.add_all([vm, nic])
        db.commit()
        
        # Create relationship (dependency satisfaction)
        rel = Relationship(
            architecture_version_id=architecture_version.id,
            source_resource_id=vm.id,
            target_resource_id=nic.id,
            relationship_type="uses",
        )
        db.add(rel)
        db.commit()
        
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        assert result["status"] == "VALID"
        assert result["error_count"] == 0
    
    def test_required_dependency_missing_error(
        self, db: Session, architecture_version, vm_catalog, nic_catalog, setup_dependencies
    ):
        """Test: REQUIRED dependency that is missing generates ERROR."""
        vm = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="vm-01",
            resource_type="microsoft.compute/virtualmachines",
            name="Test VM",
            location="eastus",
        )
        # Note: No NIC created
        db.add(vm)
        db.commit()
        
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        assert result["status"] == "INVALID"
        assert any(f["code"] == "REQUIRED_DEPENDENCY_MISSING" for f in result["findings"])
    
    def test_recommended_dependency_missing_warning(
        self, db: Session, architecture_version, vm_catalog, nic_catalog
    ):
        """Test: RECOMMENDED dependency missing generates WARNING."""
        # Setup recommended dependency
        recommended_dep = CatalogDependency(
            resource_type_id=vm_catalog.id,
            depends_on_resource_type="microsoft.insights/components",  # App Insights
            dependency_classification="RECOMMENDED",
            reason="Monitoring is recommended",
        )
        db.add(recommended_dep)
        db.commit()
        
        vm = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="vm-01",
            resource_type="microsoft.compute/virtualmachines",
            name="Test VM",
            location="eastus",
        )
        db.add(vm)
        db.commit()
        
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        # Should be VALID (no ERRORs) but have WARNINGs
        assert result["status"] == "VALID"
        assert result["warning_count"] >= 1
        assert any(f["code"] == "RECOMMENDED_DEPENDENCY_MISSING" for f in result["findings"])
    
    def test_optional_dependency_missing_info(
        self, db: Session, architecture_version, vm_catalog
    ):
        """Test: OPTIONAL dependency missing is INFO or no finding."""
        # Setup optional dependency
        optional_dep = CatalogDependency(
            resource_type_id=vm_catalog.id,
            depends_on_resource_type="microsoft.compute/backupvaults",
            dependency_classification="OPTIONAL",
            reason="Backup is optional",
        )
        db.add(optional_dep)
        db.commit()
        
        vm = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="vm-01",
            resource_type="microsoft.compute/virtualmachines",
            name="Test VM",
            location="eastus",
        )
        db.add(vm)
        db.commit()
        
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        # Should be VALID
        assert result["status"] == "VALID"
        assert result["error_count"] == 0


class TestValidationEngineStatus:
    """Test overall validation status determination."""
    
    def test_error_makes_invalid(
        self, db: Session, architecture_version
    ):
        """Test: ANY ERROR makes status INVALID."""
        resource = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="bad-01",
            resource_type="",  # Error: empty type
            name="Bad",
            location="eastus",
        )
        db.add(resource)
        db.commit()
        
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        assert result["status"] == "INVALID"
        assert result["error_count"] >= 1
    
    def test_warning_only_keeps_valid(
        self, db: Session, architecture_version, vm_catalog
    ):
        """Test: Only WARNINGs (no ERRORs) keeps status VALID."""
        # Setup recommended dependency
        recommended_dep = CatalogDependency(
            resource_type_id=vm_catalog.id,
            depends_on_resource_type="microsoft.insights/components",
            dependency_classification="RECOMMENDED",
            reason="Monitoring recommended",
        )
        db.add(recommended_dep)
        db.commit()
        
        vm = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="vm-01",
            resource_type="microsoft.compute/virtualmachines",
            name="Test VM",
            location="eastus",
        )
        db.add(vm)
        db.commit()
        
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        assert result["status"] == "VALID"
        assert result["error_count"] == 0
        assert result["warning_count"] >= 1
    
    def test_info_only_keeps_valid(
        self, db: Session, architecture_version, vm_catalog
    ):
        """Test: Only INFOs (no ERRORs) keeps status VALID."""
        # Setup optional dependency
        optional_dep = CatalogDependency(
            resource_type_id=vm_catalog.id,
            depends_on_resource_type="microsoft.compute/backupvaults",
            dependency_classification="OPTIONAL",
            reason="Backup optional",
        )
        db.add(optional_dep)
        db.commit()
        
        vm = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="vm-01",
            resource_type="microsoft.compute/virtualmachines",
            name="Test VM",
            location="eastus",
        )
        db.add(vm)
        db.commit()
        
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        assert result["status"] == "VALID"
        assert result["error_count"] == 0


class TestValidationEngineVersionIsolation:
    """Test version isolation."""
    
    def test_same_version_isolation(
        self, db: Session, architecture: Architecture, vm_catalog
    ):
        """Test: Validation only uses resources from the specified version."""
        v1 = ArchitectureVersion(
            architecture_id=architecture.id,
            version_number="1.0",
            status="draft",
        )
        v2 = ArchitectureVersion(
            architecture_id=architecture.id,
            version_number="2.0",
            status="draft",
        )
        db.add_all([v1, v2])
        db.commit()
        
        # Add VM to V1
        vm_v1 = Resource(
            architecture_version_id=v1.id,
            resource_key="vm-01",
            resource_type="microsoft.compute/virtualmachines",
            name="VM in V1",
            location="eastus",
        )
        db.add(vm_v1)
        db.commit()
        
        # Validate V2 (no resources)
        result_v2 = ValidationEngine.validate_version(
            db, architecture.id, v2.id
        )
        
        # Validate V1 (has VM)
        result_v1 = ValidationEngine.validate_version(
            db, architecture.id, v1.id
        )
        
        # V2 should be empty, V1 should have VM
        assert result_v2["total_findings"] == 0
        assert result_v1["total_findings"] == 0  # VM is valid
    
    def test_cross_architecture_isolation(
        self, db: Session, vm_catalog
    ):
        """Test: Validation only uses resources from the specified architecture."""
        arch1 = Architecture(name="Arch1", provider="azure")
        arch2 = Architecture(name="Arch2", provider="azure")
        db.add_all([arch1, arch2])
        db.commit()
        
        v1 = ArchitectureVersion(
            architecture_id=arch1.id, version_number="1.0", status="draft"
        )
        v2 = ArchitectureVersion(
            architecture_id=arch2.id, version_number="1.0", status="draft"
        )
        db.add_all([v1, v2])
        db.commit()
        
        # Add VM to Arch1
        vm1 = Resource(
            architecture_version_id=v1.id,
            resource_key="vm-01",
            resource_type="microsoft.compute/virtualmachines",
            name="VM in Arch1",
            location="eastus",
        )
        db.add(vm1)
        db.commit()
        
        # Validate Arch2 (no resources)
        result = ValidationEngine.validate_version(db, arch2.id, v2.id)
        
        assert result["total_findings"] == 0


class TestValidationEngineNoMutation:
    """Test that validation doesn't modify architecture."""
    
    def test_validation_does_not_modify_resources(
        self, db: Session, architecture_version, vm_catalog
    ):
        """Test: Validation never modifies resources."""
        vm = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="vm-01",
            resource_type="microsoft.compute/virtualmachines",
            name="Original Name",
            location="eastus",
        )
        db.add(vm)
        db.commit()
        
        original_name = vm.name
        
        # Run validation
        ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        # Refresh and check
        db.refresh(vm)
        assert vm.name == original_name
    
    def test_validation_does_not_add_resources(
        self, db: Session, architecture_version
    ):
        """Test: Validation never creates resources."""
        resource_count_before = (
            db.query(Resource)
            .filter(Resource.architecture_version_id == architecture_version.id)
            .count()
        )
        
        # Run validation
        ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        resource_count_after = (
            db.query(Resource)
            .filter(Resource.architecture_version_id == architecture_version.id)
            .count()
        )
        
        assert resource_count_before == resource_count_after


class TestValidationEngineMultipleFindings:
    """Test multiple findings aggregation."""
    
    def test_multiple_findings_aggregation(
        self, db: Session, architecture_version, vm_catalog
    ):
        """Test: Multiple findings are aggregated correctly."""
        # Create multiple problematic resources
        vm1 = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="vm-01",
            resource_type="",  # Error 1
            name="",  # Error 2
            location="eastus",
        )
        vm2 = Resource(
            architecture_version_id=architecture_version.id,
            resource_key="unknown-01",
            resource_type="microsoft.unknown/type",  # Error 3
            name="Unknown",
            location="eastus",
        )
        db.add_all([vm1, vm2])
        db.commit()
        
        result = ValidationEngine.validate_version(
            db, architecture_version.architecture_id, architecture_version.id
        )
        
        assert result["status"] == "INVALID"
        assert result["total_findings"] >= 3
        assert result["error_count"] >= 3


class TestValidationEngineAPI:
    """Test validation API endpoint (via client tests in conftest)."""
    
    def test_api_validation_endpoint_404_unknown_architecture(self, client):
        """Test: Unknown architecture returns 404."""
        fake_arch_id = uuid4()
        fake_version_id = uuid4()
        
        response = client.get(
            f"/architectures/{fake_arch_id}/versions/{fake_version_id}/validation"
        )
        
        assert response.status_code == 404
    
    def test_api_validation_endpoint_404_unknown_version(self, client, db: Session):
        """Test: Unknown version returns 404."""
        arch = Architecture(name="Test", provider="azure")
        db.add(arch)
        db.commit()
        
        fake_version_id = uuid4()
        
        response = client.get(
            f"/architectures/{arch.id}/versions/{fake_version_id}/validation"
        )
        
        assert response.status_code == 404
    
    def test_api_validation_endpoint_success(self, client, db: Session):
        """Test: Valid architecture/version returns validation result."""
        arch = Architecture(name="Test", provider="azure")
        db.add(arch)
        db.commit()
        
        version = ArchitectureVersion(
            architecture_id=arch.id,
            version_number="1.0",
            status="draft",
        )
        db.add(version)
        db.commit()
        
        response = client.get(
            f"/architectures/{arch.id}/versions/{version.id}/validation"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] in ["VALID", "INVALID"]
        assert "error_count" in data
        assert "warning_count" in data
        assert "info_count" in data
        assert "findings" in data
        assert isinstance(data["findings"], list)
