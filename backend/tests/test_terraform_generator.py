"""Tests for Milestone 6 deterministic Terraform generation."""

from typing import Optional

import pytest
from sqlalchemy.orm import Session

from app.models import (
    Architecture,
    ArchitectureVersion,
    CatalogDependency,
    CatalogHierarchy,
    Relationship,
    Resource,
    ResourceCatalog,
)
from app.services import TerraformGenerator


RG = "microsoft.resources/resourcegroups"
VNET = "microsoft.network/virtualnetworks"
SUBNET = "microsoft.network/virtualnetworks/subnets"
NIC = "microsoft.network/networkinterfaces"
VM = "microsoft.compute/virtualmachines"
NSG = "microsoft.network/networksecuritygroups"
STORAGE = "microsoft.storage/storageaccounts"


@pytest.fixture
def terraform_catalog(db: Session):
    """Create a small catalog with real Terraform mappings and hierarchy."""
    definitions = [
        (RG, "Resource Group", "management", "azurerm_resource_group"),
        (VNET, "Virtual Network", "networking", "azurerm_virtual_network"),
        (SUBNET, "Subnet", "networking", "azurerm_subnet"),
        (NIC, "Network Interface", "networking", "azurerm_network_interface"),
        (VM, "Virtual Machine", "compute", "azurerm_windows_virtual_machine"),
        (NSG, "Network Security Group", "networking", "azurerm_network_security_group"),
        (STORAGE, "Storage Account", "storage", "azurerm_storage_account"),
    ]
    catalogs = {}
    for resource_type, display_name, category, terraform_type in definitions:
        entry = ResourceCatalog(
            provider="azure",
            resource_type=resource_type,
            display_name=display_name,
            category=category,
            version="1.0",
            enabled=True,
            terraform_mapping={
                "terraform_type": terraform_type,
                "provider": "azurerm",
            },
        )
        db.add(entry)
        db.flush()
        catalogs[resource_type] = entry

    db.add_all(
        [
            CatalogHierarchy(
                parent_resource_type_id=catalogs[RG].id,
                child_resource_type_id=catalogs[VNET].id,
            ),
            CatalogHierarchy(
                parent_resource_type_id=catalogs[VNET].id,
                child_resource_type_id=catalogs[SUBNET].id,
            ),
            CatalogHierarchy(
                parent_resource_type_id=catalogs[RG].id,
                child_resource_type_id=catalogs[NIC].id,
            ),
            CatalogHierarchy(
                parent_resource_type_id=catalogs[RG].id,
                child_resource_type_id=catalogs[VM].id,
            ),
        ]
    )
    db.commit()
    return catalogs


def create_architecture(db: Session, version_number: str = "1.0"):
    architecture = Architecture(
        name="Terraform Architecture",
        provider="azure",
    )
    db.add(architecture)
    db.flush()
    version = ArchitectureVersion(
        architecture_id=architecture.id,
        version_number=version_number,
        status="draft",
    )
    db.add(version)
    db.commit()
    return architecture, version


def create_version(db: Session, architecture: Architecture, number: str):
    version = ArchitectureVersion(
        architecture_id=architecture.id,
        version_number=number,
        status="draft",
    )
    db.add(version)
    db.commit()
    return version


def add_resource(
    db: Session,
    version: ArchitectureVersion,
    key: str,
    resource_type: str,
    name: Optional[str] = None,
    parent: Optional[Resource] = None,
    location: Optional[str] = "eastus",
    properties: Optional[dict] = None,
    sku: Optional[dict] = None,
    tags: Optional[dict] = None,
):
    resource = Resource(
        architecture_version_id=version.id,
        resource_key=key,
        resource_type=resource_type,
        name=name or key,
        parent_resource_id=parent.id if parent else None,
        location=location,
        properties=properties,
        sku=sku,
        tags=tags,
    )
    db.add(resource)
    db.commit()
    return resource


def relate(
    db: Session,
    version: ArchitectureVersion,
    source: Resource,
    target: Resource,
    relationship_type: str = "uses",
):
    relationship = Relationship(
        architecture_version_id=version.id,
        source_resource_id=source.id,
        target_resource_id=target.id,
        relationship_type=relationship_type,
    )
    db.add(relationship)
    db.commit()
    return relationship


def generated_content(result: dict) -> str:
    return "\n".join(item["content"] for item in result["files"])


def file_content(result: dict, path: str) -> str:
    return next(item["content"] for item in result["files"] if item["path"] == path)


