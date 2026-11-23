from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.domains.assessments.routes import RiskAcceptanceRead
from app.domains.assessments.sla import finding_sla
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
        policy_path = PATH + "/sla-policy"
        policy = {"critical_days": 1, "high_days": 10, "medium_days": 30, "low_days": 60, "informational_days": 90}
        assert client.get(policy_path, headers=own).json() is None
        assert client.put(policy_path, headers=own, json={**policy, "critical_days": 0}).status_code == 422
        saved_policy_response = client.put(policy_path, headers=own, json=policy)
        assert saved_policy_response.status_code == 200, saved_policy_response.text
        saved_policy = saved_policy_response.json()
        assert client.put(policy_path, headers=own, json=policy).json() == saved_policy
        assert client.put(policy_path, headers=own, json={**policy, "high_days": 20}).status_code == 409
        assert client.get(policy_path, headers=foreign).json() is None
        sla = client.get(assessment, headers=own).json()["findings"][0]["sla"]
        assert sla["age_source"] == "observed" and sla["deadline_source"] == "policy"
        assert sla["deadline"] == "2026-01-11"
        finding = f"{assessment}/findings/{client.get(assessment, headers=own).json()['findings'][0]['id']}"
        risk = finding + "/risk-acceptance"
        today = datetime.now(timezone.utc).date()
        decision = {"rationale": "Approved temporary exception", "expires_on": str(today + timedelta(days=10))}
        assert client.put(risk, headers=own, json={**decision, "expires_on": str(today)}).status_code == 422
        assert client.put(risk, headers=own, json={**decision, "rationale": " "}).status_code == 422
        assert client.put(risk, headers=foreign, json=decision).status_code == 404
        recorded = client.put(risk, headers=own, json=decision)
        assert recorded.status_code == 200, recorded.text
        first_decision = recorded.json()
        assert first_decision["actor_username"] == "phase-one-admin" and first_decision["active"]
        assert client.put(risk, headers=own, json=decision).json() == first_decision
        replacement = {**decision, "rationale": "Updated exception rationale"}
        assert client.put(risk, headers=own, json=replacement).status_code == 409
        changed = client.put(risk, headers=own, json={**replacement, "previous_id": first_decision["id"]})
        assert changed.status_code == 200, changed.text
        updated_decision = changed.json()
        assert updated_decision["id"] != first_decision["id"]
        current = client.get(assessment, headers=own).json()["findings"][0]
        assert current["status"] == "open" and current["risk_acceptance"] == updated_decision
        events = client.get("/api/audit", headers=own).json()
        assert sum(event["action"] == "record_vulnerability_risk_acceptance" for event in events) == 2
        assert sum(event["action"] == "update_vulnerability_sla_policy" for event in events) == 1
        assert client.put(finding, headers=own, json={"status": "closed"}).status_code == 409
        for status in ("confirmed", "in_remediation", "ready_for_retest"):
            assert client.put(finding, headers=own, json={"status": status}).status_code == 200
        assert client.put(finding, headers=own, json={"status": "closed"}).status_code == 422
        closed = client.put(finding, headers=own, json={"status": "closed", "retest_note": "Human retest passed",
                                                       "owner": "Operations", "due_date": "2026-02-01"})
        assert closed.status_code == 200 and closed.json()["retest_note"] == "Human retest passed"
        assert closed.json()["risk_acceptance"] == updated_decision
        assert closed.json()["sla"]["deadline"] == "2026-02-01"
        assert closed.json()["sla"]["deadline_source"] == "manual" and closed.json()["sla"]["status"] == "closed"
        assert client.put(risk, headers=own, json={**decision, "previous_id": updated_decision["id"]}).status_code == 409
        history = client.get(assessment, headers=own).json()["findings"][0]["history"]
        assert [event["status"] for event in history] == ["confirmed", "in_remediation", "ready_for_retest", "closed"]

        username = "assessment-viewer-" + uuid4().hex
        assert client.post("/api/auth/users", headers=WRITE, json={"username": username, "password": PASSWORD}).status_code == 201
        assert client.post(f"/api/auth/clients/{first}/members", headers=WRITE,
                           json={"username": username, "role": "viewer"}).status_code == 204
        client.cookies.clear()
        assert client.post("/api/auth/login", headers=WRITE, json={"username": username, "password": PASSWORD}).status_code == 200
        assert client.get(assessment, headers=own).status_code == 200
        assert client.get(assessment, headers=own).json()["findings"][0]["risk_acceptance"] == updated_decision
        assert client.put(risk, headers=own, json=decision).status_code == 403
        assert client.get(policy_path, headers=own).json() == saved_policy
        assert client.put(policy_path, headers=own, json=policy).status_code == 403
        portfolio = client.get(PATH + "/portfolio", headers=own)
        assert portfolio.status_code == 200, portfolio.text
        data = portfolio.json()
        assert not data["has_next"]
        assert [row["severity"] for row in data["findings"]] == ["critical", "high"]
        assert data["findings"][0]["assessment_id"] == other_assessment["id"]
        assert data["findings"][1]["status"] == "closed"
        assert data["findings"][1]["owner"] == "Operations"
        assert data["findings"][1]["due_date"] == "2026-02-01"
        assert data["findings"][1]["sla"] == closed.json()["sla"]
        assert client.get(PATH + "/portfolio", headers=foreign).status_code == 403
        assert client.post(PATH, headers=own, json=details).status_code == 403
        assert client.put(finding, headers=own, json={"status": "open"}).status_code == 403


def test_risk_acceptance_flags_utc_expiry():
    now = datetime.now(timezone.utc)
    decision = RiskAcceptanceRead(id=uuid4(), rationale="Reviewed", expires_on=now.date(),
                                  actor_username="reviewer", created_at=now - timedelta(days=1))
    assert decision.model_dump()["active"] is False


def test_sla_uses_import_date_when_observation_is_missing_and_manual_override_first():
    today = date(2026, 1, 11)
    finding = SimpleNamespace(created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), observed_at=None,
                              due_date=None, severity="high", status="open")
    policy = SimpleNamespace(high_days=10)
    sla = finding_sla(finding, policy, today)
    assert sla.age_days == 10 and sla.age_source == "imported"
    assert sla.status == "due_today"
    finding.due_date = date(2026, 1, 10)
    manual = finding_sla(finding, policy, today)
    assert manual.status == "overdue" and manual.deadline_source == "manual"
