"""HTTP integration coverage for M11 conformance APIs."""

from app.core.config import settings
from app.services import ConformanceEngine
from tests.test_conformance import actual_vm, add_catalog, create_desired, create_snapshot


def configure(monkeypatch):
    monkeypatch.setattr(settings, "azure_tenant_id", "tenant-a")
    monkeypatch.setattr(settings, "azure_subscription_id", "sub-a")


def seed(db, monkeypatch, actual=None):
    configure(monkeypatch)
    architecture, version, _, _ = create_desired(db)
    add_catalog(db)
    snapshot = create_snapshot(db, actual if actual is not None else [actual_vm()])
    return architecture, version, snapshot


def test_run_and_get_conformance(client, db, monkeypatch):
    architecture, version, snapshot = seed(db, monkeypatch)
    created = client.post(f"/architectures/{architecture.id}/versions/{version.id}/conformance", json={"azure_snapshot_id": str(snapshot.id)})
    assert created.status_code == 201
    assessment_id = created.json()["id"]
    detail = client.get(f"/architectures/{architecture.id}/versions/{version.id}/conformance/{assessment_id}")
    assert detail.status_code == 200
    assert detail.json()["overall_status"] == "CONFORMANT"


def test_conformance_history_and_latest_drift(client, db, monkeypatch):
    architecture, version, snapshot = seed(db, monkeypatch, [])
    client.post(f"/architectures/{architecture.id}/versions/{version.id}/conformance", json={"azure_snapshot_id": str(snapshot.id)})
    history = client.get(f"/architectures/{architecture.id}/versions/{version.id}/drift/history")
    latest = client.get(f"/architectures/{architecture.id}/versions/{version.id}/drift")
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert latest.json()["overall_status"] == "DRIFTED"


def test_compare_assessments_endpoint(client, db, monkeypatch):
    architecture, version, first_snapshot = seed(db, monkeypatch, [])
    first = ConformanceEngine.assess(db, architecture.id, version.id, first_snapshot.id)
    second_snapshot = create_snapshot(db, [actual_vm(location="westus")], sequence=2)
    second = ConformanceEngine.assess(db, architecture.id, version.id, second_snapshot.id)
    response = client.get(f"/architectures/{architecture.id}/versions/{version.id}/conformance/compare/{first.id}/{second.id}")
    assert response.status_code == 200
    assert response.json()["new_drift"]


def test_conformance_api_normalizes_missing_snapshot(client, db, monkeypatch):
    architecture, version, _ = seed(db, monkeypatch)
    response = client.post(f"/architectures/{architecture.id}/versions/{version.id}/conformance", json={"azure_snapshot_id": "00000000-0000-0000-0000-000000000000"})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "AZURE_SNAPSHOT_NOT_FOUND"


def test_conformance_request_rejects_unknown_fields(client, db, monkeypatch):
    architecture, version, snapshot = seed(db, monkeypatch)
    response = client.post(f"/architectures/{architecture.id}/versions/{version.id}/conformance", json={"azure_snapshot_id": str(snapshot.id), "azure_url": "https://example.invalid"})
    assert response.status_code == 422
