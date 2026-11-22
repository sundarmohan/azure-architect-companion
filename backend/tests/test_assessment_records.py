from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.test_local_access import PASSWORD, WRITE

PATH = "/api/assessments"


def test_assessment_scope_import_and_retest_lifecycle(monkeypatch):
    monkeypatch.setenv("MONITORAI_OBSERVATION_WORKER", "0")
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_USERNAME", "phase-one-admin")
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_PASSWORD", PASSWORD)
    with TestClient(app, base_url="https://testserver") as client:
        assert client.post("/api/auth/login", headers=WRITE, json={
            "username": "phase-one-admin", "password": PASSWORD,
        }).status_code == 200
        first, second = [client.post("/api/auth/clients", headers=WRITE, json={"name": str(uuid4())})
                         .json()["client_id"] for _ in range(2)]
        own, foreign = [{**WRITE, "X-Client-ID": workspace} for workspace in (first, second)]
        details = {"name": "Authorized review", "scope": "Approved environment and exclusions recorded in ticket",
                   "authorization": "Reference SEC-100", "environment": "staging",
                   "window_start": "2026-01-01T10:00:00Z", "window_end": "2026-01-01T14:00:00Z"}
        assert client.post(PATH, headers=own, json={**details, "window_end": details["window_start"]}).status_code == 422
        assert client.post(PATH, headers=own, json={**details, "window_start": "2026-01-01T10:00:00"}).status_code == 422
        created = client.post(PATH, headers=own, json=details)
        assert created.status_code == 201, created.text
        assessment = f"{PATH}/{created.json()['id']}"
        assert client.get(assessment, headers=foreign).status_code == 404
        assert client.get(PATH, headers=foreign).json() == []
        row = {"external_id": "provider-123", "title": "Configuration finding", "severity": "high",
               "source": "Approved Review", "evidence": "Sanitized operator observation",
               "observed_at": "2026-01-01T11:00:00Z"}
        assert client.post(assessment + "/findings/import", headers=foreign, json={"findings": [row]}).status_code == 404
        assert client.post(assessment + "/findings/import", headers=own, json={
            "findings": [{**row, "observed_at": "2026-01-02T11:00:00Z"}],
        }).status_code == 422
        imported = client.post(assessment + "/findings/import", headers=own, json={"findings": [row, row]})
        assert imported.status_code == 200, imported.text
        assert imported.json() == {"inserted": 1, "duplicates": 1}
        assert client.post(assessment + "/findings/import", headers=own, json={"findings": [row]}).json()["duplicates"] == 1
        other_assessment = client.post(PATH, headers=own, json={**details, "name": "Second review"}).json()
        assert client.post(f"{PATH}/{other_assessment['id']}/findings/import", headers=own, json={
            "findings": [{**row, "severity": "critical", "title": "Priority finding"}],
        }).status_code == 200
        assert client.get(PATH + "/portfolio", headers=foreign).json() == {"findings": [], "has_next": False}
        finding = f"{assessment}/findings/{client.get(assessment, headers=own).json()['findings'][0]['id']}"
        assert client.put(finding, headers=own, json={"status": "closed"}).status_code == 409
        for status in ("confirmed", "in_remediation", "ready_for_retest"):
            assert client.put(finding, headers=own, json={"status": status}).status_code == 200
        assert client.put(finding, headers=own, json={"status": "closed"}).status_code == 422
        closed = client.put(finding, headers=own, json={"status": "closed", "retest_note": "Human retest passed",
                                                       "owner": "Operations", "due_date": "2026-02-01"})
        assert closed.status_code == 200 and closed.json()["retest_note"] == "Human retest passed"
        history = client.get(assessment, headers=own).json()["findings"][0]["history"]
        assert [event["status"] for event in history] == ["confirmed", "in_remediation", "ready_for_retest", "closed"]

        username = "assessment-viewer-" + uuid4().hex
        assert client.post("/api/auth/users", headers=WRITE, json={"username": username, "password": PASSWORD}).status_code == 201
        assert client.post(f"/api/auth/clients/{first}/members", headers=WRITE,
                           json={"username": username, "role": "viewer"}).status_code == 204
        client.cookies.clear()
        assert client.post("/api/auth/login", headers=WRITE, json={"username": username, "password": PASSWORD}).status_code == 200
        assert client.get(assessment, headers=own).status_code == 200
        portfolio = client.get(PATH + "/portfolio", headers=own)
        assert portfolio.status_code == 200, portfolio.text
        data = portfolio.json()
        assert not data["has_next"]
        assert [row["severity"] for row in data["findings"]] == ["critical", "high"]
        assert data["findings"][0]["assessment_id"] == other_assessment["id"]
        assert data["findings"][1]["status"] == "closed"
        assert data["findings"][1]["owner"] == "Operations"
        assert data["findings"][1]["due_date"] == "2026-02-01"
        assert client.get(PATH + "/portfolio", headers=foreign).status_code == 403
        assert client.post(PATH, headers=own, json=details).status_code == 403
        assert client.put(finding, headers=own, json={"status": "open"}).status_code == 403
