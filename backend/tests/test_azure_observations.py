import asyncio
from uuid import UUID, uuid4

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.db.session import SessionLocal, engine
from app.domains.access import inventory
from app.domains.monitoring import observations
from app.domains.monitoring.observation_worker import claim_due_schedule
from app.main import app
from tests.test_local_access import PASSWORD, WRITE


def test_observations_and_schedules_are_scoped(monkeypatch):
    monkeypatch.setenv("MONITORAI_OBSERVATION_WORKER", "0")
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_USERNAME", "phase-one-admin")
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_PASSWORD", PASSWORD)
    monkeypatch.setenv("MONITORAI_AZURE_ENCRYPTION_KEY", Fernet.generate_key().decode())
    primary, secondary = str(uuid4()), str(uuid4())
    status = "synced"
    resource = {"id": f"/subscriptions/{primary}/resourceGroups/test/providers/Microsoft.Compute/virtualMachines/test",
                "name": "test", "type": "Microsoft.Compute/virtualMachines", "resource_group": "test", "location": "eastus"}

    async def fake_inventory(values, subscription_id):
        assert values["client_secret"] == "fake"
        return inventory.InventoryCollection("synced", resources=[resource])

    async def fake_observations(context, kinds):
        if not context.inventory_exists:
            return {kind: ("inventory_required", {}, []) for kind in kinds}
        assert str(context.subscription_id) == primary and context.resources == [resource]
        payload = {"monitoring": {"resources": [{**resource, "health": "degraded", "health_status": "synced", "metrics": []}]},
                   "network": {"resources": [], "links": []},
                   "security": {"findings": [{"id": "a" * 64, "code": "storage", "title": "Example",
                                               "severity": "high", "evidence": [], "source": "azure"}],
                                "score": 15, "score_factors": [{"severity": "high", "count": 1, "weight": 15}]}}
        return {kind: (status, payload[kind] if status == "synced" else {}, []) for kind in kinds}

    monkeypatch.setattr(inventory, "collect_inventory", fake_inventory)
    monkeypatch.setattr(observations, "collect_observations", fake_observations)
    with TestClient(app, base_url="https://testserver") as client:
        assert client.post("/api/auth/login", headers=WRITE, json={
            "username": "phase-one-admin", "password": PASSWORD,
        }).status_code == 200
        admin = client.cookies.get("monitorai_session")
        first, second = [client.post("/api/auth/clients", headers=WRITE, json={"name": str(uuid4())})
                         .json()["client_id"] for _ in range(2)]
        first_headers, second_headers = [{**WRITE, "X-Client-ID": key} for key in (first, second)]
        credentials = {"tenant_id": str(uuid4()), "client_id": str(uuid4()), "client_secret": "fake",
                       "subscription_id": primary, "additional_subscription_ids": [secondary]}
        for headers in (first_headers, second_headers):
            assert client.put("/api/settings/azure/credentials", headers=headers, json=credentials).status_code == 200

        monitor = "/api/azure/monitoring"
        schedule = monitor + "/schedule"
        network = "/api/azure/network"
        security = "/api/azure/security"
        tracking = f"{security}/findings/{'a' * 64}/tracking"
        assert client.post(monitor + "/refresh", headers=first_headers).json()["status"] == "inventory_required"
        sync = client.post("/api/azure/inventory/refresh", headers=first_headers)
        assert sync.status_code == 200, sync.text
        for path in (monitor, network, security):
            refreshed = client.post(path + "/refresh", headers=first_headers)
            assert refreshed.status_code == 200, refreshed.text
            assert refreshed.json()["status"] == "synced"
            assert client.get(path, headers=second_headers).json()["status"] == "not_synced"
            assert client.get(path, headers=first_headers, params={"subscription_id": secondary}).json()["status"] == "not_synced"

        initial = client.get(monitor, headers=first_headers).json()["resources"][0]["health_alert"]
        assert initial["acknowledged_at"] is None
        alert = f"{monitor}/health-alerts/{initial['evidence_id']}/acknowledgement"
        assert client.put(alert, headers=second_headers).status_code == 409
        assert client.put(alert, headers=first_headers, params={"subscription_id": secondary}).status_code == 409
        saved_ack = client.put(alert, headers=first_headers)
        assert saved_ack.status_code == 200, saved_ack.text
        assert saved_ack.json()["acknowledged_at"]
        assert client.put(alert, headers=first_headers).json() == saved_ack.json()
        assert client.get(monitor, headers=first_headers).json()["resources"][0]["health_alert"] == saved_ack.json()

        changed = client.post(monitor + "/refresh", headers=first_headers).json()
        assert changed["resources"][0]["health_alert"]["acknowledged_at"] is None
        assert changed["resources"][0]["health_alert"]["evidence_id"] != initial["evidence_id"]
        assert client.put(alert, headers=first_headers).json() == saved_ack.json()
        superseded = f"{monitor}/health-alerts/{changed['resources'][0]['health_alert']['evidence_id']}/acknowledgement"
        assert client.post(monitor + "/refresh", headers=first_headers).status_code == 200
        assert client.put(superseded, headers=first_headers).status_code == 409
        events = client.get("/api/audit", headers=first_headers).json()
        assert sum(event["action"] == "acknowledge_azure_health_alert" for event in events) == 1

        details = {"status": "in_progress", "owner": "Cloud operations", "due_date": "2026-12-31"}
        assert client.put(tracking, headers=second_headers, json=details).status_code == 404
        saved = client.put(tracking, headers=first_headers, json=details)
        assert saved.status_code == 200, saved.text
        assert client.get(security, headers=first_headers).json()["findings"][0]["tracking"] == details
        assert client.get(security, headers=second_headers).json()["findings"] == []
        assert client.get(security, headers=first_headers).json()["score"] == 15

        status = "permission_failure"
        read = client.post(monitor + "/refresh", headers=first_headers).json()
        assert read["status"] == "permission_failure"
        assert read["last_success_at"] and read["resources"][0]["health"] == "degraded"
        assert client.get(schedule, headers=first_headers).json()["include_security"] is False
        assert client.put(schedule, headers=first_headers, json={"enabled": True, "interval_minutes": 4}).status_code == 422
        configured = client.put(schedule, headers=first_headers, json={
            "enabled": True, "interval_minutes": 5, "include_security": True,
        })
        assert configured.json()["enabled"] and configured.json()["include_security"]
        assert client.get(schedule, headers=second_headers).json()["enabled"] is False

        username = "observation-viewer-" + uuid4().hex
        assert client.post("/api/auth/users", headers=WRITE, json={"username": username, "password": PASSWORD}).status_code == 201
        assert client.post(f"/api/auth/clients/{first}/members", headers=WRITE,
                           json={"username": username, "role": "viewer"}).status_code == 204
        client.cookies.clear()
        assert client.post("/api/auth/login", headers=WRITE, json={"username": username, "password": PASSWORD}).status_code == 200
        assert client.get(monitor, headers=first_headers).status_code == 200
        assert client.get(network, headers=second_headers).status_code == 403
        assert client.post(monitor + "/refresh", headers=first_headers).status_code == 403
        assert client.put(tracking, headers=first_headers, json=details).status_code == 403
        assert client.put(alert, headers=first_headers).status_code == 403
        assert client.put(schedule, headers=first_headers, json={"enabled": False, "interval_minutes": 5}).status_code == 403
        client.cookies.clear()
        client.cookies.set("monitorai_session", admin)

    async def verify_claim():
        try:
            claim = await claim_due_schedule()
            assert tuple(map(str, claim[:2])) == (first, primary)
            assert isinstance(claim[2], UUID) and claim[3] is True
            async with SessionLocal() as db:
                assert await observations.refresh_observations(
                    db, UUID(first), UUID(primary), observations.KINDS, schedule_generation=uuid4(),
                ) == {}
            assert await claim_due_schedule() is None
        finally:
            await engine.dispose()

    asyncio.run(verify_claim())
