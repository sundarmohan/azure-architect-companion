from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.domains.access import inventory
from app.domains.monitoring import diagnostics
from app.main import app
from tests.test_local_access import PASSWORD, WRITE


def test_diagnostics_use_owned_inventory_and_fixed_queries(monkeypatch):
    monkeypatch.setenv("MONITORAI_OBSERVATION_WORKER", "0")
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_USERNAME", "phase-one-admin")
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_PASSWORD", PASSWORD)
    monkeypatch.setenv("MONITORAI_AZURE_ENCRYPTION_KEY", Fernet.generate_key().decode())
    subscription = str(uuid4())
    resource_id = f"/subscriptions/{subscription}/resourceGroups/test/providers/Microsoft.Web/sites/example"
    calls = []

    async def fake_inventory(_credentials, _subscription):
        return inventory.InventoryCollection("synced", resources=[{
            "id": resource_id, "name": "example", "resource_group": "test",
            "type": "Microsoft.Web/sites", "location": "eastus",
        }])

    async def fake_logs(credentials, resource, source, hours):
        calls.append((resource, source, hours))
        assert credentials["client_secret"] == "fake"
        query = diagnostics.build_query(resource, source, hours)
        assert "AppServiceHTTPLogs" in query and resource_id in query and "ago(6h)" in query
        assert "CsUriQuery" not in query
        return diagnostics.parse_results({"tables": [{
            "name": "PrimaryResult", "columns": [{"name": col} for col in ("timestamp", "category", "count")],
            "rows": [["2026-01-01T00:00:00Z", "HTTP 5xx", 3], ["2026-01-01T00:00:00Z", "sensitive raw line", 1]],
        }]}, source, hours)

    monkeypatch.setattr(inventory, "collect_inventory", fake_inventory)
    monkeypatch.setattr(diagnostics, "query_logs", fake_logs)
    with TestClient(app, base_url="https://testserver") as client:
        assert client.post("/api/auth/login", headers=WRITE, json={
            "username": "phase-one-admin", "password": PASSWORD,
        }).status_code == 200
        first, second = [client.post("/api/auth/clients", headers=WRITE, json={"name": str(uuid4())})
                         .json()["client_id"] for _ in range(2)]
        own, other = [{**WRITE, "X-Client-ID": key} for key in (first, second)]
        for headers in (own, other):
            assert client.put("/api/settings/azure/credentials", headers=headers, json={
                "tenant_id": str(uuid4()), "client_id": str(uuid4()), "client_secret": "fake",
                "subscription_id": subscription,
            }).status_code == 200
        assert client.post("/api/azure/inventory/refresh", headers=own).status_code == 200
        url = "/api/azure/diagnostics/query"
        body = {"resource_id": resource_id, "source": "app_service", "hours": 6}
        assert client.post(url, headers=other, json=body).status_code == 404
        assert client.post(url, headers=own, json={**body, "query": "arbitrary"}).status_code == 422
        assert client.post(url, headers=own, json={**body, "resource_id": resource_id + "/../../resource"}).status_code == 404
        response = client.post(url, headers=own, json=body)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "partial_failure"
        assert response.json()["rows"][0]["count"] == 3 and "sensitive raw line" not in response.text
        assert calls == [(resource_id, "app_service", 6)]
