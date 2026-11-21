import pytest
from fastapi.testclient import TestClient
from types import SimpleNamespace

from tests.legacy_app import app
from app.domains.settings.service import SettingsService


@pytest.fixture(autouse=True)
def reset_settings_state(monkeypatch):
    SettingsService.reset_runtime_state()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_TENANT_ID", raising=False)
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
    monkeypatch.delenv("AZURE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("AZURE_SUBSCRIPTION_ID", raising=False)
    with TestClient(app) as cleanup_client:
        cleanup_client.delete("/api/settings/providers/openai")
        cleanup_client.delete("/api/settings/providers/gemini")
        cleanup_client.delete("/api/settings/azure/credentials")
        cleanup_client.delete("/api/settings/cloud-accounts/aws/credentials")
        cleanup_client.delete("/api/settings/cloud-accounts/gcp/credentials")


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_provider_key_save_and_secret_not_returned(client: TestClient):
    key = "sk-test-openai-secret"
    response = client.put("/api/settings/providers/openai", json={"api_key": key})
    assert response.status_code == 200
    payload = response.json()

    assert payload["provider"] == "openai"
    assert payload["configuration_state"] == "configured"
    assert "api_key" not in payload
    assert key not in response.text

    overview = client.get("/api/settings")
    assert overview.status_code == 200
    assert key not in overview.text


def test_provider_key_persists_across_runtime_reset():
    key = "sk-test-openai-persisted"
    with TestClient(app) as first_client:
        save_response = first_client.put("/api/settings/providers/openai", json={"api_key": key})
        assert save_response.status_code == 200
        assert save_response.json()["configuration_state"] == "configured"

    SettingsService.reset_runtime_state()

    with TestClient(app) as second_client:
        overview = second_client.get("/api/settings")
        assert overview.status_code == 200
        payload = overview.json()
        openai = next(item for item in payload["ai_providers"] if item["provider"] == "openai")
        assert openai["configuration_state"] == "configured"
        assert key not in overview.text


def test_provider_not_configured_state(client: TestClient):
    response = client.get("/api/settings")
    assert response.status_code == 200
    payload = response.json()
    openai = next(item for item in payload["ai_providers"] if item["provider"] == "openai")
    assert openai["configuration_state"] == "not_configured"
    assert openai["connection_state"] == "not_configured"


def test_provider_configured_state_from_environment(client: TestClient, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gem-test-key")
    response = client.get("/api/settings")
    assert response.status_code == 200
    payload = response.json()
    gemini = next(item for item in payload["ai_providers"] if item["provider"] == "gemini")
    assert gemini["configuration_state"] == "configured"


def test_invalid_provider_returns_404(client: TestClient):
    response = client.put("/api/settings/providers/unknown", json={"api_key": "x"})
    assert response.status_code == 404


def test_provider_connection_test_controlled_failures(client: TestClient, monkeypatch):
    client.put("/api/settings/providers/openai", json={"api_key": "sk-test"})

    class _Response:
        def __init__(self, status_code: int):
            self.status_code = status_code

    class _AsyncClient401:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *args, **kwargs):
            return _Response(401)

    monkeypatch.setattr("app.domains.settings.service.httpx.AsyncClient", _AsyncClient401)
    auth_fail = client.post("/api/settings/providers/openai/test", json={})
    assert auth_fail.status_code == 200
    assert auth_fail.json()["state"] == "authentication_failure"

    class _AsyncClient403(_AsyncClient401):
        async def get(self, *args, **kwargs):
            return _Response(403)

    monkeypatch.setattr("app.domains.settings.service.httpx.AsyncClient", _AsyncClient403)
    perm_fail = client.post("/api/settings/providers/openai/test", json={})
    assert perm_fail.status_code == 200
    assert perm_fail.json()["state"] == "permission_failure"

    class _AsyncClient500(_AsyncClient401):
        async def get(self, *args, **kwargs):
            return _Response(500)

    monkeypatch.setattr("app.domains.settings.service.httpx.AsyncClient", _AsyncClient500)
    provider_fail = client.post("/api/settings/providers/openai/test", json={})
    assert provider_fail.status_code == 200
    assert provider_fail.json()["state"] == "provider_error"


def test_azure_not_configured_behavior(client: TestClient):
    response = client.post("/api/settings/azure/test", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["configuration_state"] == "not_configured"
    assert payload["connection_state"] == "not_configured"


def test_azure_save_status_clear_redacts_secret(client: TestClient):
    secret = "azure-secret-value"
    payload = {
        "tenant_id": "tenant-id",
        "client_id": "client-id",
        "client_secret": secret,
        "subscription_id": "subscription-id",
    }
    save = client.put("/api/settings/azure/credentials", json=payload)
    assert save.status_code == 200
    save_body = save.json()
    assert save_body["configuration_state"] == "configured"
    assert "client_secret" not in save.text
    assert secret not in save.text

    status = client.get("/api/settings/azure/status")
    assert status.status_code == 200
    assert "client_secret" not in status.text
    assert secret not in status.text

    overview = client.get("/api/settings")
    assert overview.status_code == 200
    assert "client_secret" not in overview.text
    assert secret not in overview.text

    clear = client.delete("/api/settings/azure/credentials")
    assert clear.status_code == 200
    clear_body = clear.json()
    assert clear_body["configuration_state"] == "not_configured"
    assert clear_body["connection_state"] == "not_configured"


def test_azure_save_without_secret_reentry_uses_stored_secret(client: TestClient):
    first = {
        "tenant_id": "tenant-id",
        "client_id": "client-id",
        "client_secret": "first-secret",
        "subscription_id": "subscription-id",
    }
    save1 = client.put("/api/settings/azure/credentials", json=first)
    assert save1.status_code == 200
    assert save1.json()["configuration_state"] == "configured"

    update_without_secret = {
        "tenant_id": "tenant-id",
        "client_id": "client-id-updated",
        "client_secret": "",
        "subscription_id": "subscription-id",
    }
    save2 = client.put("/api/settings/azure/credentials", json=update_without_secret)
    assert save2.status_code == 200
    payload = save2.json()
    assert payload["configuration_state"] == "configured"
    assert payload["configured_client_id_hint"] == "clie...ated"


def test_azure_test_connection_controlled_states(client: TestClient, monkeypatch):
    payload = {
        "tenant_id": "tenant-id",
        "client_id": "client-id",
        "client_secret": "azure-secret",
        "subscription_id": "subscription-id",
    }
    save = client.put("/api/settings/azure/credentials", json=payload)
    assert save.status_code == 200

    class _Token:
        token = "token"

    class _Credential:
        def __init__(self, *args, **kwargs):
            pass

        def get_token(self, *args, **kwargs):
            return _Token()

    monkeypatch.setattr("app.domains.settings.service.ClientSecretCredential", _Credential)

    class _Response:
        def __init__(self, status_code: int):
            self.status_code = status_code

    class _AsyncClient200:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *args, **kwargs):
            return _Response(200)

    monkeypatch.setattr("app.domains.settings.service.httpx.AsyncClient", _AsyncClient200)
    ok = client.post("/api/settings/azure/test", json={})
    assert ok.status_code == 200
    assert ok.json()["connection_state"] == "configured"

    class _AsyncClient403(_AsyncClient200):
        async def get(self, *args, **kwargs):
            return _Response(403)

    monkeypatch.setattr("app.domains.settings.service.httpx.AsyncClient", _AsyncClient403)
    denied = client.post("/api/settings/azure/test", json={})
    assert denied.status_code == 200
    assert denied.json()["connection_state"] == "permission_failure"


def test_existing_endpoints_unaffected(client: TestClient):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    architectures = client.get("/api/architectures")
    assert architectures.status_code == 200
    assert isinstance(architectures.json(), list)


def test_cloud_accounts_overview_contains_supported_providers(client: TestClient):
    response = client.get("/api/settings/cloud-accounts")
    assert response.status_code == 200
    payload = response.json()
    providers = {item["provider"] for item in payload}
    assert providers == {"azure", "aws", "gcp"}


def test_aws_save_without_secret_reentry_uses_stored_secret(client: TestClient):
    first = {
        "access_key_id": "AKIA_TEST_1234",
        "secret_access_key": "first-secret",
        "region": "us-east-1",
        "service_account_json": "",
    }
    save1 = client.put("/api/settings/cloud-accounts/aws/credentials", json=first)
    assert save1.status_code == 200
    assert save1.json()["configuration_state"] == "configured"

    update_without_secret = {
        "access_key_id": "AKIA_TEST_5678",
        "secret_access_key": "",
        "region": "us-west-2",
        "service_account_json": "",
    }
    save2 = client.put("/api/settings/cloud-accounts/aws/credentials", json=update_without_secret)
    assert save2.status_code == 200
    payload = save2.json()
    assert payload["configuration_state"] == "configured"
    assert payload["configured_identity_hint"] == "AKIA...5678"


def test_aws_connection_test_returns_authenticated_identity(client: TestClient, monkeypatch):
    save = client.put(
        "/api/settings/cloud-accounts/aws/credentials",
        json={
            "access_key_id": "AKIA_TEST_1234",
            "secret_access_key": "test-secret",
            "region": "us-east-1",
            "service_account_json": "",
        },
    )
    assert save.status_code == 200

    from app.domains.settings import service as settings_service_module

    async def _fake_aws_test(self, credentials):
        return settings_service_module._CloudAccountSnapshot(
            state="configured",
            message="AWS connection test succeeded.",
            authenticated_identity="123456789012",
            authenticated_name="arn:aws:iam::123456789012:user/test",
            last_tested_at="2026-01-01T00:00:00+00:00",
        )

    monkeypatch.setattr("app.domains.settings.service.SettingsService._test_aws_connection", _fake_aws_test)

    tested = client.post("/api/settings/cloud-accounts/aws/test", json={})
    assert tested.status_code == 200
    body = tested.json()
    assert body["connection_state"] == "configured"
    assert body["authenticated_identity"] == "123456789012"


def test_azure_status_includes_discovery_resource_counts(client: TestClient):
    architecture = client.post(
        "/api/architectures",
        json={"name": "settings-counts", "provider": "azure", "environment": "draft", "status": "draft"},
    ).json()

    subscription = client.post(
        f"/api/architectures/{architecture['id']}/subscriptions",
        json={"name": "sub-counts", "subscription_id": "sub-counts", "tenant_id": "tenant-counts"},
    ).json()

    group = client.post(
        f"/api/architectures/{architecture['id']}/resource-groups",
        json={
            "name": "rg-counts",
            "location": "eastus",
            "subscription_id": subscription["id"],
            "properties": {"discovery_last_seen_at": "2026-08-30T15:00:00+00:00"},
        },
    ).json()

    client.post(
        f"/api/architectures/{architecture['id']}/resources",
        json={
            "resource_type": "vm",
            "name": "vm-counts",
            "resource_group_id": group["id"],
            "properties": {
                "azure_resource_id": "/subscriptions/sub-counts/resourceGroups/rg-counts/providers/Microsoft.Compute/virtualMachines/vm-counts",
                "azure_subscription_id": "sub-counts",
                "discovery_last_seen_at": "2026-08-30T15:30:00+00:00",
            },
        },
    )

    save = client.put(
        "/api/settings/azure/credentials",
        json={
            "tenant_id": "tenant-counts",
            "client_id": "client-counts",
            "client_secret": "secret-counts",
            "subscription_id": "sub-counts",
        },
    )
    assert save.status_code == 200

    status = client.get("/api/settings/azure/status")
    assert status.status_code == 200
    payload = status.json()
    assert payload["discovered_resource_group_count"] == 1
    assert payload["discovered_resource_count"] == 1
    assert payload["last_discovery_sync_at"] == "2026-08-30T15:30:00+00:00"

    cleanup = client.delete(f"/api/architectures/{architecture['id']}")
    assert cleanup.status_code == 204


def test_azure_subscription_inventory_scopes_resources_by_subscription(client: TestClient, monkeypatch):
    architecture = client.post(
        "/api/architectures",
        json={"name": "inventory-scoping", "provider": "azure", "environment": "draft", "status": "draft"},
    ).json()

    sub_a = client.post(
        f"/api/architectures/{architecture['id']}/subscriptions",
        json={"name": "sub-a", "subscription_id": "sub-a", "tenant_id": "tenant-a"},
    ).json()
    sub_b = client.post(
        f"/api/architectures/{architecture['id']}/subscriptions",
        json={"name": "sub-b", "subscription_id": "sub-b", "tenant_id": "tenant-b"},
    ).json()

    rg_a = client.post(
        f"/api/architectures/{architecture['id']}/resource-groups",
        json={"name": "rg-a", "location": "eastus", "subscription_id": sub_a["id"]},
    ).json()
    rg_b = client.post(
        f"/api/architectures/{architecture['id']}/resource-groups",
        json={"name": "rg-b", "location": "eastus", "subscription_id": sub_b["id"]},
    ).json()

    client.post(
        f"/api/architectures/{architecture['id']}/resources",
        json={
            "resource_type": "vm",
            "name": "vm-a",
            "resource_group_id": rg_a["id"],
            "properties": {"azure_subscription_id": "sub-a"},
        },
    )
    client.post(
        f"/api/architectures/{architecture['id']}/resources",
        json={
            "resource_type": "vm",
            "name": "vm-b",
            "resource_group_id": rg_b["id"],
            "properties": {"azure_subscription_id": "sub-b"},
        },
    )

    async def _fake_cost(self, **kwargs):
        count = len(kwargs.get("resources") or [])
        return SimpleNamespace(total_monthly_cost=float(count * 10))

    monkeypatch.setattr("app.domains.settings.service.CostEstimationService.estimate_architecture_cost", _fake_cost)

    inventory = client.get("/api/settings/azure/subscriptions")
    assert inventory.status_code == 200
    rows = [item for item in inventory.json() if item["architecture_id"] == architecture["id"]]
    rows = sorted(rows, key=lambda item: item["subscription_id"] or "")
    assert len(rows) == 2

    assert rows[0]["subscription_id"] == "sub-a"
    assert rows[0]["resource_group_count"] == 1
    assert rows[0]["resource_count"] == 1
    assert rows[0]["monitoring_state"] in {"no_data", "azure_api_failure", "live", "unsupported"}

    assert rows[1]["subscription_id"] == "sub-b"
    assert rows[1]["resource_group_count"] == 1
    assert rows[1]["resource_count"] == 1
    assert rows[1]["monitoring_state"] in {"no_data", "azure_api_failure", "live", "unsupported"}

    cleanup = client.delete(f"/api/architectures/{architecture['id']}")
    assert cleanup.status_code == 204