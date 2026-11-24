"""Collect read-only topology and configuration evidence from Azure Resource Manager."""

import asyncio
import re
from collections import Counter
from dataclasses import dataclass, field
from ipaddress import ip_address, ip_network
from uuid import UUID

import httpx

from app.domains.architecture.azure_discovery import AzureResourceDiscoveryAdapter

ARM = "https://management.azure.com"
NETWORK_API = "2025-05-01"
PRIVATE_DNS_API = "2018-09-01"
RESOURCE_LIMIT = 100
MAX_CONCURRENT_REQUESTS = 6
API_VERSIONS = {
    "virtualnetworks": NETWORK_API,
    "networksecuritygroups": NETWORK_API,
    "routetables": NETWORK_API,
    "azurefirewalls": NETWORK_API,
    "firewallpolicies": NETWORK_API,
    "applicationgateways": NETWORK_API,
    "applicationgatewaywebapplicationfirewallpolicies": NETWORK_API,
    "publicipaddresses": NETWORK_API,
    "networkinterfaces": NETWORK_API,
    "natgateways": NETWORK_API,
    "privateendpoints": NETWORK_API,
    "loadbalancers": NETWORK_API,
    "virtualnetworkgateways": NETWORK_API,
    "dnszones": "2018-05-01",
    "privatednszones": PRIVATE_DNS_API,
}
EXTRA_RESOURCE_API_VERSIONS = {"microsoft.web/sites": "2024-11-01"}
LIMITATIONS = (
    "Topology includes only relationships between collected resources in the selected subscription.",
    "Exposure indicators reflect Azure configuration. They do not establish end-to-end reachability.",
    "Routes and security rules show configured intent. Effective routes, effective rules, firewall policy rules, DNS records, and flow logs are outside this snapshot.",
    "App Service VNet integration is outbound integration; it does not establish private inbound access.",
    "Private Endpoint approval and custom DNS configuration do not prove that clients resolve or reach the private address.",
)
ARM_SEGMENT = re.compile(r"[\w().-]{1,260}", re.UNICODE)


@dataclass
class NetworkCollection:
    status: str
    failure_reason: str | None = None
    resources: list[dict] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


def scoped_resource_id(value, subscription_id: str) -> str | None:
    if not isinstance(value, str) or len(value) > 1024 or not value.startswith("/"):
        return None
    parts = value[1:].split("/")
    if len(parts) < 8 or len(parts) % 2 or parts[0].casefold() != "subscriptions":
        return None
    if parts[1].casefold() != subscription_id or parts[2].casefold() != "resourcegroups":
        return None
    if parts[4].casefold() != "providers":
        return None
    if any(not ARM_SEGMENT.fullmatch(part) or part in {".", ".."} for part in parts):
        return None
    return value


def scoped_network_id(value, subscription_id: str) -> str | None:
    scoped = scoped_resource_id(value, subscription_id)
    if not scoped:
        return None
    return scoped if scoped[1:].split("/")[5].casefold() == "microsoft.network" else None


def obj(value):
    return value if isinstance(value, dict) else {}


