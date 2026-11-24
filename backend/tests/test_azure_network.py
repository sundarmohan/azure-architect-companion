import asyncio

import httpx

from app.domains.monitoring.network import collect_network

SUBSCRIPTION = "c213dd1e-e2bd-401e-8ef3-cd4fc43879c2"
OTHER_SUBSCRIPTION = "beb8b7ed-1fad-4125-bb85-e1a460c30eea"
BASE = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/test/providers/Microsoft.Network"


def inventory_item(kind, name):
    return {"id": f"{BASE}/{kind}/{name}", "name": name,
            "type": f"Microsoft.Network/{kind}", "location": "eastus"}


def compare_network(items, handler):
    async def collect():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await collect_network(SUBSCRIPTION, items, client, {"Authorization": "Bearer mocked-token"})

    return asyncio.run(collect())


def test_network_projects_allowlisted_facts_and_scoped_links():
    vnet = inventory_item("virtualNetworks", "vnet")
    nsg = inventory_item("networkSecurityGroups", "nsg")
    routes = inventory_item("routeTables", "routes")
    dns = inventory_item("privateDnsZones", "internal.example")
    public_ip = inventory_item("publicIPAddresses", "frontend")
    foreign = inventory_item("virtualNetworks", "foreign")
    foreign["id"] = foreign["id"].replace(SUBSCRIPTION, OTHER_SUBSCRIPTION)
    malformed = inventory_item("azureFirewalls", "../ignored?token=secret")
    subnet = {"id": f"{vnet['id']}/subnets/app", "properties": {
        "addressPrefix": "10.0.1.0/24", "networkSecurityGroup": {"id": nsg["id"].upper()},
        "routeTable": {"id": routes["id"]}, "untrusted": "secret",
        "delegations": [{"name": "web", "properties": {
            "serviceName": "Microsoft.Web/serverFarms", "actions": ["Microsoft.Network/virtualNetworks/subnets/action"],
        }}],
        "serviceEndpoints": [{"service": "Microsoft.Storage", "locations": ["eastus"]}],
    }}
    rule = {"name": "public inbound", "properties": {
        "access": "Allow", "direction": "Inbound", "sourceAddressPrefixes": ["Internet"],
        "destinationPortRange": "443", "protocol": "Tcp", "description": "secret",
    }}
    props = {
        vnet["id"]: {
            "addressSpace": {"addressPrefixes": ["10.0.0.0/16"]},
            "dhcpOptions": {"dnsServers": ["10.0.0.4", "not-an-ip"]},
            "subnets": [subnet, {"id": f"{foreign['id']}/subnets/foreign"}],
            "virtualNetworkPeerings": [{"properties": {"remoteVirtualNetwork": {"id": foreign["id"]}}}],
        },
        nsg["id"]: {"securityRules": [rule]},
        routes["id"]: {"routes": [{"name": "private", "properties": {
            "addressPrefix": "10.8.0.0/16", "nextHopType": "VirtualAppliance", "nextHopIpAddress": "10.0.0.7",
        }}]},
        dns["id"]: {"numberOfRecordSets": 2},
        public_ip["id"]: {"ipAddress": "203.0.113.10"},
    }
    requests = []

    def handler(request):
        requests.append(request.url.path)
        assert request.method == "GET"
        assert request.url.host == "management.azure.com"
        if request.url.path == f"{dns['id']}/virtualNetworkLinks":
            return httpx.Response(200, json={"value": [
                {"id": f"{dns['id']}/virtualNetworkLinks/vnet", "properties": {"virtualNetwork": {"id": vnet["id"]}}},
            ]})
        return httpx.Response(200, json={"id": request.url.path, "properties": props[request.url.path],
                                          "tags": {"ignored": "secret"}})

    result = compare_network([vnet, nsg, routes, dns, public_ip, foreign, malformed], handler)
    assert result.status == "synced"
    assert set(requests) == {*props, f"{dns['id']}/virtualNetworkLinks"}
    resources = {row["id"]: row["properties"] for row in result.resources}
    assert resources[vnet["id"]]["dns_servers"] == ["10.0.0.4"]
    assert resources[subnet["id"]]["delegations"][0]["service_name"] == "Microsoft.Web/serverFarms"
    assert resources[subnet["id"]]["service_endpoints"] == [{"service": "Microsoft.Storage", "locations": ["eastus"]}]
    assert resources[nsg["id"]]["internet_inbound_allow_rules"] == 1
    assert resources[nsg["id"]]["custom_rules"][0]["destination_ports"] == ["443"]
    assert resources[routes["id"]]["routes"][0]["next_hop_addresses"] == ["10.0.0.7"]
    assert resources[public_ip["id"]]["assigned_addresses"] == ["203.0.113.10"]
    assert "secret" not in str(result.resources)
    expected = [
        {"source": vnet["id"], "target": subnet["id"], "kind": "contains"},
        {"source": subnet["id"], "target": nsg["id"], "kind": "protected_by"},
        {"source": subnet["id"], "target": routes["id"], "kind": "uses_route_table"},
        {"source": dns["id"], "target": vnet["id"], "kind": "dns_zone_link"},
    ]
    expected = [dict(row, evidence_source="azure_configuration", connectivity="not_validated") for row in expected]
    assert result.links == sorted(expected, key=lambda row: (row["source"], row["target"], row["kind"]))


