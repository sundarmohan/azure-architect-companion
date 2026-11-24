from uuid import uuid4

from fastapi.testclient import TestClient

from tests.legacy_app import app
from app.domains.architecture.azure_discovery import AzureResourceDiscoveryAdapter


class _FakeAdapterSuccess:
    async def discover_subscription_resources(self, *, subscription_id: str):
        return {
            "success": True,
            "connection_state": "configured_connected",
            "subscription": {
                "id": subscription_id,
                "name": "Discovered Subscription",
                "state": "Enabled",
            },
            "resource_groups": [
                {
                    "azure_resource_id": "/subscriptions/sub-1/resourceGroups/rg-live",
                    "name": "rg-live",
                    "location": "eastus",
                    "subscription_id": subscription_id,
                    "tags": {"env": "dev"},
                    "properties": {},
                }
            ],
            "resources": [
                {
                    "azure_resource_id": "/subscriptions/sub-1/resourceGroups/rg-live/providers/Microsoft.Network/virtualNetworks/vnet-live",
                    "azure_resource_type": "Microsoft.Network/virtualNetworks",
                    "resource_type": "vnet",
                    "name": "vnet-live",
                    "location": "eastus",
                    "resource_group_name": "rg-live",
                    "subscription_id": subscription_id,
                    "sku": None,
                    "parent_azure_resource_id": None,
                    "properties": {},
                },
                {
                    "azure_resource_id": "/subscriptions/sub-1/resourceGroups/rg-live/providers/Microsoft.Network/virtualNetworks/vnet-live/subnets/subnet-live",
                    "azure_resource_type": "Microsoft.Network/virtualNetworks/subnets",
                    "resource_type": "subnet",
                    "name": "subnet-live",
                    "location": "eastus",
                    "resource_group_name": "rg-live",
                    "subscription_id": subscription_id,
                    "sku": None,
                    "parent_azure_resource_id": "/subscriptions/sub-1/resourceGroups/rg-live/providers/Microsoft.Network/virtualNetworks/vnet-live",
                    "properties": {},
                },
                {
                    "azure_resource_id": "/subscriptions/sub-1/resourceGroups/rg-live/providers/Microsoft.Compute/virtualMachines/vm-live",
                    "azure_resource_type": "Microsoft.Compute/virtualMachines",
                    "resource_type": "vm",
                    "name": "vm-live",
                    "location": "eastus",
                    "resource_group_name": "rg-live",
                    "subscription_id": subscription_id,
                    "sku": "Standard_B2s",
                    "parent_azure_resource_id": None,
                    "properties": {"provisioningState": "Succeeded"},
                },
                {
                    "azure_resource_id": "/subscriptions/sub-1/resourceGroups/rg-live/providers/Microsoft.Web/serverfarms/plan-live",
                    "azure_resource_type": "Microsoft.Web/serverfarms", "resource_type": "appserviceplan",
                    "name": "plan-live", "location": "eastus", "resource_group_name": "rg-live",
                    "subscription_id": subscription_id, "sku": "P1v3", "parent_azure_resource_id": None,
                    "properties": {},
                },
                {
                    "azure_resource_id": "/subscriptions/sub-1/resourceGroups/rg-live/providers/Microsoft.Web/sites/app-live",
                    "azure_resource_type": "Microsoft.Web/sites", "resource_type": "appservice",
                    "name": "app-live", "location": "eastus", "resource_group_name": "rg-live",
                    "subscription_id": subscription_id, "sku": None, "parent_azure_resource_id": None,
                    "properties": {"serverFarmId": "/subscriptions/sub-1/resourceGroups/rg-live/providers/Microsoft.Web/serverfarms/plan-live"},
                },
                {
                    "azure_resource_id": "/subscriptions/sub-1/resourceGroups/rg-live/providers/Microsoft.Storage/storageAccounts/storelive",
                    "azure_resource_type": "Microsoft.Storage/storageAccounts", "resource_type": "storage",
                    "name": "storelive", "location": "eastus", "resource_group_name": "rg-live",
                    "subscription_id": subscription_id, "sku": "Standard_LRS", "parent_azure_resource_id": None,
                    "properties": {},
                },
                {
                    "azure_resource_id": "/subscriptions/sub-1/resourceGroups/rg-live/providers/Microsoft.Network/privateEndpoints/pe-live",
                    "azure_resource_type": "Microsoft.Network/privateEndpoints", "resource_type": "privateendpoint",
                    "name": "pe-live", "location": "eastus", "resource_group_name": "rg-live",
                    "subscription_id": subscription_id, "sku": None, "parent_azure_resource_id": None,
                    "properties": {
                        "subnet": {"id": "/subscriptions/sub-1/resourceGroups/rg-live/providers/Microsoft.Network/virtualNetworks/vnet-live/subnets/subnet-live"},
                        "privateLinkServiceConnections": [{"properties": {"privateLinkServiceId": "/subscriptions/sub-1/resourceGroups/rg-live/providers/Microsoft.Storage/storageAccounts/storelive"}}],
                    },
                },
            ],
            "unsupported_resources": 1,
            "skipped_without_group": 0,
        }