def rows(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def strings(value):
    return [item for item in value if isinstance(item, str) and 0 < len(item) <= 260] if isinstance(value, list) else []


def reference(value):
    return obj(value).get("id")


def string_fields(source, **fields_to_copy):
    return {
        target: source[key] for target, key in fields_to_copy.items()
        if isinstance(source.get(key), str) and 0 < len(source[key]) <= 260
    }


def parsed_addresses(values, parser):
    parsed = []
    for value in strings(values):
        try:
            parsed.append(str(parser(value)))
        except ValueError:
            continue
    return parsed


def status_reason(code):
    return {401: "authentication_failure", 403: "permission_failure"}.get(code, "provider_error")


def resource_row(item, kind, facts):
    return {
        "id": item["id"],
        "name": item["name"],
        "type": kind,
        "location": item.get("location", ""),
        "properties": facts,
    }


def child_row(parent, child, child_type, subscription_id):
    child_id = scoped_network_id(child.get("id"), subscription_id)
    prefix = f"{parent['id']}/{child_type}/"
    if not child_id or not child_id.casefold().startswith(prefix.casefold()):
        return None
    if "/" in child_id[len(prefix):]:
        return None
    return {"id": child_id, "name": child_id.rsplit("/", 1)[-1], "location": parent.get("location", "")}


def subnet_facts(props):
    prefixes = [*strings(props.get("addressPrefixes")), props.get("addressPrefix")]
    delegations = []
    for delegation in rows(props.get("delegations")):
        details = obj(delegation.get("properties"))
        delegations.append({
            **string_fields(delegation, name="name"),
            **string_fields(details, service_name="serviceName"),
            "actions": strings(details.get("actions")),
        })
    endpoints = [{
        **string_fields(endpoint, service="service"),
        "locations": strings(endpoint.get("locations")),
    } for endpoint in rows(props.get("serviceEndpoints"))]
    facts = {
        "address_prefixes": parsed_addresses(prefixes, ip_network),
        "delegations": delegations,
        "service_endpoints": endpoints,
        **string_fields(props, private_endpoint_policies="privateEndpointNetworkPolicies",
                        private_link_service_policies="privateLinkServiceNetworkPolicies", purpose="purpose"),
    }
    if isinstance(props.get("defaultOutboundAccess"), bool):
        facts["default_outbound_access"] = props["defaultOutboundAccess"]
    return facts


def security_rules(props):
    rules = []
    for rule in rows(props.get("securityRules")):
        details = obj(rule.get("properties"))
        prefixes = [*strings(details.get("sourceAddressPrefixes")), details.get("sourceAddressPrefix")]
        priority = details.get("priority")
        summary = {
            **string_fields(rule, name="name"),
            **string_fields(details, access="access", direction="direction", protocol="protocol"),
            "destination_ports": strings([*strings(details.get("destinationPortRanges")), details.get("destinationPortRange")]),
            "internet_source": any(isinstance(prefix, str) and prefix.casefold() in {"*", "internet", "0.0.0.0/0", "::/0"}
                                   for prefix in prefixes),
        }
        if type(priority) is int:
            summary["priority"] = priority
        rules.append(summary)
    return rules


def route_rows(props):
    routes = []
    for route in rows(props.get("routes")):
        details = obj(route.get("properties"))
        routes.append({
            **string_fields(route, name="name"),
            **string_fields(details, destination="addressPrefix", next_hop_type="nextHopType"),
            "next_hop_addresses": parsed_addresses([details.get("nextHopIpAddress")], ip_address),
        })
    return routes


def project_network_resource(item, payload, kind, subscription_id):
    """Keep only selected network facts and same-subscription link endpoints."""
    props = obj(payload.get("properties"))
    facts = {}
    children, links = [], []

    def link(source, target, relation):
        target_id = scoped_network_id(target, subscription_id)
        if target_id:
            links.append((source, target_id, relation))

    def link_resource(source, target, relation):
        target_id = scoped_resource_id(target, subscription_id)
        if target_id:
            links.append((source, target_id, relation))

    def references(source, details, fields):
        for key, relation in fields:
            link(source, reference(details.get(key)), relation)

    resource_id = item["id"]
    if kind == "virtualnetworks":
        facts["address_spaces"] = parsed_addresses(obj(props.get("addressSpace")).get("addressPrefixes"), ip_network)
        facts["dns_servers"] = parsed_addresses(obj(props.get("dhcpOptions")).get("dnsServers"), ip_address)
        for child in rows(props.get("subnets")):
            subnet = child_row(item, child, "subnets", subscription_id)
            if subnet is None:
                continue
            details = obj(child.get("properties"))
            children.append(resource_row(subnet, "microsoft.network/virtualnetworks/subnets", subnet_facts(details)))
            link(resource_id, subnet["id"], "contains")
            references(subnet["id"], details, (
                ("networkSecurityGroup", "protected_by"), ("routeTable", "uses_route_table"),
                ("natGateway", "uses_nat_gateway"),
            ))
            for private_endpoint in rows(details.get("privateEndpoints")):
                link(reference(private_endpoint), subnet["id"], "attached_to_subnet")
        for peering in rows(props.get("virtualNetworkPeerings")):
            detail = obj(peering.get("properties"))
            relation = "peered_with" if str(detail.get("peeringState", "")).casefold() == "connected" else "peering_configured"
            link(resource_id, reference(detail.get("remoteVirtualNetwork")), relation)
    elif kind == "networksecuritygroups":
        rules = security_rules(props)
        facts = {
            "custom_rules": rules,
            "internet_inbound_allow_rules": sum(
                rule.get("internet_source") and rule.get("direction", "").casefold() == "inbound"
                and rule.get("access", "").casefold() == "allow" for rule in rules
            ),
        }
        for subnet in rows(props.get("subnets")):
            link(reference(subnet), resource_id, "protected_by")
        for interface in rows(props.get("networkInterfaces")):
            link(reference(interface), resource_id, "protected_by")
    elif kind == "routetables":
        facts["routes"] = route_rows(props)
        if isinstance(props.get("disableBgpRoutePropagation"), bool):
            facts["bgp_route_propagation_enabled"] = not props["disableBgpRoutePropagation"]
        for subnet in rows(props.get("subnets")):
            link(reference(subnet), resource_id, "uses_route_table")
    elif kind == "publicipaddresses":
        facts = {
            **string_fields(props, allocation="publicIPAllocationMethod", version="publicIPAddressVersion"),
            **string_fields(obj(props.get("dnsSettings")), dns_name="fqdn"),
            "assigned_addresses": parsed_addresses([props.get("ipAddress")], ip_address),
        }
        attached = scoped_network_id(reference(props.get("ipConfiguration")), subscription_id)
        if attached and len(attached.split("/")) > 9:
            link(resource_id, attached.rsplit("/", 2)[0], "attached_to")
    elif kind in {"dnszones", "privatednszones"}:
        facts = {"zone_visibility": "private" if kind == "privatednszones" else "public"}
        count = props.get("numberOfRecordSets")
        if type(count) is int:
            facts["record_set_count"] = count
        if kind == "dnszones":
            facts["name_servers"] = strings(props.get("nameServers"))
    elif kind == "microsoft.web/sites":
        facts = string_fields(
            props, state="state", default_hostname="defaultHostName", public_network_access="publicNetworkAccess",
        )
        if isinstance(props.get("httpsOnly"), bool):
            facts["https_only"] = props["httpsOnly"]
        link_resource(resource_id, props.get("serverFarmId"), "hosted_on")
        link_resource(resource_id, props.get("virtualNetworkSubnetId"), "integrates_with_subnet")
    elif kind == "privateendpoints":
        references(resource_id, props, (("subnet", "attached_to_subnet"),))
        for interface in rows(props.get("networkInterfaces")):
            link(resource_id, reference(interface), "uses_network_interface")
        connections = []
        for field_name in ("privateLinkServiceConnections", "manualPrivateLinkServiceConnections"):
            for connection in rows(props.get(field_name)):
                details = obj(connection.get("properties"))
                state = obj(details.get("privateLinkServiceConnectionState"))
                connections.append({
                    **string_fields(connection, name="name"),
                    **string_fields(state, status="status"),
                    "group_ids": strings(details.get("groupIds")),
                })
                link_resource(resource_id, details.get("privateLinkServiceId"), "private_link_to")
        custom_dns = [{
            **string_fields(config, fqdn="fqdn"),
            "ip_addresses": parsed_addresses(config.get("ipAddresses"), ip_address),
        } for config in rows(props.get("customDnsConfigs"))]
        facts = {"connections": connections, "custom_dns": custom_dns}
    elif kind == "applicationgatewaywebapplicationfirewallpolicies":
        facts = string_fields(obj(props.get("policySettings")), state="state", mode="mode")
    else:
        references(resource_id, props, (
            ("networkSecurityGroup", "protected_by"), ("firewallPolicy", "uses_firewall_policy"),
            ("subnet", "attached_to_subnet"),
        ))
        for key in ("ipConfigurations", "frontendIPConfigurations", "gatewayIPConfigurations"):
            for config in rows(props.get(key)):
                details = obj(config.get("properties"))
                references(resource_id, details, (
                    ("subnet", "attached_to_subnet"), ("publicIPAddress", "uses_public_ip"),
                ))
        for public_ip in rows(props.get("publicIpAddresses")):
            link(resource_id, public_ip.get("id"), "uses_public_ip")
        if kind == "azurefirewalls":
            facts.update(string_fields(props, threat_intelligence_mode="threatIntelMode"))
            facts["classic_rule_collection_count"] = sum(
                len(rows(props.get(field))) for field in (
                    "applicationRuleCollections", "networkRuleCollections", "natRuleCollections",
                )
            )
        if kind == "firewallpolicies":
            references(resource_id, props, (("basePolicy", "inherits_firewall_policy"),))
            facts.update(string_fields(props, threat_intelligence_mode="threatIntelMode"))
            facts.update(string_fields(obj(props.get("intrusionDetection")), intrusion_detection_mode="mode"))
            dns_proxy_enabled = obj(props.get("dnsSettings")).get("enableProxy")
            if isinstance(dns_proxy_enabled, bool):
                facts["dns_proxy_enabled"] = dns_proxy_enabled
        if kind == "applicationgateways":
            waf = obj(props.get("webApplicationFirewallConfiguration"))
            facts = string_fields(waf, waf_mode="firewallMode")
            if isinstance(waf.get("enabled"), bool):
                facts["waf_enabled"] = waf["enabled"]
        if kind in {"azurefirewalls", "firewallpolicies", "applicationgateways", "loadbalancers"}:
            facts.update(string_fields(obj(payload.get("sku")), sku="name", tier="tier"))
    resource_type = kind if kind.startswith("microsoft.") else f"microsoft.network/{kind}"
    return [resource_row(item, resource_type, facts), *children], links


async def collect_network(subscription_id: str, resources: list[dict], http: httpx.AsyncClient,
                          headers: dict[str, str]) -> NetworkCollection:
    subscription_id = str(UUID(subscription_id))
    candidates = {}
    inventory_records = {}
    ignored = 0
    for resource in resources:
        resource_type = str(resource.get("type") or "").casefold()
        resource_id = scoped_resource_id(resource.get("id"), subscription_id)
        if resource_id:
            inventory_records[resource_id.casefold()] = resource
        kind = resource_type.removeprefix("microsoft.network/") if resource_type.startswith("microsoft.network/") else resource_type
        api_version = API_VERSIONS.get(kind) or EXTRA_RESOURCE_API_VERSIONS.get(resource_type)
        if not api_version:
            continue
        if (not resource_id or len(resource_id.split("/")) != 9
                or resource_id.split("/")[-2].casefold() != kind.split("/")[-1]):
            ignored += 1
            continue
        candidates[resource_id.casefold()] = (resource, kind, api_version)

    limiter = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    pager = AzureResourceDiscoveryAdapter()

    async def collect(item, kind, api_version):
        async with limiter:
            try:
                response = await http.get(
                    f"{ARM}{item['id']}", params={"api-version": api_version},
                    headers=headers, follow_redirects=False,
                )
                if response.status_code != 200:
                    return [], [], status_reason(response.status_code)
                payload = response.json()
                returned_id = obj(payload).get("id")
                if (not isinstance(returned_id, str) or returned_id.casefold() != item["id"].casefold()
                        or not isinstance(payload.get("properties"), dict)):
                    return [], [], "provider_error"
                result, links = project_network_resource(item, payload, kind, subscription_id)
                if kind != "privatednszones":
                    return result, links, None
                try:
                    linked = await pager._collect_paged(
                        client=http, url=f"{ARM}{item['id']}/virtualNetworkLinks",
                        api_version=PRIVATE_DNS_API, headers=headers,
                    )
                except (httpx.HTTPError, ValueError):
                    return result, links, "provider_error"
                if not linked["success"]:
                    cause = linked.get("connection_state")
                    return result, links, cause if cause in {"permission_failure", "authentication_failure"} else "provider_error"
                for row in linked["items"]:
                    child = child_row(item, row, "virtualNetworkLinks", subscription_id)
                    target = scoped_network_id(reference(obj(row.get("properties")).get("virtualNetwork")), subscription_id)
                    if child and target:
                        links.append((item["id"], target, "dns_zone_link"))
                return result, links, None
            except (httpx.HTTPError, ValueError):
                return [], [], "provider_error"

    selected = sorted(candidates)[:RESOURCE_LIMIT]
    discovered = await asyncio.gather(*(collect(*candidates[key]) for key in selected))
    records = {item["id"].casefold(): item for result, _, _ in discovered for item in result}
    for _, links, _ in discovered:
        for source, target, _relation in links:
            for endpoint in (source, target):
                key = endpoint.casefold()
                inventory = inventory_records.get(key)
                if key not in records and inventory:
                    records[key] = {
                        "id": inventory["id"], "name": str(inventory.get("name") or ""),
                        "type": str(inventory.get("type") or ""), "location": str(inventory.get("location") or ""),
                        "properties": {"topology_context": True, "evidence_source": "saved_inventory"},
                    }
    edges = {
        (records[source.casefold()]["id"], records[target.casefold()]["id"], relation)
        for _, links, _ in discovered for source, target, relation in links
        if source.casefold() in records and target.casefold() in records
    }
    failures = Counter(error for _, _, error in discovered if error)
    reason = failures.most_common(1)[0][0] if failures else None
    status = ("partial_failure" if records else reason) if failures else "synced"
    limitations = list(LIMITATIONS)
    if ignored:
        limitations.append(f"Skipped {ignored} inventory item(s) with unusable ARM identifiers.")
    if len(candidates) > RESOURCE_LIMIT:
        limitations.append(f"Collected at most {RESOURCE_LIMIT} network resources for this refresh.")
    if failures:
        limitations.append(f"Azure did not return all requested details for {sum(failures.values())} network resource(s).")
    return NetworkCollection(status, reason, [records[key] for key in sorted(records)],
                             [{"source": source, "target": target, "kind": relation,
                               "evidence_source": "azure_configuration", "connectivity": "not_validated"}
                              for source, target, relation in sorted(edges)], limitations)
