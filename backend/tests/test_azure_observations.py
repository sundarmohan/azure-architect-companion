import asyncio
from datetime import datetime, timezone
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
    security_title = "Example"
    resource = {"id": f"/subscriptions/{primary}/resourceGroups/test/providers/Microsoft.Compute/virtualMachines/test",
                "name": "test", "type": "Microsoft.Compute/virtualMachines", "resource_group": "test", "location": "eastus"}

    async def fake_inventory(values, subscription_id):
        assert values["client_secret"] == "fake"
        return inventory.InventoryCollection("synced", resources=[resource])

    async def fake_observations(context, kinds):
        if not context.inventory_exists:
            return {kind: ("inventory_required", {}, []) for kind in kinds}
        assert str(context.subscription_id) == primary and context.resources == [resource]
        payload = {"monitoring": {"resources": [{**resource, "health": "degraded", "health_status": "synced",
                                                   "metrics": [{"name": "Percentage CPU", "aggregation": "average",
                                                                "unit": "Percent", "points": [{
                                                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                                                    "value": 82.5,
                                                                }]}]}]},
                   "network": {"resources": [], "links": []},
                   "security": {"findings": [{"id": "a" * 64, "code": "storage", "title": security_title,
                                               "severity": "high", "evidence": ["Recorded Azure setting"],
                                               "resource_id": resource["id"], "source": "azure",
                                               "observed_at": "2026-01-01T00:00:00Z"}],
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
        thresholds = monitor + "/thresholds"
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

        threshold = {"resource_id": resource["id"], "metric": "Percentage CPU", "aggregation": "average",
                     "direction": "above", "limit": 80}
        empty_threshold = client.get(thresholds, headers=second_headers)
        assert empty_threshold.status_code == 200 and empty_threshold.json()["threshold"] is None
        assert client.put(thresholds, headers=second_headers, json=threshold).status_code == 409
        saved_threshold = client.put(thresholds, headers=first_headers, json=threshold)
        assert saved_threshold.status_code == 200, saved_threshold.text
        assert saved_threshold.json()["assessment"]["status"] == "breached"
        assert saved_threshold.json()["assessment"]["value"] == 82.5
        assert saved_threshold.json()["threshold"]["unit"] == "Percent"
        assert client.get(thresholds, headers=first_headers).json()["threshold"]["limit"] == 80
        invalid_threshold = {**threshold, "metric": "Unsupported"}
        assert client.put(thresholds, headers=first_headers, json=invalid_threshold).status_code == 409

        initial = client.get(monitor, headers=first_headers).json()["resources"][0]["health_alert"]
        assert initial["acknowledged_at"] is None
        alert = f"{monitor}/health-alerts/{initial['evidence_id']}/acknowledgement"
        incident_create = f"{monitor}/health-alerts/{initial['evidence_id']}/incident"
        incidents = f"{monitor}/health-incidents"
        attention = incidents + "/attention"
        assert client.get(attention, headers=first_headers).json() == {
            "unassigned_incidents": [], "overdue_actions": [],
        }
        assert client.put(incident_create, headers=first_headers).status_code == 404
        assert client.put(alert, headers=second_headers).status_code == 409
        assert client.put(alert, headers=first_headers, params={"subscription_id": secondary}).status_code == 409
        saved_ack = client.put(alert, headers=first_headers)
        assert saved_ack.status_code == 200, saved_ack.text
        assert saved_ack.json()["acknowledged_at"]
        assert client.put(alert, headers=first_headers).json() == saved_ack.json()
        assert client.get(monitor, headers=first_headers).json()["resources"][0]["health_alert"] == saved_ack.json()
        created = client.put(incident_create, headers=first_headers)
        assert created.status_code == 200, created.text
        incident = created.json()
        assert incident["evidence_id"] == initial["evidence_id"]
        assert incident["resource_id"] == resource["id"] and incident["health"] == "degraded"
        assert incident["acknowledged_at"] == saved_ack.json()["acknowledged_at"]
        assert client.put(incident_create, headers=first_headers).json() == incident
        unassigned = client.get(attention, headers=first_headers).json()
        assert [item["id"] for item in unassigned["unassigned_incidents"]] == [incident["id"]]
        assert unassigned["overdue_actions"] == []
        assert client.put(incident_create, headers=second_headers).status_code == 404
        assert client.get(incidents, headers=second_headers).json() == {"incidents": [], "has_next": False}
        assert client.get(incidents, headers=first_headers, params={"subscription_id": secondary}).json()["incidents"] == []
        incident_path = f"{incidents}/{incident['id']}"
        assert client.put(incident_path, headers=first_headers,
                          json={"status": "resolved", "updated_at": incident["updated_at"]}).status_code == 422
        investigation = {"status": "investigating", "owner": "Cloud operations", "rca_note": "Reviewing availability",
                         "updated_at": incident["updated_at"]}
        updated = client.put(incident_path, headers=first_headers, json=investigation)
        assert updated.status_code == 200, updated.text
        assert updated.json()["owner"] == "Cloud operations"
        assert client.put(incident_path, headers=first_headers, json=investigation).json() == updated.json()
        assert client.put(incident_path, headers=first_headers,
                          json={**investigation, "owner": "Stale change"}).status_code == 409
        assert client.put(incident_path, headers=second_headers, json=investigation).status_code == 404
        actions = incident_path + "/actions"
        action_path = actions + "/" + str(uuid4())
        action = {"kind": "corrective", "title": "Review availability configuration", "owner": "Ops",
                  "status": "open", "due_date": "2020-12-31"}
        assert client.put(action_path, headers=second_headers, json=action).status_code == 404
        assert client.put(action_path, headers=first_headers,
                          params={"subscription_id": secondary}, json=action).status_code == 404
        assert client.put(action_path, headers=first_headers, json={**action, "owner": " "}).status_code == 422
        action_result = client.put(action_path, headers=first_headers, json=action)
        assert action_result.status_code == 200, action_result.text
        recorded = action_result.json()
        assert recorded["owner"] == "Ops" and recorded["status"] == "open"
        overdue = client.get(attention, headers=first_headers).json()
        assert overdue["unassigned_incidents"] == []
        assert overdue["overdue_actions"][0]["incident"]["id"] == incident["id"]
        assert overdue["overdue_actions"][0]["action"]["id"] == recorded["id"]
        assert client.put(action_path, headers=first_headers, json=action).json() == recorded
        followup = {**action, "status": "completed", "updated_at": recorded["updated_at"]}
        action_result = client.put(action_path, headers=first_headers, json=followup)
        assert action_result.status_code == 200, action_result.text
        completed = action_result.json()
        assert completed["status"] == "completed"
        assert client.put(action_path, headers=first_headers, json={**followup, "status": "in_progress"}).status_code == 409
        assert client.get(actions, headers=first_headers).json() == [completed]
        assert client.get(attention, headers=first_headers).json()["overdue_actions"] == []
        assert client.get(actions, headers=second_headers).status_code == 404
        evidence_path = incident_path + "/security-evidence"
        link_path = evidence_path + "/" + "a" * 64
        saved_security = client.get(security, headers=first_headers).json()
        version = {"collected_at": saved_security["last_success_at"]}
        assert client.put(link_path, headers=second_headers, json=version).status_code == 404
        assert client.put(link_path, headers=first_headers, params={"subscription_id": secondary}, json=version).status_code == 404
        assert client.put(link_path, headers=first_headers,
                          json={"collected_at": "2000-01-01T00:00:00Z"}).status_code == 409
        linked = client.put(link_path, headers=first_headers, json=version)
        assert linked.status_code == 200, linked.text
        evidence = linked.json()
        assert evidence["title"] == "Example" and evidence["source"] == "azure"
        assert evidence["resource_id"] == resource["id"] and evidence["observed_at"] == "2026-01-01T00:00:00Z"
        assert evidence["evidence"] == ["Recorded Azure setting"]
        security_title = "Changed after evidence linking"
        refreshed_security = client.post(security + "/refresh", headers=first_headers).json()
        assert refreshed_security["findings"][0]["title"] == security_title
        assert client.put(link_path, headers=first_headers, json={"collected_at": refreshed_security["last_success_at"]}).json() == evidence
        assert client.get(evidence_path, headers=first_headers).json() == [evidence]
        assert client.get(evidence_path, headers=second_headers).status_code == 404

        changed = client.post(monitor + "/refresh", headers=first_headers).json()
        assert changed["resources"][0]["health_alert"]["acknowledged_at"] is None
        assert changed["resources"][0]["health_alert"]["evidence_id"] != initial["evidence_id"]
        assert client.put(alert, headers=first_headers).json() == saved_ack.json()
        superseded = f"{monitor}/health-alerts/{changed['resources'][0]['health_alert']['evidence_id']}/acknowledgement"
        assert client.post(monitor + "/refresh", headers=first_headers).status_code == 200
        assert client.put(superseded, headers=first_headers).status_code == 409
        events = client.get("/api/audit", headers=first_headers).json()
        assert sum(event["action"] == "acknowledge_azure_health_alert" for event in events) == 1
        assert sum(event["action"] == "create_azure_health_incident" for event in events) == 1
        assert sum(event["action"] == "update_azure_health_incident" for event in events) == 1
        assert sum(event["action"] == "create_azure_health_incident_action" for event in events) == 1
        assert sum(event["action"] == "update_azure_health_incident_action" for event in events) == 1
        assert sum(event["action"] == "link_azure_incident_security_evidence" for event in events) == 1
        assert sum(event["action"] == "save_azure_metric_threshold" for event in events) == 1
        assert client.get(incidents, headers=first_headers).json()["incidents"] == [updated.json()]
        assert client.get(attention, headers=first_headers).status_code == 200

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
        assert client.get(incidents, headers=first_headers).json()["incidents"] == [updated.json()]
        assert client.put(incident_create, headers=first_headers).status_code == 403
        assert client.put(incident_path, headers=first_headers, json=investigation).status_code == 403
        assert client.get(actions, headers=first_headers).json() == [completed]
        assert client.put(action_path, headers=first_headers, json=followup).status_code == 403
        assert client.get(evidence_path, headers=first_headers).json() == [evidence]
        assert client.put(link_path, headers=first_headers, json=version).status_code == 403
        assert client.put(schedule, headers=first_headers, json={"enabled": False, "interval_minutes": 5}).status_code == 403
        assert client.get(thresholds, headers=first_headers).json()["threshold"]["limit"] == 80
        assert client.put(thresholds, headers=first_headers, json=threshold).status_code == 403
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