class _FakeAdapterEmpty:
    async def discover_subscription_resources(self, *, subscription_id: str):
        return {
            "success": True,
            "connection_state": "configured_connected",
            "resource_groups": [],
            "resources": [],
            "unsupported_resources": 0,
            "skipped_without_group": 0,
        }


class _FakeAdapterAuthFailure:
    async def discover_subscription_resources(self, *, subscription_id: str):
        return {
            "success": False,
            "connection_state": "authentication_failure",
            "error": "auth failed",
        }


class _FakeAdapterPermissionFailure:
    async def discover_subscription_resources(self, *, subscription_id: str):
        return {
            "success": False,
            "connection_state": "permission_failure",
            "error": "forbidden",
        }


class _FakeAdapterApiFailure:
    async def discover_subscription_resources(self, *, subscription_id: str):
        return {
            "success": False,
            "connection_state": "azure_api_failure",
            "error": "api failure",
        }


def _create_architecture(client: TestClient, name: str) -> dict:
    response = client.post(
        "/api/architectures",
        json={"name": name, "provider": "azure", "environment": "draft", "status": "draft"},
    )
    assert response.status_code == 201
    return response.json()


def _create_subscription(client: TestClient, architecture_id: str, *, name: str, subscription_id: str | None) -> dict:
    response = client.post(
        f"/api/architectures/{architecture_id}/subscriptions",
        json={"name": name, "subscription_id": subscription_id},
    )
    assert response.status_code == 201
    return response.json()


def test_adapter_normalizes_supported_and_unsupported_resource_types():
    adapter = AzureResourceDiscoveryAdapter()

    vm = adapter._normalize_resource(
        {
            "id": "/subscriptions/sub-1/resourceGroups/rg-live/providers/Microsoft.Compute/virtualMachines/vm-live",
            "name": "vm-live",
            "type": "Microsoft.Compute/virtualMachines",
            "location": "eastus",
            "properties": {},
            "sku": {"name": "Standard_B2s"},
        },
        "sub-1",
    )
    assert vm is not None
    assert vm["resource_type"] == "vm"
    assert vm["resource_group_name"] == "rg-live"
    assert vm["sku"] == "Standard_B2s"

    unsupported = adapter._normalize_resource(
        {
            "id": "/subscriptions/sub-1/resourceGroups/rg-live/providers/Microsoft.Sample/customType/sample",
            "name": "sample",
            "type": "Microsoft.Sample/customType",
            "location": "eastus",
            "properties": {},
        },
        "sub-1",
    )
    assert unsupported is None


def test_discovery_success_duplicate_safety_and_hierarchy(monkeypatch):
    monkeypatch.setattr(
        "app.domains.architecture.routes.AzureResourceDiscoveryAdapter",
        _FakeAdapterSuccess,
    )

    with TestClient(app) as client:
        architecture = _create_architecture(client, f"disc-{uuid4()}")
        subscription = _create_subscription(
            client,
            architecture["id"],
            name="sub-live",
            subscription_id="sub-1",
        )

        first = client.post(
            f"/api/architectures/{architecture['id']}/discover-resources",
            json={"subscription_id": subscription["id"]},
        )
        assert first.status_code == 200
        payload = first.json()
        assert payload["success"] is True
        assert payload["connection_state"] == "configured_connected"
        assert payload["discovered_subscription_name"] == "Discovered Subscription"
        assert payload["resource_groups_created"] == 1
        assert payload["resources_created"] == 7
        assert payload["relationships_created"] == 4
        assert payload["unsupported_resources"] == 1
        assert len(payload["normalized_resources"]) == 7

        subscriptions = client.get(f"/api/architectures/{architecture['id']}/subscriptions")
        assert subscriptions.status_code == 200
        persisted_subscription = next(
            row for row in subscriptions.json() if row["id"] == subscription["id"]
        )
        assert persisted_subscription["name"] == "Discovered Subscription"
        assert persisted_subscription["properties"]["discovered_subscription_state"] == "Enabled"
        assert persisted_subscription["properties"].get("discovery_last_sync_at")

        resources_first = client.get(f"/api/architectures/{architecture['id']}/resources")
        assert resources_first.status_code == 200
        assert len(resources_first.json()) == 7

        second = client.post(
            f"/api/architectures/{architecture['id']}/discover-resources",
            json={"subscription_id": subscription["id"]},
        )
        assert second.status_code == 200
        payload_second = second.json()
        assert payload_second["success"] is True
        assert payload_second["resources_created"] == 0
        assert payload_second["resources_updated"] >= 3

        resources_second = client.get(f"/api/architectures/{architecture['id']}/resources")
        assert resources_second.status_code == 200
        items = resources_second.json()
        assert len(items) == 7

        vnet = next(item for item in items if item["resource_type"] == "vnet")
        subnet = next(item for item in items if item["resource_type"] == "subnet")
        assert subnet["parent_resource_id"] == vnet["id"]
        by_type = {item["resource_type"]: item for item in items}
        relationships = client.get(f"/api/architectures/{architecture['id']}/relationships").json()
        relationship_types = {
            (item["source_resource_id"], item["target_resource_id"], item["relationship_type"])
            for item in relationships
        }
        assert (by_type["appservice"]["id"], by_type["appserviceplan"]["id"], "hosted_on") in relationship_types
        assert (by_type["subnet"]["id"], by_type["privateendpoint"]["id"], "contains") in relationship_types
        assert (by_type["privateendpoint"]["id"], by_type["storage"]["id"], "private_link") in relationship_types

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


