"""Read-only validation and review artifacts for a saved Azure architecture."""

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from ipaddress import ip_network
from typing import Annotated, Literal
from uuid import UUID
from xml.etree import ElementTree as ET

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.access.routes import client_access, get_db
from app.domains.architecture.catalog import CATALOG_BY_RESOURCE_TYPE, classify_relationship_rule
from app.domains.architecture.configuration import get_resource_configuration
from app.domains.architecture.models import (
    Architecture,
    ArchitectureRelationship,
    ArchitectureResource,
    AzureResourceGroup,
    AzureSubscription,
)
from app.domains.architecture.routes import get_architecture_or_404

router = APIRouter(dependencies=[Depends(client_access)])
Name = Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.+-]*$")]
ServiceName = Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.@-]*$")]


class ServiceSetting(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ServiceName
    enabled: StrictBool
    state: Literal["started", "stopped"]


class AnsibleSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packages: list[Name] = Field(default_factory=list, max_length=50)
    services: list[ServiceSetting] = Field(default_factory=list, max_length=50)


class Finding(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    resource_id: UUID | None = None


class ValidationReport(BaseModel):
    findings: list[Finding]


@dataclass
class DesignGraph:
    architecture: Architecture
    subscriptions: list[AzureSubscription]
    groups: dict[UUID, AzureResourceGroup]
    resources: dict[UUID, ArchitectureResource]
    relationships: list[ArchitectureRelationship]


async def load_graph(db: AsyncSession, architecture_id: UUID) -> DesignGraph:
    architecture = await get_architecture_or_404(db, architecture_id)
    subscriptions = await db.scalars(select(AzureSubscription).where(
        AzureSubscription.architecture_id == architecture_id).order_by(AzureSubscription.id))
    groups = await db.scalars(select(AzureResourceGroup).where(
        AzureResourceGroup.architecture_id == architecture_id).order_by(AzureResourceGroup.id))
    resources = await db.scalars(select(ArchitectureResource).where(
        ArchitectureResource.architecture_id == architecture_id).order_by(ArchitectureResource.id))
    edges = await db.scalars(select(ArchitectureRelationship).where(
        ArchitectureRelationship.architecture_id == architecture_id).order_by(ArchitectureRelationship.id))
    return DesignGraph(architecture, list(subscriptions), {group.id: group for group in groups},
                       {resource.id: resource for resource in resources}, list(edges))


def network_ranges(value, *, single=False):
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list) or not values or len(values) > 64 or (single and len(values) != 1):
        return []
    try:
        if any(not isinstance(item, str) or "/" not in item for item in values):
            return []
        return [ip_network(item.strip()) for item in values]
    except ValueError:
        return []


def subnet_parent(graph: DesignGraph, subnet: ArchitectureResource):
    candidate_ids = {edge.source_resource_id for edge in graph.relationships
                     if edge.relationship_type == "contains" and edge.target_resource_id == subnet.id}
    if subnet.parent_resource_id:
        candidate_ids.add(subnet.parent_resource_id)
    candidates = [graph.resources[item_id] for item_id in candidate_ids if item_id in graph.resources
                  and graph.resources[item_id].resource_type == "vnet"]
    if len(candidates) != 1 or (subnet.parent_resource_id and candidates[0].id != subnet.parent_resource_id):
        return None
    return candidates[0]


def valid_name(name, minimum, maximum):
    return minimum <= len(name) <= maximum and bool(
        re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9_])?", name)
    )


def valid_group(group):
    return (
        bool(re.fullmatch(r"[A-Za-z0-9_.()\-]{1,90}", group.name))
        and not group.name.endswith(".")
        and bool(re.fullmatch(r"[A-Za-z0-9 ]{2,100}", group.location or ""))
        and bool((group.location or "").strip())
    )


