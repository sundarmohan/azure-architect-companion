import asyncio
from datetime import date
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.domains.cost import azure_cost_management_adapter as adapter_module
from app.main import app
from tests.test_local_access import PASSWORD, WRITE


def test_actual_cost_is_subscription_scoped_and_bounded(monkeypatch):
    monkeypatch.setenv("MONITORAI_OBSERVATION_WORKER", "0")
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_USERNAME", "phase-one-admin")
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_PASSWORD", PASSWORD)
    monkeypatch.setenv("MONITORAI_AZURE_ENCRYPTION_KEY", Fernet.generate_key().decode())
    subscription, other = str(uuid4()), str(uuid4())
    calls = []

    async def fake_cost(self, *, credentials, subscription_id, start_date, end_date):
        calls.append(subscription_id)
        assert credentials["client_secret"] == "cost-test"
        assert start_date == date(2026, 1, 1) and end_date == date(2026, 1, 31)
        return {"available": True, "currency": "CAD", "total_cost": 9,
                "daily": [{"usage_date": "2026-01-01", "cost": 9}]}

    monkeypatch.setattr(adapter_module.AzureCostManagementAdapter, "get_actual_cost", fake_cost)
    path = "/api/azure/cost/actual"
    dates = {"start_date": "2026-01-01", "end_date": "2026-01-31"}
    with TestClient(app, base_url="https://testserver") as client:
        assert client.get(path, params=dates).status_code == 401
        assert client.post("/api/auth/login", headers=WRITE, json={
            "username": "phase-one-admin", "password": PASSWORD,
        }).status_code == 200
        workspace = client.post("/api/auth/clients", headers=WRITE, json={"name": str(uuid4())}).json()["client_id"]
        headers = {**WRITE, "X-Client-ID": workspace}
        assert client.get(path, headers=headers, params=dates).status_code == 404
        assert client.put("/api/settings/azure/credentials", headers=headers, json={
            "tenant_id": str(uuid4()), "client_id": str(uuid4()), "client_secret": "cost-test",
            "subscription_id": subscription,
        }).status_code == 200
        assert client.get(path, headers=headers, params={**dates, "subscription_id": other}).status_code == 404
        assert client.get(path, headers=headers, params={**dates, "end_date": "2026-02-01"}).status_code == 422
        result = client.get(path, headers=headers, params={**dates, "subscription_id": subscription})
        assert result.status_code == 200, result.text
        assert result.json()["currency"] == "CAD"
        assert result.json()["total_cost"] == 9
        assert result.json()["subscription_id"] == subscription
        assert "cost-test" not in result.text
        assert calls == [subscription]

        path = "/api/azure/cost/budget"
        scope = {"subscription_id": subscription}
        budget = {"amount": "30.00", "currency": "CAD"}
        assert client.get(path, headers=headers, params=scope).json() is None
        assert client.put(path, headers=headers, params=scope, json={**budget, "amount": 0}).status_code == 422
        assert client.put(path, headers=headers, params={"subscription_id": other}, json=budget).status_code == 404
        saved = client.put(path, headers=headers, params=scope, json=budget)
        assert saved.status_code == 200, saved.text
        assert client.get(path, headers=headers, params=scope).json() == budget
        events = client.get("/api/audit", headers=headers).json()
        assert any(item["action"] == "save_azure_cost_budget" for item in events)
        viewer = "cost-viewer-" + uuid4().hex
        assert client.post("/api/auth/users", headers=WRITE, json={
            "username": viewer, "password": PASSWORD,
        }).status_code == 201
        assert client.post(f"/api/auth/clients/{workspace}/members", headers=WRITE, json={
            "username": viewer, "role": "viewer",
        }).status_code == 204
        client.cookies.clear()
        assert client.post("/api/auth/login", headers=WRITE, json={
            "username": viewer, "password": PASSWORD,
        }).status_code == 200
        assert client.get(path, headers=headers, params=scope).json() == budget
        assert client.put(path, headers=headers, params=scope, json=budget).status_code == 403
        assert calls == [subscription]


def test_billed_result_parsing_does_not_mix_currencies_or_silent_partial_pages(monkeypatch):
    class Credential:
        def __init__(self, **kwargs):
            assert kwargs["client_secret"] == "scoped"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def get_token(self, _scope):
            return type("Token", (), {"token": "dummy"})()

    properties = {
        "columns": [{"name": name} for name in ("PreTaxCost", "UsageDate", "Currency")],
        "rows": [[0, 20260101, "CAD"], [3, 20260102, "CAD"]],
    }
    adapter = adapter_module.AzureCostManagementAdapter()

    async def fake_post(**kwargs):
        assert kwargs["body"]["type"] == "ActualCost"
        assert kwargs["body"]["timePeriod"]["to"] == "2026-01-02T23:59:59+00:00"
        return httpx.Response(200, json={"properties": properties}, request=httpx.Request("POST", kwargs["query_url"]))

    monkeypatch.setattr(adapter_module, "AsyncClientSecretCredential", Credential)
    monkeypatch.setattr(adapter, "_post_cost_query", fake_post)
    kwargs = {
        "credentials": {"tenant_id": "tenant", "client_id": "client", "client_secret": "scoped"},
        "subscription_id": str(uuid4()), "start_date": date(2026, 1, 1), "end_date": date(2026, 1, 2),
    }
    result = asyncio.run(adapter.get_actual_cost(**kwargs))
    assert result["available"] and result["total_cost"] == 3 and result["daily"][0]["cost"] == 0
    properties["rows"][1][2] = "USD"
    assert not asyncio.run(adapter.get_actual_cost(**kwargs))["available"]
    properties["nextLink"] = "https://example.invalid"
    assert "partial" in asyncio.run(adapter.get_actual_cost(**kwargs))["error"]
