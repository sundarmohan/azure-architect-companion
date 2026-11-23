import asyncio
from uuid import UUID, uuid4

import httpx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.domains.backup.routes import read_rows, retention_summary, vaults_for_inventory
from app.main import app
from tests.test_local_access import PASSWORD, WRITE


def test_backup_vaults_and_reads_stay_in_scope():
    subscription = UUID("11111111-1111-1111-1111-111111111111")
    root = f"/subscriptions/{subscription}/resourceGroups/example/providers/Microsoft.RecoveryServices/vaults"
    vault = f"{root}/recovery"
    assert vaults_for_inventory([
        {"id": vault}, {"id": vault.upper()}, {"id": vault + "/backupJobs/job"},
        {"id": vault.replace(str(subscription), "22222222-2222-2222-2222-222222222222")},
        {"id": vault.replace("example", "..")},
    ], subscription) == [(vault, "recovery")]

    def transport(request):
        assert request.method == "GET"
        assert request.url.host == "management.azure.com"
        assert request.url.path == vault + "/backupJobs"
        return httpx.Response(200, json={
            "value": [{"properties": {"operation": "Restore", "status": "Completed", "private": "omit"}}],
            "nextLink": "https://untrusted.example/another-page",
        })

    async def read():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
            return await read_rows(http, asyncio.Semaphore(1), {}, vault, "jobs", "backupJobs", "2025-08-01")

    assert asyncio.run(read()) == {
        "status": "synced", "truncated": True, "rows": [{"operation": "Restore", "status": "Completed"}],
    }


def test_retention_summary_only_uses_supported_policy_fields():
    assert retention_summary({
        "dailySchedule": {"retentionDuration": {"count": 30, "durationType": "Days"}},
        "yearlySchedule": {"retentionDuration": {"count": 7, "durationType": "Years"}},
        "monthlySchedule": {"retentionDuration": {"count": True, "durationType": "Months"}},
    }) == "Daily 30 days; Yearly 7 years"
    assert retention_summary(None) == ""


def test_replication_evidence_projects_same_vault_items_from_one_read():
    subscription = UUID("11111111-1111-1111-1111-111111111111")
    vault = f"/subscriptions/{subscription}/resourceGroups/example/providers/Microsoft.RecoveryServices/vaults/recovery"
    item_path = "/replicationFabrics/fabric/replicationProtectionContainers/container/replicationProtectedItems/item"
    good = {
        "id": vault.upper() + item_path,
        "properties": {
            "friendlyName": "Replicated VM",
            "protectionState": "Protected",
            "replicationHealth": "Normal",
            "providerSpecificDetails": {
                "lastRecoveryPointReceived": "2026-11-23T10:00:00Z",
                "ipAddress": "192.0.2.1",
            },
            "allowedOperations": ["TestFailover"],
        },
    }
    unknown_point = {
        "id": vault + item_path + "-2",
        "properties": {"friendlyName": "Another VM", "providerSpecificDetails": {"lastRecoveryPointReceived": "invalid"}},
    }
    calls = []

    def transport(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.url.host == "management.azure.com"
        assert request.url.path == vault + "/replicationProtectedItems"
        assert dict(request.url.params) == {"api-version": "2025-08-01"}
        return httpx.Response(200, json={
            "value": [good, unknown_point, {**good, "id": vault.replace("recovery", "recovery-other") + item_path},
                      {**good, "id": vault + item_path.replace("/fabric/", "/../")}],
            "nextLink": "https://example.invalid/ignored",
        })

    async def read():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
            return await read_rows(http, asyncio.Semaphore(1), {}, vault, "replication_items",
                                   "replicationProtectedItems", "2025-08-01")

    assert asyncio.run(read()) == {"status": "partial_failure", "truncated": True, "rows": [
        {"friendlyName": "Replicated VM", "protectionState": "Protected", "replicationHealth": "Normal",
         "lastRecoveryPointReceived": "2026-11-23T10:00:00Z"},
        {"friendlyName": "Another VM"},
    ]}
    assert len(calls) == 1


def test_recovery_objectives_are_scoped_persisted_and_audited(monkeypatch):
    monkeypatch.setenv("MONITORAI_OBSERVATION_WORKER", "0")
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_USERNAME", "phase-one-admin")
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_PASSWORD", PASSWORD)
    monkeypatch.setenv("MONITORAI_AZURE_ENCRYPTION_KEY", Fernet.generate_key().decode())
    subscription = str(uuid4())
    path = "/api/azure/backup/objectives"
    params = {"subscription_id": subscription}
    objectives = {"rpo_hours": 24, "rto_minutes": 60}
    with TestClient(app, base_url="https://testserver") as client:
        assert client.get(path, params=params).status_code == 401
        assert client.post("/api/auth/login", headers=WRITE, json={
            "username": "phase-one-admin", "password": PASSWORD,
        }).status_code == 200
        first, second = [client.post("/api/auth/clients", headers=WRITE, json={"name": str(uuid4())})
                         .json()["client_id"] for _ in range(2)]
        headers, other_headers = [{**WRITE, "X-Client-ID": item} for item in (first, second)]
        for scope_headers in (headers, other_headers):
            assert client.put("/api/settings/azure/credentials", headers=scope_headers, json={
                "tenant_id": str(uuid4()), "client_id": str(uuid4()), "client_secret": "objectives-test",
                "subscription_id": subscription,
            }).status_code == 200
        assert client.get(path, headers=headers, params=params).json() is None
        assert client.put(path, headers=headers, params=params, json={**objectives, "rpo_hours": 0}).status_code == 422
        assert client.put(path, headers=headers, params={"subscription_id": str(uuid4())}, json=objectives).status_code == 404
        saved = client.put(path, headers=headers, params=params, json=objectives)
        assert saved.status_code == 200, saved.text
        assert client.get(path, headers=headers, params=params).json() == objectives
        assert client.get(path, headers=other_headers, params=params).json() is None
        assert any(event["action"] == "save_azure_recovery_objectives" for event in
                   client.get("/api/audit", headers=headers).json())
        editor = "backup-editor-" + uuid4().hex
        assert client.post("/api/auth/users", headers=WRITE, json={"username": editor, "password": PASSWORD}).status_code == 201
        for client_id, role in [(first, "editor"), (second, "viewer")]:
            assert client.post(f"/api/auth/clients/{client_id}/members", headers=WRITE, json={
                "username": editor, "role": role,
            }).status_code == 204
        client.cookies.clear()
        assert client.post("/api/auth/login", headers=WRITE, json={"username": editor, "password": PASSWORD}).status_code == 200
        updated = {**objectives, "rto_minutes": 120}
        assert client.put(path, headers=headers, params=params, json=updated).json() == updated
        assert client.get(path, headers=other_headers, params=params).json() is None
        assert client.put(path, headers=other_headers, params=params, json=objectives).status_code == 403