def validation_findings(graph: DesignGraph) -> list[Finding]:
    findings = []

    def add(code, message, item_id=None, severity="error"):
        findings.append(Finding(severity=severity, code=code, message=message, resource_id=item_id))

    group_names = Counter(group.name.casefold() for group in graph.groups.values())
    for group in graph.groups.values():
        if not valid_group(group):
            add("invalid_resource_group", "Set a valid resource group name and Azure region.", group.id)
        if group_names[group.name.casefold()] > 1:
            add("duplicate_resource_group", "Use distinct resource group names for Terraform export.", group.id)

    vnet_names = Counter((item.resource_group_id, item.name.casefold())
                         for item in graph.resources.values() if item.resource_type == "vnet")
    subnets_by_vnet = {}
    linked_types = {item.id: set() for item in graph.resources.values()}
    for edge in graph.relationships:
        source = graph.resources.get(edge.source_resource_id)
        target = graph.resources.get(edge.target_resource_id)
        if source and target and edge.relationship_type in {"contains", "deployed_in", "depends_on"}:
            linked_types[source.id].add(target.resource_type)
            linked_types[target.id].add(source.resource_type)
    for item in graph.resources.values():
        configuration = get_resource_configuration(item.resource_type)
        if configuration["configuration_status"] == "common_properties_only":
            add("configuration_coverage", "Review resource-specific settings manually.", item.id, "warning")
        catalog_item = CATALOG_BY_RESOURCE_TYPE.get(item.resource_type, {})
        group = graph.groups.get(item.resource_group_id)
        if catalog_item.get("requires_resource_group") and not group:
            add("missing_resource_group", "Place the resource in a resource group.", item.id)
        if catalog_item.get("requires_location") and not (item.location or (group and group.location)):
            add("missing_azure_region", "Set an Azure region on the resource or its group.", item.id)
        parent = graph.resources.get(item.parent_resource_id)
        resolved_types = linked_types[item.id] | ({parent.resource_type} if parent else set())
        if item.resource_type not in {"vnet", "subnet"}:
            required = set(catalog_item.get("required_dependencies", ())) - {"resource_group"} - resolved_types
            if required:
                add("required_dependencies", f"Connect required resources: {', '.join(sorted(required))}.", item.id, "warning")
            if catalog_item.get("requires_subnet") and "subnet" not in resolved_types:
                add("missing_required_subnet", "Associate the resource with an appropriate subnet.", item.id, "warning")
        if item.resource_type == "vnet":
            if not valid_name(item.name, 2, 64):
                add("invalid_vnet_name", "Set an Azure virtual network name of 2 to 64 valid characters.", item.id)
            if vnet_names[(item.resource_group_id, item.name.casefold())] > 1:
                add("duplicate_vnet", "Use distinct virtual network names within this resource group.", item.id)
            ranges = network_ranges(item.properties.get("address_space"))
            if not ranges:
                add("invalid_vnet_cidr", "Set one or more valid, aligned virtual network CIDR blocks.", item.id)
            elif any(first.overlaps(second) for index, first in enumerate(ranges) for second in ranges[index + 1:]):
                add("overlapping_vnet_ranges", "Remove overlapping virtual network address spaces.", item.id)
        if item.resource_type == "subnet":
            if not valid_name(item.name, 1, 80):
                add("invalid_subnet_name", "Set an Azure subnet name of 1 to 80 valid characters.", item.id)
            parent = subnet_parent(graph, item)
            if parent is None or parent.resource_group_id != item.resource_group_id:
                add("missing_subnet_vnet", "Place the subnet in exactly one virtual network in the same resource group.", item.id)
            ranges = network_ranges(item.properties.get("address_prefix"), single=True)
            if not ranges:
                add("invalid_subnet_cidr", "Set one valid, aligned subnet CIDR block.", item.id)
            if parent and ranges:
                if not any(ranges[0].version == block.version and ranges[0].subnet_of(block)
                           for block in network_ranges(parent.properties.get("address_space"))):
                    add("subnet_outside_vnet", "Set a subnet CIDR within its virtual network address space.", item.id)
                subnets_by_vnet.setdefault(parent.id, []).append((item, ranges[0]))

    for subnets in subnets_by_vnet.values():
        for index, (item, address) in enumerate(subnets):
            for other, other_address in subnets[index + 1:]:
                if item.name.casefold() == other.name.casefold():
                    for duplicate in (item, other):
                        add("duplicate_subnet", "Give each subnet within the virtual network a unique name.", duplicate.id)
                if address.overlaps(other_address):
                    for overlapping in (item, other):
                        add("overlapping_subnet", "Use distinct, non-overlapping CIDRs for adjacent subnets.", overlapping.id)

    for edge in graph.relationships:
        source = graph.resources.get(edge.source_resource_id)
        target = graph.resources.get(edge.target_resource_id)
        if source is None or target is None or source.id == target.id:
            add("invalid_relationship_endpoints", "Replace the relationship with two existing and distinct resources.")
            continue
        rule = classify_relationship_rule(source.resource_type, target.resource_type, edge.relationship_type)
        if rule["status"] != "VALID":
            add(f"relationship_{rule['status'].lower()}", rule["reason"], source.id,
                "warning" if rule["valid"] else "error")

    return list({(finding.code, finding.resource_id): finding for finding in findings}.values())


