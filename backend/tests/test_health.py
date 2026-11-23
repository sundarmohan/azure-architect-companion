from fastapi.testclient import TestClient

from app.main import app


def test_health(monkeypatch):
    monkeypatch.delenv("MONITORAI_BUILD_SHA", raising=False)
    monkeypatch.delenv("MONITORAI_BUILD_TIME", raising=False)
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok", "version": "2.2", "build": {"commit": None, "built_at": None},
    }


def test_health_reports_only_validated_build_provenance(monkeypatch):
    monkeypatch.setenv("MONITORAI_BUILD_SHA", "a" * 40)
    monkeypatch.setenv("MONITORAI_BUILD_TIME", "2026-11-23T15:30:00Z")
    payload = TestClient(app).get("/health").json()
    assert payload["build"] == {"commit": "a" * 40, "built_at": "2026-11-23T15:30:00Z"}

    monkeypatch.setenv("MONITORAI_BUILD_SHA", "not-a-commit")
    monkeypatch.setenv("MONITORAI_BUILD_TIME", "not-a-time")
    payload = TestClient(app).get("/health").json()
    assert payload["build"] == {"commit": None, "built_at": None}