class TestBasicGeneration:
    def test_resource_group_generation(self, db: Session, terraform_catalog):
        architecture, version = create_architecture(db)
        add_resource(
            db,
            version,
            "rg-prod",
            RG,
            tags={"owner": "platform", "cost.center": "shared"},
        )

        result = TerraformGenerator.generate(db, architecture.id, version.id)

        assert result["status"] == "GENERATED"
        content = file_content(result, "resource_group.tf")
        assert 'resource "azurerm_resource_group" "rg_prod"' in content
        assert '"owner" = "platform"' in content
        assert '"cost.center" = "shared"' in content

    def test_vnet_generation_uses_resource_group_reference(self, db: Session, terraform_catalog):
        architecture, version = create_architecture(db)
        resource_group = add_resource(db, version, "rg-main", RG)
        add_resource(
            db,
            version,
            "vnet-main",
            VNET,
            parent=resource_group,
            properties={"addressSpace": {"addressPrefixes": ["10.0.0.0/16"]}},
        )

        result = TerraformGenerator.generate(db, architecture.id, version.id)
        content = file_content(result, "networking/virtual_network.tf")

        assert "resource_group_name = azurerm_resource_group.rg_main.name" in content
        assert 'address_space = ["10.0.0.0/16"]' in content

    def test_subnet_generation_uses_vnet_reference(self, db: Session, terraform_catalog):
        architecture, version = create_architecture(db)
        resource_group = add_resource(db, version, "rg-main", RG)
        vnet = add_resource(db, version, "vnet-main", VNET, parent=resource_group)
        add_resource(
            db,
            version,
            "subnet-app",
            SUBNET,
            parent=vnet,
            properties={"addressPrefix": "10.0.1.0/24"},
        )

        result = TerraformGenerator.generate(db, architecture.id, version.id)
        content = file_content(result, "networking/subnet.tf")

        assert "virtual_network_name = azurerm_virtual_network.vnet_main.name" in content
        assert "resource_group_name = azurerm_resource_group.rg_main.name" in content
        assert 'address_prefixes = ["10.0.1.0/24"]' in content

    def test_multiple_resource_groups(self, db: Session, terraform_catalog):
        architecture, version = create_architecture(db)
        add_resource(db, version, "rg-a", RG)
        add_resource(db, version, "rg-b", RG)

        result = TerraformGenerator.generate(db, architecture.id, version.id)
        content = file_content(result, "resource_group.tf")

        assert content.count('resource "azurerm_resource_group"') == 2

    def test_multiple_vnets_preserve_parent_references(self, db: Session, terraform_catalog):
        architecture, version = create_architecture(db)
        rg_a = add_resource(db, version, "rg-a", RG)
        rg_b = add_resource(db, version, "rg-b", RG)
        add_resource(db, version, "vnet-a", VNET, parent=rg_a)
        add_resource(db, version, "vnet-b", VNET, parent=rg_b)

        result = TerraformGenerator.generate(db, architecture.id, version.id)
        content = file_content(result, "networking/virtual_network.tf")

        assert "azurerm_resource_group.rg_a.name" in content
        assert "azurerm_resource_group.rg_b.name" in content

    def test_multiple_subnets_are_grouped_deterministically(self, db: Session, terraform_catalog):
        architecture, version = create_architecture(db)
        rg = add_resource(db, version, "rg", RG)
        vnet = add_resource(db, version, "vnet", VNET, parent=rg)
        add_resource(db, version, "subnet-b", SUBNET, parent=vnet)
        add_resource(db, version, "subnet-a", SUBNET, parent=vnet)

        result = TerraformGenerator.generate(db, architecture.id, version.id)
        content = file_content(result, "networking/subnet.tf")

        assert content.index('"subnet_a"') < content.index('"subnet_b"')


class TestRelationshipsAndDependencies:
    def test_nic_and_vm_use_relationship_references(self, db: Session, terraform_catalog):
        architecture, version = create_architecture(db)
        rg = add_resource(db, version, "rg", RG)
        vnet = add_resource(db, version, "vnet", VNET, parent=rg)
        subnet = add_resource(db, version, "subnet", SUBNET, parent=vnet)
        nic = add_resource(db, version, "nic", NIC, parent=rg)
        vm = add_resource(db, version, "vm", VM, parent=rg, sku={"name": "Standard_D2s_v5"})
        relate(db, version, nic, subnet)
        relate(db, version, vm, nic)

        result = TerraformGenerator.generate(db, architecture.id, version.id)

        assert "subnet_id                     = azurerm_subnet.subnet.id" in file_content(
            result, "networking/network_interface.tf"
        )
        assert "network_interface_ids = [azurerm_network_interface.nic.id]" in file_content(
            result, "compute/windows_virtual_machine.tf"
        )

    def test_required_dependency_satisfied(self, db: Session, terraform_catalog):
        terraform_catalog[VM].required_dependencies.append(
            CatalogDependency(
                depends_on_resource_type=NIC,
                dependency_classification="REQUIRED",
                reason="VM requires NIC",
            )
        )
        db.commit()
        architecture, version = create_architecture(db)
        nic = add_resource(db, version, "nic", NIC)
        vm = add_resource(db, version, "vm", VM)
        relate(db, version, vm, nic)

        result = TerraformGenerator.generate(db, architecture.id, version.id)

        assert result["status"] == "GENERATED"

    def test_required_dependency_missing_blocks_generation(self, db: Session, terraform_catalog):
        terraform_catalog[VM].required_dependencies.append(
            CatalogDependency(
                depends_on_resource_type=NIC,
                dependency_classification="REQUIRED",
                reason="VM requires NIC",
            )
        )
        db.commit()
        architecture, version = create_architecture(db)
        add_resource(db, version, "vm", VM)

        result = TerraformGenerator.generate(db, architecture.id, version.id)

        assert result["status"] == "BLOCKED"
        assert any(
            finding["code"] == "REQUIRED_DEPENDENCY_MISSING"
            for finding in result["validation_findings"]
        )