def finite_position(value: float) -> float:
    return value if math.isfinite(value) else 0


def export_properties(item: ArchitectureResource, resources: dict[UUID, ArchitectureResource]) -> dict:
    # Explicitly export typed fields. Source properties and freeform configuration
    # may also contain discovery metadata or user-provided credential material.
    fields = get_resource_configuration(item.resource_type)["fields"]
    values = {}
    for field in fields:
        key = field["storage_key"]
        value = item.properties.get(key)
        if key in {"address_space", "address_prefix"}:
            ranges = network_ranges(value, single=(key == "address_prefix"))
            if ranges:
                values[key] = str(ranges[0]) if key == "address_prefix" else [str(item) for item in ranges]
        elif field["options"] and value in field["options"]:
            values[key] = value
        elif field["field_type"] == "searchable_select" and isinstance(value, str):
            try:
                resource_id = UUID(value)
            except ValueError:
                continue
            if resource_id in resources:
                values[key] = str(resource_id)
        elif field["field_type"] == "boolean" and isinstance(value, bool):
            values[key] = value
        elif field["field_type"] == "number" and type(value) in (int, float) and abs(value) <= 1e12:
            values[key] = value
    return values


def definition(graph: DesignGraph) -> dict:
    design = graph.architecture
    return {
        "schema_version": 1,
        "scope": "Design definition with typed configuration fields only",
        "architecture": {
            "id": str(design.id), "name": design.name, "provider": design.provider,
            "project": design.project, "environment": design.environment, "status": design.status,
            "default_region": design.default_region,
        },
        "subscription_contexts": [
            {"id": str(item.id), "name": item.name, "environment": item.environment}
            for item in graph.subscriptions
        ],
        "resource_groups": [
            {"id": str(group.id), "name": group.name, "location": group.location,
             "subscription_context_id": str(group.subscription_id) if group.subscription_id else None,
             "position_x": finite_position(group.position_x), "position_y": finite_position(group.position_y)}
            for group in graph.groups.values()
        ],
        "resources": [
            {"id": str(item.id), "name": item.name, "resource_type": item.resource_type,
             "location": item.location, "resource_group_id": str(item.resource_group_id) if item.resource_group_id else None,
             "parent_resource_id": str(item.parent_resource_id) if item.parent_resource_id else None,
             "position_x": finite_position(item.position_x), "position_y": finite_position(item.position_y),
             "properties": export_properties(item, graph.resources)}
            for item in graph.resources.values()
        ],
        "relationships": [
            {"source_resource_id": str(edge.source_resource_id), "target_resource_id": str(edge.target_resource_id),
             "relationship_type": edge.relationship_type}
            for edge in graph.relationships
            if edge.source_resource_id in graph.resources and edge.target_resource_id in graph.resources
        ],
    }


def xml_text(value: str) -> str:
    return re.sub(r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]", "", value)