def test_network_keeps_inventory_backed_private_link_and_app_service_relationships():
    vnet = inventory_item("virtualNetworks", "vnet")
    private_endpoint = inventory_item("privateEndpoints", "storage-pe")
    storage = {
        "id": f"/subscriptions/{SUBSCRIPTION}/resourceGroups/test/providers/Microsoft.Storage/storageAccounts/data",
        "name": "data", "type": "Microsoft.Storage/storageAccounts", "location": "eastus",
    }
    app = {
        "id": f"/subscriptions/{SUBSCRIPTION}/resourceGroups/test/providers/Microsoft.Web/sites/app",
        "name": "app", "type": "Microsoft.Web/sites", "location": "eastus",
    }
    plan = {
        "id": f"/subscriptions/{SUBSCRIPTION}/resourceGroups/test/providers/Microsoft.Web/serverFarms/plan",
        "name": "plan", "type": "Microsoft.Web/serverFarms", "location": "eastus",
    }
    subnet_id = f"{vnet['id']}/subnets/apps"
    payloads = {
        vnet["id"]: {"subnets": [{"id": subnet_id, "properties": {
            "addressPrefix": "10.0.1.0/24", "privateEndpoints": [{"id": private_endpoint["id"]}],
        }}]},
        private_endpoint["id"]: {
            "subnet": {"id": subnet_id},
            "privateLinkServiceConnections": [{"name": "storage", "properties": {
                "privateLinkServiceId": storage["id"], "groupIds": ["blob"],
                "privateLinkServiceConnectionState": {"status": "Approved"},
            }}],
            "customDnsConfigs": [{"fqdn": "data.blob.core.windows.net", "ipAddresses": ["10.0.1.4"]}],
        },
        app["id"]: {
            "serverFarmId": plan["id"], "virtualNetworkSubnetId": subnet_id,
            "publicNetworkAccess": "Disabled", "httpsOnly": True,
        },
    }

    def handler(request):
        assert request.method == "GET"
        return httpx.Response(200, json={"id": request.url.path, "properties": payloads[request.url.path]})

    result = compare_network([vnet, private_endpoint, storage, app, plan], handler)
    assert result.status == "synced"
    by_id = {row["id"]: row for row in result.resources}
    assert by_id[storage["id"]]["properties"]["evidence_source"] == "saved_inventory"
    assert by_id[plan["id"]]["properties"]["topology_context"] is True
    assert by_id[private_endpoint["id"]]["properties"]["connections"][0]["status"] == "Approved"
    assert by_id[private_endpoint["id"]]["properties"]["custom_dns"][0]["ip_addresses"] == ["10.0.1.4"]
    kinds = {(row["source"], row["target"], row["kind"]) for row in result.links}
    assert (private_endpoint["id"], subnet_id, "attached_to_subnet") in kinds
    assert (private_endpoint["id"], storage["id"], "private_link_to") in kinds
    assert (app["id"], plan["id"], "hosted_on") in kinds
    assert (app["id"], subnet_id, "integrates_with_subnet") in kinds
    assert all(row["connectivity"] == "not_validated" for row in result.links)


def test_network_trusts_neither_redirects_nor_foreign_payload_identifiers():
    allowed = inventory_item("virtualNetworks", "allowed")
    denied = inventory_item("publicIPAddresses", "denied")
    mismatched = inventory_item("routeTables", "mismatched")
    redirected = inventory_item("networkInterfaces", "redirected")

    def handler(request):
        if request.url.path == allowed["id"]:
            return httpx.Response(200, json={"id": allowed["id"], "properties": {}})
        if request.url.path == denied["id"]:
            return httpx.Response(403, json={"error": {"message": "untrusted details"}})
        if request.url.path == mismatched["id"]:
            return httpx.Response(200, json={"id": mismatched["id"].replace(SUBSCRIPTION, OTHER_SUBSCRIPTION),
                                              "properties": {}})
        if request.url.path == redirected["id"]:
            return httpx.Response(302, headers={"Location": "https://example.invalid/foreign"})
        raise AssertionError(f"Unexpected Azure request: {request.url.path}")

    mixed = compare_network([allowed, denied, mismatched, redirected], handler)
    assert mixed.status == "partial_failure"
    assert [row["id"] for row in mixed.resources] == [allowed["id"]]
    denied_result = compare_network([denied], handler)
    assert denied_result.status == "permission_failure"
    assert denied_result.failure_reason == "permission_failure"
    assert denied_result.resources == []