class TestValidationAndCatalogFailures:
    def test_validation_error_blocks_generation(self, db: Session, terraform_catalog):
        architecture, version = create_architecture(db)
        add_resource(db, version, "unknown", "microsoft.unknown/resources")

        result = TerraformGenerator.generate(db, architecture.id, version.id)

        assert result["status"] == "BLOCKED"
        assert result["files"] == []
        assert result["errors"][0]["code"] == "INVALID_ARCHITECTURE"

    def test_validation_warning_allows_generation(self, db: Session, terraform_catalog):
        db.add(
            CatalogDependency(
                resource_type_id=terraform_catalog[STORAGE].id,
                depends_on_resource_type=NSG,
                dependency_classification="RECOMMENDED",
                reason="Storage should have network controls",
            )
        )
        db.commit()
        architecture, version = create_architecture(db)
        add_resource(db, version, "storage", STORAGE)

        result = TerraformGenerator.generate(db, architecture.id, version.id)

        assert result["status"] == "GENERATED"
        assert any(item["severity"] == "WARNING" for item in result["validation_findings"])

    def test_unknown_catalog_resource_fails(self, db: Session, terraform_catalog):
        architecture, version = create_architecture(db)
        add_resource(db, version, "mystery", "unknown/provider")

        result = TerraformGenerator.generate(db, architecture.id, version.id)

        assert result["status"] == "BLOCKED"
        assert any(
            item["code"] == "CATALOG_RESOURCE_TYPE_UNKNOWN"
            for item in result["validation_findings"]
        )
        assert len(result["resources_unsupported"]) == 1

    def test_missing_terraform_mapping_fails(self, db: Session, terraform_catalog):
        resource_type = "microsoft.custom/mappedlater"
        db.add(
            ResourceCatalog(
                provider="azure",
                resource_type=resource_type,
                display_name="Mapped Later",
                category="custom",
                version="1.0",
                enabled=True,
                terraform_mapping=None,
            )
        )
        db.commit()
        architecture, version = create_architecture(db)
        add_resource(db, version, "custom", resource_type)

        result = TerraformGenerator.generate(db, architecture.id, version.id)

        assert result["status"] == "BLOCKED"
        assert result["errors"][0]["code"] == "TERRAFORM_MAPPING_MISSING"

    def test_invalid_terraform_mapping_fails(self, db: Session, terraform_catalog):
        resource_type = "microsoft.custom/invalid"
        db.add(
            ResourceCatalog(
                provider="azure",
                resource_type=resource_type,
                display_name="Invalid Mapping",
                category="custom",
                version="1.0",
                enabled=True,
                terraform_mapping={"terraform_type": "invalid-type", "provider": "azurerm"},
            )
        )
        db.commit()
        architecture, version = create_architecture(db)
        add_resource(db, version, "invalid", resource_type)

        result = TerraformGenerator.generate(db, architecture.id, version.id)

        assert result["status"] == "BLOCKED"
        assert result["errors"][0]["code"] == "TERRAFORM_MAPPING_INVALID"

    def test_missing_catalog_required_property_fails(self, db: Session, terraform_catalog):
        terraform_catalog[STORAGE].properties_schema = {"required": ["accountTier"]}
        db.commit()
        architecture, version = create_architecture(db)
        add_resource(db, version, "storage", STORAGE)

        result = TerraformGenerator.generate(db, architecture.id, version.id)

        assert result["status"] == "BLOCKED"
        assert result["errors"][0]["code"] == "REQUIRED_PROPERTY_MISSING"