def diagram(graph: DesignGraph) -> bytes:
    # A topology overview in a compact grid. Definition JSON retains canvas positions.
    items = list(graph.resources.values())
    positions = {item.id: (24 + index % 4 * 224, 70 + index // 4 * 90)
                 for index, item in enumerate(items)}
    height = 90 + max(1, (len(items) + 3) // 4) * 90
    svg = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "viewBox": f"0 0 920 {height}",
                             "role": "img", "aria-labelledby": "diagram-title"})
    ET.SubElement(svg, "title", {"id": "diagram-title"}).text = xml_text(graph.architecture.name)
    ET.SubElement(svg, "rect", {"width": "920", "height": str(height), "fill": "#f3f7fb"})
    ET.SubElement(svg, "text", {"x": "24", "y": "35", "font-family": "sans-serif",
                                "font-size": "22", "fill": "#102845"}).text = xml_text(graph.architecture.name[:74])
    if not items:
        ET.SubElement(svg, "text", {"x": "24", "y": "88", "font-family": "sans-serif"}).text = "No resources"
    connections = {(edge.source_resource_id, edge.target_resource_id) for edge in graph.relationships}
    connections.update((item.parent_resource_id, item.id) for item in items if item.parent_resource_id)
    for source_id, target_id in sorted(connections):
        if source_id in positions and target_id in positions:
            start_x, start_y = positions[source_id]
            end_x, end_y = positions[target_id]
            ET.SubElement(svg, "line", {"x1": str(start_x + 100), "y1": str(start_y + 26),
                                       "x2": str(end_x + 100), "y2": str(end_y + 26),
                                       "stroke": "#557aa0", "stroke-width": "2"})
    for item in items:
        x, y = positions[item.id]
        ET.SubElement(svg, "rect", {"x": str(x), "y": str(y), "width": "200", "height": "54",
                                   "rx": "5", "fill": "#fff", "stroke": "#054d82"})
        ET.SubElement(svg, "text", {"x": str(x + 10), "y": str(y + 22), "font-family": "sans-serif",
                                    "font-size": "14", "fill": "#102845"}).text = xml_text(item.name[:25])
        ET.SubElement(svg, "text", {"x": str(x + 10), "y": str(y + 41), "font-family": "sans-serif",
                                    "font-size": "12", "fill": "#375d82"}).text = xml_text(item.resource_type[:28])
    return ET.tostring(svg, encoding="utf-8", xml_declaration=True)


def tf_address(prefix: str, item_id: UUID) -> str:
    return f"{prefix}_{item_id.hex}"


def tf_literal(value: str) -> str:
    return value.replace("${", "$${").replace("%{", "%%{")


