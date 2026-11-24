from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.domains.access import inventory
from app.main import app
from tests.test_local_access import PASSWORD, WRITE


def test_active_architecture_sync_uses_client_inventory_and_maps_azure_relationships(monkeypatch):
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_USERNAME", "phase-one-admin")
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_PASSWORD", PASSWORD)
    monkeypatch.setenv("MONITORAI_AZURE_ENCRYPTION_KEY", Fernet.generate_key().decode())
    subscription = str(uuid4())
    group_id = f"/subscriptions/{subscription}/resourceGroups/rg-live"
    vnet_id = f"{group_id}/providers/Microsoft.Network/virtualNetworks/vnet-live"
    subnet_id = f"{vnet_id}/subnets/apps"
    plan_id = f"{group_id}/providers/Microsoft.Web/serverfarms/plan-live"
    app_id = f"{group_id}/providers/Microsoft.Web/sites/app-live"

    async def fake_collect(_values, _subscription_id):
        return inventory.InventoryCollection(status="synced", groups=[{
            "id": group_id, "name": "rg-live", "location": "eastus",
        }], resources=[
            {"id": vnet_id, "name": "vnet-live", "location": "eastus",
             "type": "Microsoft.Network/virtualNetworks", "resource_group": "rg-live", "properties": {}},
            {"id": subnet_id, "name": "apps", "location": "eastus",
             "type": "Microsoft.Network/virtualNetworks/subnets", "resource_group": "rg-live",
             "parent_azure_resource_id": vnet_id, "properties": {}},
            {"id": plan_id, "name": "plan-live", "location": "eastus",
             "type": "Microsoft.Web/serverfarms", "resource_group": "rg-live", "properties": {}},
            {"id": app_id, "name": "app-live", "location": "eastus",
             "type": "Microsoft.Web/sites", "resource_group": "rg-live",
             "properties": {"serverFarmId": plan_id, "virtualNetworkSubnetId": subnet_id}},
        ])

    monkeypatch.setattr(inventory, "collect_inventory", fake_collect)
    with TestClient(app, base_url="https://testserver") as client:
        assert client.post("/api/auth/login", headers=WRITE, json={
            "username": "phase-one-admin", "password": PASSWORD,
        }).status_code == 200
        client_id = client.post("/api/auth/clients", headers=WRITE, json={"name": str(uuid4())}).json()["client_id"]
        headers = {**WRITE, "X-Client-ID": client_id}
        credentials = {"tenant_id": str(uuid4()), "client_id": str(uuid4()), "client_secret": "fake",
                       "subscription_id": subscription}
        assert client.put("/api/settings/azure/credentials", headers=headers, json=credentials).status_code == 200
        refreshed = client.post("/api/azure/inventory/refresh", headers=headers)
        assert refreshed.status_code == 200 and refreshed.json()["status"] == "synced"

        architecture = client.post("/api/architectures", headers=headers, json={"name": "Inventory design"}).json()
        architecture_id = architecture["id"]
        design_subscription = client.post(f"/api/architectures/{architecture_id}/subscriptions", headers=headers,
            json={"name": "Azure", "subscription_id": subscription}).json()
        synced = client.post(f"/api/architectures/{architecture_id}/discover-resources", headers=headers,
            json={"subscription_id": design_subscription["id"]})

        assert synced.status_code == 200, synced.text
        assert synced.json()["success"] is True
        assert synced.json()["resources_created"] == 4
        relationships = client.get(f"/api/architectures/{architecture_id}/relationships", headers=headers).json()
        resources = client.get(f"/api/architectures/{architecture_id}/resources", headers=headers).json()
        by_type = {row["resource_type"]: row for row in resources}
        mapped = {(row["source_resource_id"], row["target_resource_id"], row["relationship_type"])
                  for row in relationships}
        assert (by_type["vnet"]["id"], by_type["subnet"]["id"], "contains") in mapped
        assert (by_type["appservice"]["id"], by_type["appserviceplan"]["id"], "hosted_on") in mapped
        assert (by_type["appservice"]["id"], by_type["subnet"]["id"], "integrated_with") in mapped