def test_discovery_empty_subscription(monkeypatch):
    monkeypatch.setattr(
        "app.domains.architecture.routes.AzureResourceDiscoveryAdapter",
        _FakeAdapterEmpty,
    )

    with TestClient(app) as client:
        architecture = _create_architecture(client, f"disc-empty-{uuid4()}")
        subscription = _create_subscription(client, architecture["id"], name="sub-empty", subscription_id="sub-empty")

        response = client.post(
            f"/api/architectures/{architecture['id']}/discover-resources",
            json={"subscription_id": subscription["id"]},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["resource_groups_discovered"] == 0
        assert payload["resources_discovered"] == 0

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


def test_discovery_authentication_failure(monkeypatch):
    monkeypatch.setattr(
        "app.domains.architecture.routes.AzureResourceDiscoveryAdapter",
        _FakeAdapterAuthFailure,
    )

    with TestClient(app) as client:
        architecture = _create_architecture(client, f"disc-auth-{uuid4()}")
        subscription = _create_subscription(client, architecture["id"], name="sub-auth", subscription_id="sub-auth")

        response = client.post(
            f"/api/architectures/{architecture['id']}/discover-resources",
            json={"subscription_id": subscription["id"]},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is False
        assert payload["connection_state"] == "authentication_failure"

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


def test_discovery_permission_failure(monkeypatch):
    monkeypatch.setattr(
        "app.domains.architecture.routes.AzureResourceDiscoveryAdapter",
        _FakeAdapterPermissionFailure,
    )

    with TestClient(app) as client:
        architecture = _create_architecture(client, f"disc-perm-{uuid4()}")
        subscription = _create_subscription(client, architecture["id"], name="sub-perm", subscription_id="sub-perm")

        response = client.post(
            f"/api/architectures/{architecture['id']}/discover-resources",
            json={"subscription_id": subscription["id"]},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is False
        assert payload["connection_state"] == "permission_failure"

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


def test_discovery_azure_api_failure(monkeypatch):
    monkeypatch.setattr(
        "app.domains.architecture.routes.AzureResourceDiscoveryAdapter",
        _FakeAdapterApiFailure,
    )

    with TestClient(app) as client:
        architecture = _create_architecture(client, f"disc-api-{uuid4()}")
        subscription = _create_subscription(client, architecture["id"], name="sub-api", subscription_id="sub-api")

        response = client.post(
            f"/api/architectures/{architecture['id']}/discover-resources",
            json={"subscription_id": subscription["id"]},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is False
        assert payload["connection_state"] == "azure_api_failure"

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


def test_discovery_subscription_ownership_validation(monkeypatch):
    monkeypatch.setattr(
        "app.domains.architecture.routes.AzureResourceDiscoveryAdapter",
        _FakeAdapterSuccess,
    )

    with TestClient(app) as client:
        architecture_a = _create_architecture(client, f"disc-own-a-{uuid4()}")
        architecture_b = _create_architecture(client, f"disc-own-b-{uuid4()}")

        subscription_b = _create_subscription(
            client,
            architecture_b["id"],
            name="sub-b",
            subscription_id="sub-b",
        )

        response = client.post(
            f"/api/architectures/{architecture_a['id']}/discover-resources",
            json={"subscription_id": subscription_b["id"]},
        )
        assert response.status_code == 400

        cleanup_a = client.delete(f"/api/architectures/{architecture_a['id']}")
        cleanup_b = client.delete(f"/api/architectures/{architecture_b['id']}")
        assert cleanup_a.status_code == 204
        assert cleanup_b.status_code == 204


def test_discovery_not_configured_when_subscription_missing_external_id(monkeypatch):
    monkeypatch.setattr(
        "app.domains.architecture.routes.AzureResourceDiscoveryAdapter",
        _FakeAdapterSuccess,
    )

    with TestClient(app) as client:
        architecture = _create_architecture(client, f"disc-noconfig-{uuid4()}")
        subscription = _create_subscription(client, architecture["id"], name="sub-noconfig", subscription_id=None)

        response = client.post(
            f"/api/architectures/{architecture['id']}/discover-resources",
            json={"subscription_id": subscription["id"]},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is False
        assert payload["connection_state"] == "not_configured"

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204
