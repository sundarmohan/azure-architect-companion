from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.main import app
from tests.test_local_access import PASSWORD, WRITE


def test_compliance_reviews_are_scoped_and_viewer_read_only(monkeypatch):
    monkeypatch.setenv("MONITORAI_OBSERVATION_WORKER", "0")
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_USERNAME", "phase-one-admin")
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_PASSWORD", PASSWORD)
    monkeypatch.setenv("MONITORAI_AZURE_ENCRYPTION_KEY", Fernet.generate_key().decode())
    subscription = str(uuid4())
    credentials = {
        "tenant_id": str(uuid4()), "client_id": str(uuid4()),
        "client_secret": "fake", "subscription_id": subscription,
    }
    path = "/api/compliance/reviews"
    params = {"subscription_id": subscription}
    payload = {
        "state": "action_required", "note": "Review Azure storage configuration.",
        "action": "Require HTTPS transfer.", "owner": "Cloud operations",
        "due_date": "2026-12-31", "action_status": "planned",
    }
    with TestClient(app, base_url="https://testserver") as client:
        assert client.get(path, params=params).status_code == 401
        assert client.post("/api/auth/login", headers=WRITE, json={
            "username": "phase-one-admin", "password": PASSWORD,
        }).status_code == 200
        first, other = [client.post("/api/auth/clients", headers=WRITE, json={"name": str(uuid4())})
                        .json()["client_id"] for _ in range(2)]
        own, foreign = [{**WRITE, "X-Client-ID": client_id} for client_id in (first, other)]
        for headers in (own, foreign):
            assert client.put("/api/settings/azure/credentials", headers=headers, json=credentials).status_code == 200
        assert client.put(f"{path}/transport", params=params, headers=own,
                          json={"state": "action_required", "note": "Needs action"}).status_code == 422
        assert client.put(f"{path}/transport", params=params, headers=own, json={
            **payload, "snapshot_attempt_at": "2026-11-01T00:00:00Z",
        }).status_code == 409
        saved = client.put(f"{path}/transport", params=params, headers=own, json=payload)
        assert saved.status_code == 200, saved.text
        row = saved.json()
        assert row["topic"] == "transport"
        assert row["action_status"] == "planned"
        assert row["evidence_at"] is None
        assert client.get(path, params=params, headers=own).json() == [row]
        assert client.get(path, params=params, headers=foreign).json() == []
        assert client.get(path, params={"subscription_id": str(uuid4())}, headers=own).status_code == 404

        catalog = client.get("/api/compliance/catalog", headers=own).json()
        assert catalog["version"] == 1
        assert {entry["framework"] for entry in catalog["entries"]} == {"HIPAA", "SOC 2", "ISO/IEC 27001", "PCI DSS"}
        framework = f"{path}/hipaa_transport_v1"
        assert client.put(framework, params=params, headers=own, json={
            **payload, "applicability": "undetermined", "outcome": "pass",
        }).status_code == 422
        assert client.put(framework, params=params, headers=own, json={
            **payload, "applicability": "not_applicable", "outcome": "fail",
        }).status_code == 422
        assert client.put(f"{path}/transport", params=params, headers=own, json={
            **payload, "applicability": "applicable", "outcome": "unable_to_validate",
        }).status_code == 422
        saved_framework = client.put(framework, params=params, headers=own, json={
            **payload, "applicability": "applicable", "outcome": "unable_to_validate",
        })
        assert saved_framework.status_code == 200, saved_framework.text
        framework_row = saved_framework.json()
        assert framework_row["applicability"] == "applicable"
        assert framework_row["outcome"] == "unable_to_validate"
        assert client.get(path, params=params, headers=own).json() == [framework_row, row]
        assert client.get(path, params=params, headers=foreign).json() == []
        username = f"compliance-viewer-{uuid4().hex}"
        assert client.post("/api/auth/users", headers=WRITE,
                           json={"username": username, "password": PASSWORD}).status_code == 201
        assert client.post(f"/api/auth/clients/{first}/members", headers=WRITE,
                           json={"username": username, "role": "viewer"}).status_code == 204
        client.cookies.clear()
        assert client.post("/api/auth/login", headers=WRITE,
                           json={"username": username, "password": PASSWORD}).status_code == 200
        assert client.get(path, params=params, headers=own).json() == [framework_row, row]
        assert client.get(path, params=params, headers=foreign).status_code == 403
        assert client.put(f"{path}/transport", params=params, headers=own, json=payload).status_code == 403
