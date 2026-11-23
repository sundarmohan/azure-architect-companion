import asyncio
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.domains.access import inventory
from app.domains.architecture.azure_discovery import AzureResourceDiscoveryAdapter
from app.main import app
from tests.test_local_access import PASSWORD, WRITE


def test_inventory_isolated_by_client_and_subscription(monkeypatch):
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_USERNAME", "phase-one-admin")
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_PASSWORD", PASSWORD)
    monkeypatch.setenv("MONITORAI_AZURE_ENCRYPTION_KEY", Fernet.generate_key().decode())
    primary, secondary = str(uuid4()), str(uuid4())
    state = "synced"
    calls = []

    async def fake_collect(values, subscription_id):
        calls.append((values["client_secret"], subscription_id))
        resource_id = f"/subscriptions/{subscription_id}/resourceGroups/test/providers/example/resource"
        groups = []
        resources = inventory.summarize_items(
            [{"id": resource_id, "name": "resource", "type": "example/resource", "properties": {"secret": "not stored"}},
             {"id": resource_id.upper(), "name": "resource", "type": "example/resource"},
             {"id": "/subscriptions/foreign/resourceGroups/test", "name": "foreign"}],
            subscription_id, resources=True,
        )
        return inventory.InventoryCollection(
            state, "permission_failure" if state == "partial_failure" else None, groups, resources
        )

    monkeypatch.setattr(inventory, "collect_inventory", fake_collect)
    with TestClient(app, base_url="https://testserver") as client:
        assert client.post("/api/auth/login", headers=WRITE, json={
            "username": "phase-one-admin", "password": PASSWORD,
        }).status_code == 200
        first, second = [
            client.post("/api/auth/clients", headers=WRITE, json={"name": str(uuid4())}).json()["client_id"]
            for _ in range(2)
        ]
        first_headers = {**WRITE, "X-Client-ID": first}
        second_headers = {**WRITE, "X-Client-ID": second}
        credentials = {"tenant_id": str(uuid4()), "client_id": str(uuid4()), "client_secret": "fake",
                       "subscription_id": primary, "additional_subscription_ids": [secondary, primary, secondary]}
        for headers in (first_headers, second_headers):
            saved = client.put("/api/settings/azure/credentials", headers=headers, json=credentials)
            assert saved.status_code == 200, saved.text
            assert saved.json()["configured_subscription_ids"] == [primary, secondary]

        path = "/api/azure/inventory"
        assert client.get(path, headers=first_headers).json()["status"] == "not_synced"
        for _ in range(2):
            refreshed = client.post(f"{path}/refresh", headers=first_headers, params={"subscription_id": secondary})
            assert refreshed.status_code == 200, refreshed.text
            assert refreshed.json()["status"] == "synced"
            assert len(refreshed.json()["resources"]) == 1
            assert "not stored" not in refreshed.text
        assert calls == [("fake", secondary), ("fake", secondary)]
        assert client.get(path, headers=first_headers).json()["resources"] == []
        assert client.get(path, headers=second_headers, params={"subscription_id": secondary}).json()["resources"] == []
        assert client.get(path, headers=first_headers, params={"subscription_id": str(uuid4())}).status_code == 404

        state = "partial_failure"
        result = client.post(f"{path}/refresh", headers=first_headers, params={"subscription_id": secondary}).json()
        assert result["status"] == "partial_failure"
        assert result["failure_reason"] == "permission_failure"
        assert result["showing_retained_data"] is True
        assert result["correlation_id"]
        assert result["last_success_at"] and len(result["resources"]) == 1

        async def timed_out_collect(_values, _subscription_id):
            raise TimeoutError

        monkeypatch.setattr(inventory, "collect_inventory", timed_out_collect)
        timed_out = client.post(f"{path}/refresh", headers=first_headers, params={"subscription_id": secondary})
        assert timed_out.status_code == 200
        assert timed_out.json()["status"] == "provider_error"
        assert timed_out.json()["failure_stage"] == "inventory_collection"
        assert timed_out.json()["failure_reason"] == "timeout"
        assert timed_out.json()["showing_retained_data"] is True
        assert len(timed_out.json()["resources"]) == 1
        rotated = dict(credentials, client_id=str(uuid4()))
        assert client.put("/api/settings/azure/credentials", headers=first_headers, json=rotated).status_code == 200
        assert client.get(path, headers=first_headers, params={"subscription_id": secondary}).json()["status"] == "not_synced"
        assert client.delete("/api/settings/azure/credentials", headers=first_headers).status_code == 200
        assert client.get(path, headers=first_headers).json()["status"] == "not_configured"


def test_arm_pagination_validates_page_origin_and_path():
    subscription = str(uuid4())
    start = f"https://management.azure.com/subscriptions/{subscription}/resources"
    calls = []

    async def check():
        def mock(request):
            calls.append(str(request.url))
            return httpx.Response(200, json={"value": [], "nextLink": "https://example.invalid/page"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(mock)) as client:
            return await AzureResourceDiscoveryAdapter()._collect_paged(
                client=client, url=start, api_version="2021-04-01", headers={}
            )

    assert asyncio.run(check())["success"] is False
    assert len(calls) == 1
