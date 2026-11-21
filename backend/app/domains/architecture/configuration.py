"""Controlled Azure design-configuration metadata for the Architecture Studio."""

from copy import deepcopy

from app.domains.architecture.catalog import AZURE_RESOURCE_CATALOG


def _field(name, label, field_type="text", *, description=None, required=False, options=None,
          storage_key=None, pricing=False, networking=False, relationship=False,
          read_only=False, depends_on=None, reference=None, section=None):
    inferred_section = section or (
        "Compute" if name in {"sku", "tier", "instance_count", "vm_size", "service_tier", "compute_model", "compute_size", "performance", "replication", "account_kind"}
        else "Runtime" if name in {"operating_system", "runtime_stack", "runtime_version", "image_reference"}
        else "Networking" if networking or name in {"address_space", "dns_servers", "address_prefix", "service_endpoints", "delegation"}
        else "Security" if name in {"managed_identity_enabled", "public_network_access", "soft_delete_enabled", "purge_protection_enabled", "secure_transfer_required"}
        else "Dependencies" if relationship or name in {"server_resource_id", "os_disk", "network_interface", "availability_configuration"}
        else "General"
    )
    item = {
        "name": name,
        "label": label,
        "section": inferred_section,
        "field_type": field_type,
        "description": description,
        "required": required,
        "options": options or [],
        "storage_key": storage_key or name,
        "affects_pricing": pricing,
        "affects_networking": networking,
        "affects_relationships": relationship,
        "read_only": read_only,
        "depends_on": depends_on,
        "reference": reference,
    }
    return item


_COMMON = [
    _field("name", "Name", required=True, storage_key="__name__"),
    _field("location", "Region", storage_key="__location__", networking=True),
    _field("tags", "Tags", "tags", storage_key="tags"),
]


