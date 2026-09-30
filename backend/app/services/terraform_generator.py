"""Deterministic Terraform generation from the canonical architecture model."""

import json
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from ..enums import TerraformGenerationCode, TerraformGenerationStatus
from ..models import (
    Architecture,
    ArchitectureVersion,
    Dependency,
    Relationship,
    Resource,
    ResourceCatalog,
)
from .services import ValidationEngine


class TerraformGenerator:
    """Generate Terraform without executing Terraform or contacting Azure."""

    GENERATOR_VERSION = "1.0.0"
    _TERRAFORM_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
    _SECRET_NAMES = frozenset(
        {
            "access_key",
            "administrator_password",
            "api_key",
            "apikey",
            "client_secret",
            "connection_string",
            "password",
            "private_key",
            "secret",
            "token",
        }
    )
    _SECRET_SUFFIXES = (
        "password",
        "api_key",
        "access_key",
        "secret",
        "secret_value",
        "token",
        "token_value",
        "private_key",
        "connection_string",
        "certificate_password",
        "certificate_private_key",
    )

    @classmethod
    def generate(
        cls,
        db: Session,
        architecture_id: UUID,
        version_id: UUID,
        compare_to_version_id: Optional[UUID] = None,
    ) -> dict:
        """Generate deterministic Terraform for one architecture version."""
        architecture, version = cls._load_architecture_version(
            db, architecture_id, version_id
        )
        validation = ValidationEngine.validate_version(
            db, architecture_id, version_id
        )
        if validation["status"] == "INVALID":
            blocking_findings = [
                finding
                for finding in validation["findings"]
                if finding["severity"] == "ERROR"
            ]
            validation_errors = [
                cls._finding(
                    finding["code"],
                    finding["severity"],
                    finding["message"],
                    details=finding.get("details"),
                )
                | {
                    "resource_id": finding.get("resource_id"),
                    "resource_type": (finding.get("details") or {}).get(
                        "resource_type"
                    ),
                }
                for finding in blocking_findings
            ]
            unsupported = sorted(
                {
                    finding["resource_id"]
                    for finding in blocking_findings
                    if finding.get("resource_id")
                    and finding["code"]
                    in {
                        "RESOURCE_TYPE_NOT_IN_CATALOG",
                        "CATALOG_RESOURCE_TYPE_UNKNOWN",
                    }
                },
                key=str,
            )
            return cls._blocked_result(
                architecture_id,
                version_id,
                validation,
                [
                    cls._finding(
                        TerraformGenerationCode.INVALID_ARCHITECTURE.value,
                        "ERROR",
                        "Architecture validation contains blocking errors",
                        details={"error_count": validation["error_count"]},
                    )
                ]
                + validation_errors,
                unsupported,
            )

        resources = (
            db.query(Resource)
            .filter(Resource.architecture_version_id == version_id)
            .order_by(Resource.resource_key, Resource.id)
            .all()
        )
        relationships = (
            db.query(Relationship)
            .filter(Relationship.architecture_version_id == version_id)
            .order_by(
                Relationship.source_resource_id,
                Relationship.target_resource_id,
                Relationship.relationship_type,
            )
            .all()
        )
        dependencies = (
            db.query(Dependency)
            .filter(Dependency.architecture_version_id == version_id)
            .order_by(
                Dependency.resource_id,
                Dependency.depends_on_resource_id,
                Dependency.dependency_type,
            )
            .all()
        )
        catalogs = cls._load_catalogs(db, architecture.provider, resources)

        errors: List[dict] = []
        unsupported: List[UUID] = []
        required_property_errors: List[dict] = []
        for resource in resources:
            catalog = catalogs.get(resource.resource_type)
            if catalog is None:
                errors.append(
                    cls._finding(
                        TerraformGenerationCode.UNSUPPORTED_TERRAFORM_GENERATION.value,
                        "ERROR",
                        f"Resource type {resource.resource_type} is not enabled in the Resource Catalog",
                        resource,
                    )
                )
                unsupported.append(resource.id)
                continue

            mapping = catalog.terraform_mapping
            if not isinstance(mapping, dict) or not mapping.get("terraform_type"):
                errors.append(
                    cls._finding(
                        TerraformGenerationCode.TERRAFORM_MAPPING_MISSING.value,
                        "ERROR",
                        f"Resource type {resource.resource_type} has no Terraform mapping",
                        resource,
                    )
                )
                unsupported.append(resource.id)
                continue

            terraform_type = mapping["terraform_type"]
            if (
                not isinstance(terraform_type, str)
                or not cls._TERRAFORM_TYPE_PATTERN.fullmatch(terraform_type)
                or not terraform_type.startswith("azurerm_")
                or mapping.get("provider", "azurerm") != "azurerm"
                or not cls._has_safe_configured_path(mapping)
            ):
                errors.append(
                    cls._finding(
                        TerraformGenerationCode.TERRAFORM_MAPPING_INVALID.value,
                        "ERROR",
                        f"Resource type {resource.resource_type} has an invalid or unsupported Terraform mapping",
                        resource,
                        {"terraform_type": terraform_type},
                    )
                )
                unsupported.append(resource.id)
                continue

            required_property_errors.extend(
                cls._validate_required_properties(resource, catalog)
            )

        errors.extend(required_property_errors)
        if errors:
            return cls._blocked_result(
                architecture_id,
                version_id,
                validation,
                errors,
                unsupported,
            )

        labels = cls._build_labels(resources)
        resource_by_id = {resource.id: resource for resource in resources}
        outgoing_targets = cls._build_outgoing_targets(
            relationships, dependencies
        )
        secret_variables = cls._collect_secret_variables(resources, labels)
        warnings = cls._secret_warnings(resources, secret_variables)
        warnings.extend(cls._generic_rendering_warnings(resources, catalogs))

        generated_files = cls._generate_files(
            resources,
            catalogs,
            labels,
            resource_by_id,
            outgoing_targets,
            secret_variables,
        )
        changed_files: List[str] = []
        if compare_to_version_id is not None:
            comparison = cls.compare_versions(
                db, architecture_id, compare_to_version_id, version_id
            )
            changed_files = comparison["affected_files"]

        return {
            "architecture_id": architecture_id,
            "architecture_version_id": version_id,
            "generator_version": cls.GENERATOR_VERSION,
            "status": TerraformGenerationStatus.GENERATED.value,
            "validation_status": validation["status"],
            "validation_findings": validation["findings"],
            "files": generated_files,
            "warnings": warnings,
            "errors": [],
            "resources_processed": len(resources),
            "resources_unsupported": [],
            "changed_files": changed_files,
        }

    @classmethod
    def compare_versions(
        cls,
        db: Session,
        architecture_id: UUID,
        from_version_id: UUID,
        to_version_id: UUID,
    ) -> dict:
        """Compare canonical resources and actual generated file content."""
        cls._load_architecture_version(db, architecture_id, from_version_id)
        cls._load_architecture_version(db, architecture_id, to_version_id)
        from_result = cls.generate(db, architecture_id, from_version_id)
        to_result = cls.generate(db, architecture_id, to_version_id)
        if from_result["status"] != TerraformGenerationStatus.GENERATED.value:
            raise ValueError("Source architecture version cannot generate Terraform")
        if to_result["status"] != TerraformGenerationStatus.GENERATED.value:
            raise ValueError("Target architecture version cannot generate Terraform")

        from_resources = cls._resource_snapshots(db, from_version_id)
        to_resources = cls._resource_snapshots(db, to_version_id)
        from_files = {item["path"]: item for item in from_result["files"]}
        to_files = {item["path"]: item for item in to_result["files"]}

        added = sorted(set(to_resources) - set(from_resources))
        removed = sorted(set(from_resources) - set(to_resources))
        common = sorted(set(from_resources) & set(to_resources))
        modified = [
            key for key in common
            if cls._comparable_snapshot(from_resources[key])
            != cls._comparable_snapshot(to_resources[key])
        ]
        unchanged = [key for key in common if key not in set(modified)]

        all_paths = sorted(set(from_files) | set(to_files))
        affected_files = [
            path for path in all_paths
            if from_files.get(path, {}).get("content")
            != to_files.get(path, {}).get("content")
        ]
        unchanged_files = [path for path in all_paths if path not in affected_files]

        resource_changes = []
        for key, change_type in (
            [(key, "ADDED") for key in added]
            + [(key, "REMOVED") for key in removed]
            + [(key, "MODIFIED") for key in modified]
        ):
            affected_for_resource = sorted(
                path for path in affected_files
                if key in from_files.get(path, {}).get("resource_keys", [])
                or key in to_files.get(path, {}).get("resource_keys", [])
            )
            resource_changes.append(
                {
                    "resource_key": key,
                    "change_type": change_type,
                    "from_resource_id": from_resources.get(key, {}).get("id"),
                    "to_resource_id": to_resources.get(key, {}).get("id"),
                    "affected_files": affected_for_resource,
                }
            )

        return {
            "architecture_id": architecture_id,
            "from_version_id": from_version_id,
            "to_version_id": to_version_id,
            "added_resources": added,
            "removed_resources": removed,
            "modified_resources": modified,
            "unchanged_resources": unchanged,
            "resource_changes": resource_changes,
            "affected_files": affected_files,
            "unchanged_files": unchanged_files,
        }

    @staticmethod
    def sanitize_identifier(value: str) -> str:
        """Convert an architecture key into a valid Terraform label."""
        label = re.sub(r"[^0-9A-Za-z_]", "_", value.strip()).lower()
        label = re.sub(r"_+", "_", label).strip("_") or "resource"
        if label[0].isdigit():
            label = f"resource_{label}"
        return label

    @classmethod
    def _load_architecture_version(
        cls, db: Session, architecture_id: UUID, version_id: UUID
    ) -> Tuple[Architecture, ArchitectureVersion]:
        architecture = (
            db.query(Architecture)
            .filter(Architecture.id == architecture_id)
            .first()
        )
        if architecture is None:
            raise ValueError(f"Architecture {architecture_id} not found")
        version = (
            db.query(ArchitectureVersion)
            .filter(
                ArchitectureVersion.id == version_id,
                ArchitectureVersion.architecture_id == architecture_id,
            )
            .first()
        )
        if version is None:
            raise ValueError(f"Architecture version {version_id} not found")
        return architecture, version

    @staticmethod
    def _load_catalogs(
        db: Session, provider: str, resources: List[Resource]
    ) -> Dict[str, ResourceCatalog]:
        resource_types = sorted({resource.resource_type for resource in resources})
        if not resource_types:
            return {}
        entries = (
            db.query(ResourceCatalog)
            .filter(
                ResourceCatalog.provider == provider,
                ResourceCatalog.enabled.is_(True),
                ResourceCatalog.resource_type.in_(resource_types),
            )
            .order_by(
                ResourceCatalog.resource_type,
                ResourceCatalog.version.desc(),
                ResourceCatalog.id,
            )
            .all()
        )
        catalogs: Dict[str, ResourceCatalog] = {}
        for entry in entries:
            catalogs.setdefault(entry.resource_type, entry)
        return catalogs

    @classmethod
    def _validate_required_properties(
        cls, resource: Resource, catalog: ResourceCatalog
    ) -> List[dict]:
        schema = catalog.properties_schema or {}
        mapping = catalog.terraform_mapping or {}
        additional = mapping.get("additional_mapping") or {}
        required = list(schema.get("required", []))
        required.extend(additional.get("required_properties", []))
        properties = {**(catalog.default_properties or {}), **(resource.properties or {})}
        return [
            cls._finding(
                TerraformGenerationCode.REQUIRED_PROPERTY_MISSING.value,
                "ERROR",
                f"Required property {property_name} is missing",
                resource,
                {"property": property_name},
            )
            for property_name in sorted(set(required))
            if property_name not in properties or properties[property_name] is None
        ]

    @classmethod
    def _build_labels(cls, resources: List[Resource]) -> Dict[UUID, str]:
        labels: Dict[UUID, str] = {}
        counts: Dict[str, int] = defaultdict(int)
        for resource in sorted(resources, key=lambda item: (item.resource_key, str(item.id))):
            base = cls.sanitize_identifier(resource.resource_key)
            counts[base] += 1
            labels[resource.id] = (
                base if counts[base] == 1 else f"{base}_{counts[base]}"
            )
        return labels

    @staticmethod
    def _build_outgoing_targets(
        relationships: List[Relationship], dependencies: List[Dependency]
    ) -> Dict[UUID, List[UUID]]:
        targets: Dict[UUID, Set[UUID]] = defaultdict(set)
        for relationship in relationships:
            targets[relationship.source_resource_id].add(
                relationship.target_resource_id
            )
        for dependency in dependencies:
            targets[dependency.resource_id].add(
                dependency.depends_on_resource_id
            )
        return {
            resource_id: sorted(resource_targets, key=str)
            for resource_id, resource_targets in targets.items()
        }

    @classmethod
    def _collect_secret_variables(
        cls, resources: List[Resource], labels: Dict[UUID, str]
    ) -> Dict[Tuple[UUID, Tuple[str, ...]], str]:
        variables: Dict[Tuple[UUID, Tuple[str, ...]], str] = {}
        for resource in resources:
            cls._walk_secret_values(
                resource.id,
                resource.properties or {},
                labels[resource.id],
                (),
                variables,
            )
            cls._walk_secret_values(
                resource.id,
                resource.tags or {},
                labels[resource.id],
                ("tags",),
                variables,
            )
            cls._walk_secret_values(
                resource.id,
                resource.sku or {},
                labels[resource.id],
                ("sku",),
                variables,
            )
        return variables

    @classmethod
    def _walk_secret_values(
        cls,
        resource_id: UUID,
        value: Any,
        label: str,
        path: Tuple[str, ...],
        variables: Dict[Tuple[UUID, Tuple[str, ...]], str],
    ) -> None:
        if not isinstance(value, dict):
            return
        for key in sorted(value):
            child_path = path + (str(key),)
            if cls._is_secret_key(str(key)):
                path_label = cls.sanitize_identifier("_".join(child_path))
                variables[(resource_id, child_path)] = f"{label}_{path_label}"
            else:
                cls._walk_secret_values(
                    resource_id,
                    value[key],
                    label,
                    child_path,
                    variables,
                )

    @classmethod
    def _secret_warnings(
        cls,
        resources: List[Resource],
        variables: Dict[Tuple[UUID, Tuple[str, ...]], str],
    ) -> List[dict]:
        resource_by_id = {resource.id: resource for resource in resources}
        warnings = []
        for (resource_id, path), variable_name in sorted(
            variables.items(), key=lambda item: item[1]
        ):
            resource = resource_by_id[resource_id]
            warnings.append(
                cls._finding(
                    TerraformGenerationCode.SECRET_CONFIGURATION_REQUIRED.value,
                    "WARNING",
                    f"Secret property {'.'.join(path)} requires runtime variable {variable_name}",
                    resource,
                    {"variable": variable_name},
                )
            )
        return warnings

    @classmethod
    def _generic_rendering_warnings(
        cls,
        resources: List[Resource],
        catalogs: Dict[str, ResourceCatalog],
    ) -> List[dict]:
        """Disclose properties rendered without explicit catalog attribute metadata."""
        warnings = []
        for resource in sorted(resources, key=lambda item: item.resource_key):
            catalog = catalogs[resource.resource_type]
            mapping = catalog.terraform_mapping or {}
            additional = mapping.get("additional_mapping") or {}
            property_map = additional.get("property_map") or {}
            terraform_type = mapping["terraform_type"]
            special_properties = cls._special_property_keys(terraform_type)
            properties = {
                **(catalog.default_properties or {}),
                **(resource.properties or {}),
            }
            for key in sorted(properties):
                if key in property_map or key in special_properties:
                    continue
                warnings.append(
                    cls._finding(
                        TerraformGenerationCode.GENERIC_PROPERTY_RENDERING.value,
                        "WARNING",
                        f"Property {key} is rendered heuristically because the catalog has no explicit property mapping",
                        resource,
                        {"property": key, "value_type": type(properties[key]).__name__},
                    )
                )
            if resource.sku and terraform_type not in {
                "azurerm_windows_virtual_machine",
                "azurerm_linux_virtual_machine",
            } and not additional.get("sku_property_map"):
                warnings.append(
                    cls._finding(
                        TerraformGenerationCode.GENERIC_PROPERTY_RENDERING.value,
                        "WARNING",
                        "SKU metadata was not emitted because the catalog has no sku_property_map",
                        resource,
                        {"property": "sku", "value_type": "dict"},
                    )
                )
        return warnings

    @classmethod
    def _generate_files(
        cls,
        resources: List[Resource],
        catalogs: Dict[str, ResourceCatalog],
        labels: Dict[UUID, str],
        resource_by_id: Dict[UUID, Resource],
        outgoing_targets: Dict[UUID, List[UUID]],
        secret_variables: Dict[Tuple[UUID, Tuple[str, ...]], str],
    ) -> List[dict]:
        files: List[dict] = [
            {
                "path": "provider.tf",
                "content": cls._provider_file(),
                "resource_keys": [],
            },
            {
                "path": "terraform.tf",
                "content": cls._terraform_file(),
                "resource_keys": [],
            },
        ]
        grouped: Dict[str, List[Resource]] = defaultdict(list)
        for resource in resources:
            grouped[cls._file_path(resource, catalogs[resource.resource_type])].append(
                resource
            )

        for path in sorted(grouped):
            file_resources = sorted(
                grouped[path], key=lambda item: (labels[item.id], item.resource_key)
            )
            blocks = [
                cls._render_resource(
                    resource,
                    catalogs[resource.resource_type],
                    catalogs,
                    labels,
                    resource_by_id,
                    outgoing_targets,
                    secret_variables,
                )
                for resource in file_resources
            ]
            files.append(
                {
                    "path": path,
                    "content": "\n\n".join(blocks) + "\n",
                    "resource_keys": [item.resource_key for item in file_resources],
                }
            )

        if secret_variables:
            files.append(
                {
                    "path": "variables.tf",
                    "content": cls._variables_file(secret_variables),
                    "resource_keys": [],
                }
            )
        if resources:
            files.append(
                {
                    "path": "outputs.tf",
                    "content": cls._outputs_file(resources, catalogs, labels),
                    "resource_keys": [
                        resource.resource_key
                        for resource in sorted(resources, key=lambda item: item.resource_key)
                    ],
                }
            )
        return sorted(files, key=lambda item: item["path"])

    @staticmethod
    def _provider_file() -> str:
        return (
            'provider "azurerm" {\n'
            "  features {}\n"
            "}\n"
        )

    @staticmethod
    def _terraform_file() -> str:
        return (
            "terraform {\n"
            '  required_version = ">= 1.5.0"\n\n'
            "  required_providers {\n"
            "    azurerm = {\n"
            '      source  = "hashicorp/azurerm"\n'
            '      version = "~> 3.0"\n'
            "    }\n"
            "  }\n"
            "}\n"
        )

    @classmethod
    def _variables_file(
        cls, secret_variables: Dict[Tuple[UUID, Tuple[str, ...]], str]
    ) -> str:
        blocks = []
        for variable_name in sorted(set(secret_variables.values())):
            blocks.append(
                f'variable "{variable_name}" {{\n'
                "  type      = string\n"
                "  sensitive = true\n"
                "}"
            )
        return "\n\n".join(blocks) + "\n"

    @classmethod
    def _outputs_file(
        cls,
        resources: List[Resource],
        catalogs: Dict[str, ResourceCatalog],
        labels: Dict[UUID, str],
    ) -> str:
        blocks = []
        for resource in sorted(resources, key=lambda item: item.resource_key):
            terraform_type = catalogs[resource.resource_type].terraform_mapping[
                "terraform_type"
            ]
            label = labels[resource.id]
            blocks.append(
                f'output "{label}_id" {{\n'
                f'  description = "ID of {cls._escape(resource.name)}"\n'
                f"  value       = {terraform_type}.{label}.id\n"
                "}"
            )
        return "\n\n".join(blocks) + "\n"

    @classmethod
    def _file_path(cls, resource: Resource, catalog: ResourceCatalog) -> str:
        mapping = catalog.terraform_mapping or {}
        additional = mapping.get("additional_mapping") or {}
        configured_path = additional.get("file_path")
        if configured_path:
            return str(configured_path).replace("\\", "/").lstrip("/")
        terraform_type = mapping["terraform_type"]
        short_name = terraform_type.removeprefix("azurerm_")
        if terraform_type == "azurerm_resource_group":
            return "resource_group.tf"
        category = cls.sanitize_identifier(catalog.category or "resources")
        domain = {
            "management": "",
            "network": "networking",
            "networking": "networking",
            "compute": "compute",
            "application": "application",
            "web": "application",
            "storage": "data",
            "database": "data",
            "data": "data",
            "security": "security",
            "identity": "security",
            "monitoring": "monitoring",
        }.get(category, category)
        filename = f"{short_name}.tf"
        return f"{domain}/{filename}" if domain else filename

    @classmethod
    def _render_resource(
        cls,
        resource: Resource,
        catalog: ResourceCatalog,
        catalogs: Dict[str, ResourceCatalog],
        labels: Dict[UUID, str],
        resource_by_id: Dict[UUID, Resource],
        outgoing_targets: Dict[UUID, List[UUID]],
        secret_variables: Dict[Tuple[UUID, Tuple[str, ...]], str],
    ) -> str:
        mapping = catalog.terraform_mapping or {}
        terraform_type = mapping["terraform_type"]
        label = labels[resource.id]
        properties = {**(catalog.default_properties or {}), **(resource.properties or {})}
        property_map = (mapping.get("additional_mapping") or {}).get(
            "property_map", {}
        )
        sku_property_map = (mapping.get("additional_mapping") or {}).get(
            "sku_property_map", {}
        )

        lines = [f'resource "{terraform_type}" "{label}" {{']
        lines.append(f'  name = "{cls._escape(resource.name)}"')
        if resource.location and terraform_type != "azurerm_subnet":
            lines.append(f'  location = "{cls._escape(resource.location)}"')

        references, consumed_properties = cls._reference_attributes(
            resource,
            terraform_type,
            catalogs,
            labels,
            resource_by_id,
            outgoing_targets,
        )
        lines.extend(f"  {line}" for line in references)

        if terraform_type == "azurerm_virtual_network":
            address_space = cls._first_property(
                properties, "address_space", "addressSpace.addressPrefixes"
            )
            if address_space is not None:
                lines.append(f"  address_space = {cls._hcl_value(address_space)}")
                consumed_properties.update({"address_space", "addressSpace"})
        elif terraform_type == "azurerm_subnet":
            address_prefixes = cls._first_property(
                properties, "address_prefixes", "addressPrefix", "addressPrefixes"
            )
            if address_prefixes is not None:
                if not isinstance(address_prefixes, list):
                    address_prefixes = [address_prefixes]
                lines.append(
                    f"  address_prefixes = {cls._hcl_value(address_prefixes)}"
                )
                consumed_properties.update(
                    {"address_prefixes", "addressPrefix", "addressPrefixes"}
                )
        elif terraform_type in {
            "azurerm_windows_virtual_machine",
            "azurerm_linux_virtual_machine",
        }:
            size = (resource.sku or {}).get("name") or properties.get("size")
            if size:
                size_path = ("sku", "name") if (resource.sku or {}).get("name") else ("size",)
                lines.append(
                    f"  size = {cls._hcl_value(size, resource.id, size_path, secret_variables)}"
                )
                consumed_properties.add("size")

        for key in sorted(properties):
            if key in consumed_properties:
                continue
            terraform_key = property_map.get(key, cls._terraform_attribute_name(key))
            value = cls._hcl_value(
                properties[key],
                resource.id,
                (str(key),),
                secret_variables,
            )
            lines.extend(cls._attribute_lines(terraform_key, value))

        for key in sorted(resource.sku or {}):
            if key not in sku_property_map:
                continue
            terraform_key = sku_property_map[key]
            value = cls._hcl_value(
                resource.sku[key],
                resource.id,
                ("sku", str(key)),
                secret_variables,
            )
            lines.extend(cls._attribute_lines(terraform_key, value))

        if resource.tags:
            lines.extend(
                cls._attribute_lines(
                    "tags",
                    cls._hcl_map(
                        resource.tags,
                        resource.id,
                        ("tags",),
                        secret_variables,
                    ),
                )
            )

        lines.append("}")
        return "\n".join(lines)

    @classmethod
    def _reference_attributes(
        cls,
        resource: Resource,
        terraform_type: str,
        catalogs: Dict[str, ResourceCatalog],
        labels: Dict[UUID, str],
        resource_by_id: Dict[UUID, Resource],
        outgoing_targets: Dict[UUID, List[UUID]],
    ) -> Tuple[List[str], Set[str]]:
        related_ids = list(outgoing_targets.get(resource.id, []))
        if resource.parent_resource_id:
            related_ids.append(resource.parent_resource_id)
        ancestors = cls._ancestors(resource, resource_by_id)
        related_ids.extend(item.id for item in ancestors)
        targets = [
            resource_by_id[target_id]
            for target_id in dict.fromkeys(related_ids)
            if target_id in resource_by_id and target_id in labels
        ]

        def references(terraform_suffix: str) -> List[str]:
            values = []
            for target in targets:
                target_catalog = catalogs.get(target.resource_type)
                target_mapping = target_catalog.terraform_mapping if target_catalog else None
                target_type = (
                    target_mapping.get("terraform_type")
                    if isinstance(target_mapping, dict)
                    else None
                )
                if target_type and target_type.endswith(terraform_suffix):
                    values.append(f"{target_type}.{labels[target.id]}")
            return sorted(set(values))

        lines: List[str] = []
        consumed: Set[str] = set()
        resource_groups = references("resource_group")
        virtual_networks = references("virtual_network")
        subnets = references("subnet")
        network_interfaces = references("network_interface")
        service_plans = references("service_plan") + references("app_service_plan")

        if terraform_type != "azurerm_resource_group" and resource_groups:
            lines.append(f"resource_group_name = {resource_groups[0]}.name")
        if terraform_type == "azurerm_subnet" and virtual_networks:
            lines.append(f"virtual_network_name = {virtual_networks[0]}.name")
        if terraform_type == "azurerm_network_interface" and subnets:
            lines.extend(
                [
                    "ip_configuration {",
                    f'  name                          = "primary"',
                    f"  subnet_id                     = {subnets[0]}.id",
                    '  private_ip_address_allocation = "Dynamic"',
                    "}",
                ]
            )
        if terraform_type in {
            "azurerm_windows_virtual_machine",
            "azurerm_linux_virtual_machine",
        } and network_interfaces:
            refs = ", ".join(f"{item}.id" for item in network_interfaces)
            lines.append(f"network_interface_ids = [{refs}]")
        if terraform_type in {
            "azurerm_linux_web_app",
            "azurerm_windows_web_app",
            "azurerm_app_service",
        } and service_plans:
            attribute = (
                "app_service_plan_id"
                if terraform_type == "azurerm_app_service"
                else "service_plan_id"
            )
            lines.append(f"{attribute} = {service_plans[0]}.id")
        return lines, consumed

    @staticmethod
    def _ancestors(
        resource: Resource, resource_by_id: Dict[UUID, Resource]
    ) -> List[Resource]:
        ancestors = []
        seen: Set[UUID] = set()
        parent_id = resource.parent_resource_id
        while parent_id and parent_id not in seen:
            seen.add(parent_id)
            parent = resource_by_id.get(parent_id)
            if parent is None:
                break
            ancestors.append(parent)
            parent_id = parent.parent_resource_id
        return ancestors

    @classmethod
    def _resource_snapshots(cls, db: Session, version_id: UUID) -> Dict[str, dict]:
        resources = (
            db.query(Resource)
            .filter(Resource.architecture_version_id == version_id)
            .order_by(Resource.resource_key)
            .all()
        )
        relationships = (
            db.query(Relationship)
            .filter(Relationship.architecture_version_id == version_id)
            .all()
        )
        dependencies = (
            db.query(Dependency)
            .filter(Dependency.architecture_version_id == version_id)
            .all()
        )
        key_by_id = {resource.id: resource.resource_key for resource in resources}
        outgoing_relationships: Dict[UUID, List[Tuple[str, str]]] = defaultdict(list)
        outgoing_dependencies: Dict[UUID, List[Tuple[str, bool, str]]] = defaultdict(list)
        for relationship in relationships:
            outgoing_relationships[relationship.source_resource_id].append(
                (
                    relationship.relationship_type,
                    key_by_id.get(relationship.target_resource_id, ""),
                )
            )
        for dependency in dependencies:
            outgoing_dependencies[dependency.resource_id].append(
                (
                    dependency.dependency_type,
                    dependency.required,
                    key_by_id.get(dependency.depends_on_resource_id, ""),
                )
            )
        return {
            resource.resource_key: {
                "id": resource.id,
                "resource_type": resource.resource_type,
                "name": resource.name,
                "location": resource.location,
                "sku": resource.sku,
                "properties": resource.properties,
                "tags": resource.tags,
                "parent": key_by_id.get(resource.parent_resource_id),
                "relationships": sorted(outgoing_relationships[resource.id]),
                "dependencies": sorted(outgoing_dependencies[resource.id]),
            }
            for resource in resources
        }

    @staticmethod
    def _comparable_snapshot(snapshot: dict) -> dict:
        """Exclude persistence identity when comparing architecture versions."""
        return {key: value for key, value in snapshot.items() if key != "id"}

    @classmethod
    def _hcl_value(
        cls,
        value: Any,
        resource_id: Optional[UUID] = None,
        path: Tuple[str, ...] = (),
        secret_variables: Optional[Dict[Tuple[UUID, Tuple[str, ...]], str]] = None,
    ) -> str:
        if (
            resource_id is not None
            and secret_variables is not None
            and (resource_id, path) in secret_variables
        ):
            return f"var.{secret_variables[(resource_id, path)]}"
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str):
            return json.dumps(value.replace("${", "$${").replace("%{", "%%{"))
        if isinstance(value, list):
            rendered = [
                cls._hcl_value(
                    item,
                    resource_id,
                    path + (str(index),),
                    secret_variables,
                )
                for index, item in enumerate(value)
            ]
            return f"[{', '.join(rendered)}]"
        if isinstance(value, dict):
            rendered = []
            for key in sorted(value):
                child = cls._hcl_value(
                    value[key],
                    resource_id,
                    path + (str(key),),
                    secret_variables,
                )
                rendered.append(f"{cls._terraform_attribute_name(str(key))} = {child}")
            return "{ " + ", ".join(rendered) + " }"
        return json.dumps(str(value))

    @classmethod
    def _hcl_map(
        cls,
        value: dict,
        resource_id: Optional[UUID] = None,
        path: Tuple[str, ...] = (),
        secret_variables: Optional[Dict[Tuple[UUID, Tuple[str, ...]], str]] = None,
    ) -> str:
        rendered = []
        for key in sorted(value):
            child = cls._hcl_value(
                value[key],
                resource_id,
                path + (str(key),),
                secret_variables,
            )
            rendered.append(f"{json.dumps(str(key))} = {child}")
        return "{ " + ", ".join(rendered) + " }"

    @staticmethod
    def _attribute_lines(name: str, value: str) -> List[str]:
        return [f"  {name} = {value}"]

    @staticmethod
    def _first_property(properties: dict, *paths: str) -> Any:
        for path in paths:
            current: Any = properties
            found = True
            for part in path.split("."):
                if not isinstance(current, dict) or part not in current:
                    found = False
                    break
                current = current[part]
            if found:
                return current
        return None

    @staticmethod
    def _terraform_attribute_name(value: str) -> str:
        value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
        value = re.sub(r"[^0-9A-Za-z_]", "_", value).lower()
        return re.sub(r"_+", "_", value).strip("_") or "value"

    @classmethod
    def _is_secret_key(cls, key: str) -> bool:
        normalized = cls._terraform_attribute_name(key)
        return normalized in cls._SECRET_NAMES or any(
            normalized.endswith(f"_{suffix}")
            for suffix in cls._SECRET_SUFFIXES
        )

    @staticmethod
    def _special_property_keys(terraform_type: str) -> Set[str]:
        if terraform_type == "azurerm_virtual_network":
            return {"address_space", "addressSpace"}
        if terraform_type == "azurerm_subnet":
            return {"address_prefixes", "addressPrefix", "addressPrefixes"}
        if terraform_type in {
            "azurerm_windows_virtual_machine",
            "azurerm_linux_virtual_machine",
        }:
            return {"size"}
        return set()

    @staticmethod
    def _has_safe_configured_path(mapping: dict) -> bool:
        additional = mapping.get("additional_mapping") or {}
        configured_path = additional.get("file_path")
        if configured_path is None:
            return True
        normalized = str(configured_path).replace("\\", "/")
        parts = normalized.split("/")
        return (
            bool(normalized)
            and not normalized.startswith("/")
            and ":" not in normalized
            and all(part not in {"", ".", ".."} for part in parts)
            and normalized.endswith(".tf")
        )

    @staticmethod
    def _escape(value: str) -> str:
        return (
            value.replace("\\", "\\\\")
            .replace("${", "$${")
            .replace("%{", "%%{")
            .replace('"', '\\"')
        )

    @staticmethod
    def _finding(
        code: str,
        severity: str,
        message: str,
        resource: Optional[Resource] = None,
        details: Optional[dict] = None,
    ) -> dict:
        return {
            "code": code,
            "severity": severity,
            "message": message,
            "resource_id": resource.id if resource else None,
            "resource_type": resource.resource_type if resource else None,
            "details": details,
        }

    @classmethod
    def _blocked_result(
        cls,
        architecture_id: UUID,
        version_id: UUID,
        validation: dict,
        errors: List[dict],
        unsupported: Optional[List[UUID]] = None,
    ) -> dict:
        return {
            "architecture_id": architecture_id,
            "architecture_version_id": version_id,
            "generator_version": cls.GENERATOR_VERSION,
            "status": TerraformGenerationStatus.BLOCKED.value,
            "validation_status": validation["status"],
            "validation_findings": validation["findings"],
            "files": [],
            "warnings": [],
            "errors": errors,
            "resources_processed": 0,
            "resources_unsupported": unsupported or [],
            "changed_files": [],
        }
