"""HTTP integration tests for M10 using persisted mocked evidence."""

from datetime import datetime, timezone

from app.core.config import Settings, settings
from app.models import Architecture, ArchitectureVersion, Resource
from app.services import AzureResourceIntelligenceService

from tests.test_azure_intelligence import FakeAzureClient, VM


NOW = datetime(2026, 10, 1, 10, 30, tzinfo=timezone.utc)


def configure(monkeypatch):
    monkeypatch.setattr(settings, "azure_tenant_id", "tenant-a")
    monkeypatch.setattr(settings, "azure_subscription_id", "sub-a")
    monkeypatch.setattr(settings, "azure_intelligence_cache_ttl_seconds", 3600)


def seed_snapshot(db, monkeypatch):
    configure(monkeypatch)
    config = Settings(_env_file=None, azure_tenant_id="tenant-a", azure_subscription_id="sub-a")
    return AzureResourceIntelligenceService.refresh(db, FakeAzureClient(), config, ["eastus"], now=NOW)


def seed_architecture(db):
    architecture = Architecture(name="API M10", provider="azure")
    db.add(architecture)
    db.flush()
    version = ArchitectureVersion(architecture_id=architecture.id, version_number="1.0", version_sequence=1, status="DRAFT")
    db.add(version)
    db.flush()
    db.add(Resource(architecture_version_id=version.id, resource_key="vm", resource_type=VM, name="vm", location="eastus", sku={"name": "Standard_D2s_v5"}, properties={}))
    db.commit()
    return architecture, version


def test_status_endpoint_normalizes_connection(client, monkeypatch):
    monkeypatch.setattr(AzureResourceIntelligenceService, "connection_status", lambda: {"status": "CONNECTED", "tenant_id": "tenant-a", "subscription_id": "sub-a", "message": "Read-only Azure connection is available"})
    response = client.get("/azure/intelligence/status")
    assert response.status_code == 200
    assert response.json()["status"] == "CONNECTED"


def test_snapshot_list_and_detail_are_freshness_aware(client, db, monkeypatch):
    snapshot = seed_snapshot(db, monkeypatch)
    listed = client.get("/azure/intelligence/snapshots")
    detail = client.get(f"/azure/intelligence/snapshots/{snapshot.id}")
    assert listed.status_code == 200
    assert listed.json()[0]["snapshot_hash"] == snapshot.snapshot_hash
    assert detail.json()["freshness"] in {"FRESH", "STALE"}


def test_resource_type_region_endpoint(client, db, monkeypatch):
    seed_snapshot(db, monkeypatch)
    response = client.get(f"/azure/intelligence/resource-types/{VM}/regions", params={"region": "eastus"})
    assert response.status_code == 200
    assert response.json()["status"] == "SUPPORTED"


def test_resource_type_sku_endpoint(client, db, monkeypatch):
    seed_snapshot(db, monkeypatch)
    response = client.get(f"/azure/intelligence/resource-types/{VM}/skus", params={"region": "eastus"})
    assert response.status_code == 200
    assert response.json()[0]["name"] == "Standard_D2s_v5"


def test_provider_endpoint(client, db, monkeypatch):
    seed_snapshot(db, monkeypatch)
    response = client.get("/azure/intelligence/providers")
    assert response.status_code == 200
    assert response.json()[0]["status"] == "REGISTERED"


def test_quota_endpoint(client, db, monkeypatch):
    seed_snapshot(db, monkeypatch)
    response = client.get("/azure/intelligence/quotas/cores", params={"region": "eastus", "required": 9})
    assert response.status_code == 200
    assert response.json()["status"] == "INSUFFICIENT"


def test_preflight_endpoint_records_snapshot_reference(client, db, monkeypatch):
    snapshot = seed_snapshot(db, monkeypatch)
    architecture, version = seed_architecture(db)
    response = client.post(f"/architectures/{architecture.id}/versions/{version.id}/azure-preflight", json={"snapshot_id": str(snapshot.id)})
    assert response.status_code == 201
    assert response.json()["azure_snapshot_id"] == str(snapshot.id)


def test_refresh_rejects_caller_controlled_subscription(client):
    response = client.post("/azure/intelligence/refresh", json={"subscription_id": "other-subscription"})
    assert response.status_code == 422


def test_snapshot_from_another_subscription_is_not_returned(client, db, monkeypatch):
    configure(monkeypatch)
    other_config = Settings(_env_file=None, azure_tenant_id="tenant-b", azure_subscription_id="sub-b")
    other_client = FakeAzureClient()
    other_client.subscription["subscription_id"] = "sub-b"
    snapshot = AzureResourceIntelligenceService.refresh(db, other_client, other_config, now=NOW)
    response = client.get(f"/azure/intelligence/snapshots/{snapshot.id}")
    assert response.status_code == 404