class TestSecretsAndDeterminism:
    def test_secret_value_never_appears_in_output(self, db: Session, terraform_catalog):
        architecture, version = create_architecture(db)
        add_resource(
            db,
            version,
            "vm-secure",
            VM,
            properties={"administratorPassword": "Never-Emit-This-Secret!"},
            tags={"api_token": "Never-Emit-This-Token!"},
        )

        result = TerraformGenerator.generate(db, architecture.id, version.id)
        serialized = str(result)

        assert "Never-Emit-This-Secret!" not in serialized
        assert "Never-Emit-This-Token!" not in serialized
        assert "SECRET_CONFIGURATION_REQUIRED" in serialized

    def test_secret_becomes_sensitive_variable(self, db: Session, terraform_catalog):
        architecture, version = create_architecture(db)
        add_resource(
            db,
            version,
            "database",
            STORAGE,
            properties={"apiKey": "private-value"},
        )

        result = TerraformGenerator.generate(db, architecture.id, version.id)
        variables = file_content(result, "variables.tf")
        resource_file = file_content(result, "data/storage_account.tf")

        assert "sensitive = true" in variables
        assert "var.database_api_key" in resource_file
        assert "private-value" not in generated_content(result)

    def test_same_version_generates_identical_output(self, db: Session, terraform_catalog):
        architecture, version = create_architecture(db)
        add_resource(db, version, "rg", RG, tags={"z": "last", "a": "first"})

        first = TerraformGenerator.generate(db, architecture.id, version.id)
        second = TerraformGenerator.generate(db, architecture.id, version.id)

        assert first == second

    def test_identifier_sanitization(self):
        assert TerraformGenerator.sanitize_identifier("production-network.eastus") == (
            "production_network_eastus"
        )
        assert TerraformGenerator.sanitize_identifier("123 network") == "resource_123_network"

    def test_identifier_collisions_are_resolved_deterministically(self, db: Session, terraform_catalog):
        architecture, version = create_architecture(db)
        add_resource(db, version, "web-app", RG, name="first")
        add_resource(db, version, "web app", RG, name="second")

        result = TerraformGenerator.generate(db, architecture.id, version.id)
        content = file_content(result, "resource_group.tf")

        assert 'resource "azurerm_resource_group" "web_app"' in content
        assert 'resource "azurerm_resource_group" "web_app_2"' in content


class TestChangeDetection:
    def test_added_resource_detection(self, db: Session, terraform_catalog):
        architecture, version_one = create_architecture(db)
        add_resource(db, version_one, "rg", RG)
        version_two = create_version(db, architecture, "2.0")
        add_resource(db, version_two, "rg", RG)
        add_resource(db, version_two, "storage", STORAGE)

        result = TerraformGenerator.compare_versions(
            db, architecture.id, version_one.id, version_two.id
        )

        assert result["added_resources"] == ["storage"]
        assert "data/storage_account.tf" in result["affected_files"]

    def test_removed_resource_detection(self, db: Session, terraform_catalog):
        architecture, version_one = create_architecture(db)
        add_resource(db, version_one, "rg", RG)
        add_resource(db, version_one, "storage", STORAGE)
        version_two = create_version(db, architecture, "2.0")
        add_resource(db, version_two, "rg", RG)

        result = TerraformGenerator.compare_versions(
            db, architecture.id, version_one.id, version_two.id
        )

        assert result["removed_resources"] == ["storage"]

    def test_modified_resource_detection(self, db: Session, terraform_catalog):
        architecture, version_one = create_architecture(db)
        add_resource(db, version_one, "rg", RG, location="eastus")
        version_two = create_version(db, architecture, "2.0")
        add_resource(db, version_two, "rg", RG, location="westus")

        result = TerraformGenerator.compare_versions(
            db, architecture.id, version_one.id, version_two.id
        )

        assert result["modified_resources"] == ["rg"]
        assert "resource_group.tf" in result["affected_files"]

    def test_unchanged_resource_and_files_detection(self, db: Session, terraform_catalog):
        architecture, version_one = create_architecture(db)
        add_resource(db, version_one, "rg", RG)
        version_two = create_version(db, architecture, "2.0")
        add_resource(db, version_two, "rg", RG)

        result = TerraformGenerator.compare_versions(
            db, architecture.id, version_one.id, version_two.id
        )

        assert result["unchanged_resources"] == ["rg"]
        assert "resource_group.tf" in result["unchanged_files"]
        assert result["affected_files"] == []


class TestTerraformAPI:
    def test_generate_endpoint(self, client, db: Session, terraform_catalog):
        architecture, version = create_architecture(db)
        add_resource(db, version, "rg", RG)

        response = client.post(
            f"/architectures/{architecture.id}/versions/{version.id}/terraform/generate",
            json={},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "GENERATED"
        assert any(item["path"] == "resource_group.tf" for item in response.json()["files"])