_CONFIGURATION_OVERRIDES = {
    "appservice": [
        _field("plan_resource_id", "App Service Plan", "searchable_select", relationship=True,
               networking=True, description="Select a compatible plan by stable resource ID.", storage_key="plan_resource_id"),
        _field("sku", "SKU", "select", options=["F1", "B1", "S1", "S2", "P1v3"], pricing=True),
        _field("tier", "Tier", "select", options=["Free", "Basic", "Standard", "Premium"], pricing=True),
        _field("instance_count", "Instance count", "number", pricing=True),
        _field("operating_system", "Operating System", "select", options=["Linux", "Windows"], storage_key="operating_system"),
        _field("runtime_stack", "Runtime Stack", "select", options=["Node.js", "Python", ".NET", "Java", "PHP"], depends_on="operating_system"),
        _field("runtime_version", "Runtime Version", "text", depends_on="runtime_stack"),
        _field("vnet_integration_resource_id", "VNet Integration", "searchable_select", networking=True, relationship=True),
        _field("private_endpoint_enabled", "Private Endpoint", "boolean", networking=True, relationship=True),
        _field("public_network_access", "Public Network Access", "select", options=["Enabled", "Disabled"], networking=True),
        _field("managed_identity_enabled", "Managed Identity", "boolean"),
        _field("key_vault_resource_id", "Key Vault", "searchable_select", relationship=True),
    ],
    "appserviceplan": [
        _field("sku", "SKU", "select", options=["F1", "B1", "S1", "S2", "P1v3"], pricing=True),
        _field("tier", "Tier", "select", options=["Free", "Basic", "Standard", "Premium"], pricing=True),
        _field("operating_system", "Operating System", "select", options=["Linux", "Windows"]),
        _field("instance_count", "Capacity", "number", pricing=True),
    ],
    "vm": [
        _field("vm_size", "VM Size", "text", pricing=True, description="Authoritative VM size metadata is not currently available."),
        _field("operating_system", "Operating System", "select", options=["Linux", "Windows"]),
        _field("image_reference", "Image Reference", "text"),
        _field("os_disk", "OS Disk", "structured_object"),
        _field("availability_configuration", "Availability", "text"),
        _field("vnet_resource_id", "VNet", "searchable_select", networking=True, relationship=True),
        _field("subnet_resource_id", "Subnet", "searchable_select", networking=True, relationship=True),
        _field("network_interface", "Network Interface", "text", networking=True),
        _field("public_ip_resource_id", "Public IP", "searchable_select", networking=True, relationship=True),
    ],
    "sql": [
        _field("server_resource_id", "Server", "searchable_select", relationship=True),
        _field("service_tier", "Service Tier", "select", options=["General Purpose", "Business Critical", "Hyperscale"], pricing=True),
        _field("compute_model", "Compute Model", "select", options=["DTU", "vCore"], pricing=True, depends_on="service_tier"),
        _field("compute_size", "Compute Size", "text", pricing=True, depends_on="compute_model"),
        _field("storage_size_gb", "Storage Size (GB)", "number", pricing=True),
        _field("public_network_access", "Public Network Access", "select", options=["Enabled", "Disabled"], networking=True),
        _field("private_endpoint_enabled", "Private Endpoint", "boolean", networking=True, relationship=True),
        _field("backup", "Backup Configuration", "structured_object"),
    ],
    "storage": [
        _field("account_kind", "Account Kind", "select", options=["StorageV2", "BlobStorage", "FileStorage"]),
        _field("performance", "Performance", "select", options=["Standard", "Premium"], pricing=True),
        _field("replication", "Replication", "select", options=["LRS", "ZRS", "GRS", "GZRS"], pricing=True),
        _field("public_network_access", "Public Network Access", "select", options=["Enabled", "Disabled"], networking=True),
        _field("secure_transfer_required", "Secure Transfer Required", "boolean", networking=True),
        _field("private_endpoint_enabled", "Private Endpoint", "boolean", networking=True, relationship=True),
    ],
    "keyvault": [
        _field("sku", "SKU", "select", options=["Standard", "Premium"], pricing=True),
        _field("public_network_access", "Public Network Access", "select", options=["Enabled", "Disabled"], networking=True),
        _field("private_endpoint_enabled", "Private Endpoint", "boolean", networking=True, relationship=True),
        _field("soft_delete_enabled", "Soft Delete", "boolean"),
        _field("purge_protection_enabled", "Purge Protection", "boolean"),
        _field("managed_identity_enabled", "Managed Identity", "boolean"),
    ],
    "vnet": [
        _field("address_space", "Address Space", "multi_select", description="CIDR ranges for the virtual network.", networking=True),
        _field("dns_servers", "DNS Servers", "multi_select", networking=True),
    ],
    "subnet": [
        _field("address_prefix", "Address Prefix", networking=True),
        _field("service_endpoints", "Service Endpoints", "multi_select", networking=True),
        _field("delegation", "Delegation", networking=True),
        _field("network_security_group_resource_id", "Network Security Group", "searchable_select", networking=True, relationship=True),
    ],
}


def _default_fields(resource_type: str):
    return deepcopy(_COMMON)


AZURE_RESOURCE_CONFIGURATION = {
    item["resource_type"]: {
        "resource_type": item["resource_type"],
        "display_name": item["display_name"],
        "fields": _default_fields(item["resource_type"]) + deepcopy(_CONFIGURATION_OVERRIDES.get(item["resource_type"], [])),
        "configuration_status": "modeled" if item["resource_type"] in _CONFIGURATION_OVERRIDES else "common_properties_only",
        "reference": "https://learn.microsoft.com/azure/architecture/",
    }
    for item in AZURE_RESOURCE_CATALOG
}


def get_resource_configuration(resource_type: str) -> dict:
    return AZURE_RESOURCE_CONFIGURATION.get(resource_type, {
        "resource_type": resource_type,
        "display_name": resource_type,
        "fields": [],
        "configuration_status": "unknown",
        "reference": "https://learn.microsoft.com/azure/architecture/",
    })