def terraform(graph: DesignGraph) -> dict:
    subscription_ids = {item.subscription_id for item in graph.groups.values() if item.subscription_id is not None}
    if len(subscription_ids) > 1:
        raise HTTPException(422, "Use a single subscription context in the design for Terraform export.")
    errors = {finding.resource_id for finding in validation_findings(graph) if finding.severity == "error"}
    groups, vnets, subnets = {}, {}, {}
    omitted = []
    for group in graph.groups.values():
        if group.id in errors:
            omitted.append({"id": str(group.id), "type": "resource_group", "reason": "Resolve validation findings."})
            continue
        groups[tf_address("rg", group.id)] = {"name": tf_literal(group.name), "location": tf_literal(group.location)}
    if not groups:
        raise HTTPException(422, "Add a valid resource group before exporting Terraform.")

    for item in graph.resources.values():
        if item.resource_type == "subnet":
            continue
        if item.resource_type != "vnet":
            omitted.append({"id": str(item.id), "type": tf_literal(item.resource_type), "reason": "Unsupported resource type."})
            continue
        group = tf_address("rg", item.resource_group_id) if item.resource_group_id else ""
        if item.id in errors or group not in groups:
            omitted.append({"id": str(item.id), "type": "vnet", "reason": "Resolve validation findings or the missing group."})
            continue
        location = item.location.strip() if item.location else ""
        if location and not re.fullmatch(r"[A-Za-z0-9 ]{2,100}", location):
            omitted.append({"id": str(item.id), "type": "vnet", "reason": "Set a valid Azure location."})
            continue
        vnets[tf_address("vnet", item.id)] = {
            "name": tf_literal(item.name), "location": location or f"${{azurerm_resource_group.{group}.location}}",
            "resource_group_name": f"${{azurerm_resource_group.{group}.name}}",
            "address_space": [str(block) for block in network_ranges(item.properties.get("address_space"))],
        }

    for item in graph.resources.values():
        if item.resource_type != "subnet":
            continue
        parent = subnet_parent(graph, item)
        vnet = tf_address("vnet", parent.id) if parent else ""
        if item.id in errors or vnet not in vnets:
            omitted.append({"id": str(item.id), "type": "subnet", "reason": "Resolve validation findings or the missing parent network."})
            continue
        subnets[tf_address("subnet", item.id)] = {
            "name": tf_literal(item.name),
            "resource_group_name": vnets[vnet]["resource_group_name"],
            "virtual_network_name": f"${{azurerm_virtual_network.{vnet}.name}}",
            "address_prefixes": [str(block) for block in network_ranges(item.properties.get("address_prefix"), single=True)],
            "default_outbound_access_enabled": False,
        }

    return {
        "terraform": {"required_providers": {"azurerm": {"source": "hashicorp/azurerm", "version": "~> 4.55"}}},
        "variable": {"subscription_id": {"type": "string", "description": "Reviewed Azure subscription ID"}},
        "provider": {"azurerm": {"features": {}, "subscription_id": "${var.subscription_id}",
                                 "resource_provider_registrations": "none"}},
        "resource": {name: items for name, items in (
            ("azurerm_resource_group", groups), ("azurerm_virtual_network", vnets), ("azurerm_subnet", subnets)
        ) if items},
        "output": {"monitorai_export_scope": {"value": {
            "scope": "Review only. Applies to one subscription and includes basic network geometry only.",
            "limitations": "Review DNS, NSGs, routes, tags, service endpoints, delegation and other settings separately.",
            "omitted_resources": omitted,
        }}},
    }


def download(content: bytes | str, filename: str, media_type: str) -> Response:
    return Response(content=content, media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
    })


@router.get("/{architecture_id}/validation", response_model=ValidationReport)
async def validate_design(architecture_id: UUID, db: AsyncSession = Depends(get_db)):
    return ValidationReport(findings=validation_findings(await load_graph(db, architecture_id)))


@router.get("/{architecture_id}/exports/{format}")
async def export_design(architecture_id: UUID, format: Literal["definition", "diagram", "terraform"],
                        db: AsyncSession = Depends(get_db)):
    graph = await load_graph(db, architecture_id)
    if format == "diagram":
        return download(diagram(graph), "architecture.svg", "image/svg+xml")
    if format == "terraform":
        return download(json.dumps(terraform(graph), indent=2), "main.tf.json", "application/json")
    return download(json.dumps(definition(graph), indent=2), "architecture.json", "application/json")


@router.post("/{architecture_id}/exports/ansible")
async def export_ansible(architecture_id: UUID, settings: AnsibleSettings, db: AsyncSession = Depends(get_db)):
    await get_architecture_or_404(db, architecture_id)
    if not settings.packages and not settings.services:
        raise HTTPException(422, "Specify at least one package or service.")
    if len({service.name for service in settings.services}) != len(settings.services):
        raise HTTPException(422, "Use each service name only once.")
    tasks = [{"name": f"Install {package}", "ansible.builtin.package": {"name": package, "state": "present"}}
             for package in dict.fromkeys(settings.packages)]
    tasks.extend({"name": f"Configure {service.name}", "ansible.builtin.service": service.model_dump()}
                 for service in settings.services)
    # A JSON document is valid YAML and prevents injection into Ansible's playbook structure.
    playbook = [{"name": "Configure reviewed Linux hosts", "hosts": "azure_managed_hosts",
                 "become": True, "tasks": tasks}]
    header = "# Review package and service names for your Linux distribution. Supply your own approved inventory.\n"
    return download(header + json.dumps(playbook, indent=2) + "\n", "playbook.yml", "application/yaml")
