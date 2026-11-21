"""Mocked tests for M10 Azure Resource Intelligence."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.enums import AzurePreflightStatus
from app.models import (
    Architecture,
    ArchitectureVersion,
    AzureConnection,
    AzureIntelligenceSnapshot,
    AzurePreflightResult,
    Resource,
    ResourceCatalog,
)
from app.services import (
    AzureResourceIntelligenceService,
    ArchitectureVersioningService,
    AzureSdkReadOnlyClient,
    TerraformExecutionService,
    TerraformGenerator,
)


VM = "microsoft.compute/virtualmachines"
NOW = datetime(2026, 10, 1, 10, 30, tzinfo=timezone.utc)


class FakeAzureClient:
    def __init__(self):
        self.calls: list[str] = []
        self.subscription = {"subscription_id": "sub-a", "display_name": "Test subscription", "state": "Enabled"}
        self.locations = [{"name": "eastus", "display_name": "East US", "regional_display_name": "(US) East US", "aliases": []}]
        self.resource_groups = [{"id": "/subscriptions/sub-a/resourceGroups/rg", "name": "rg", "location": "eastus"}]
        self.resources = [{"id": "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm", "name": "vm", "type": VM, "location": "eastus", "resourceGroup": "rg"}]
        self.providers = [{"namespace": "Microsoft.Compute", "registration_state": "Registered"}]
        self.resource_types = [{"provider_namespace": "Microsoft.Compute", "resource_type": "Microsoft.Compute/virtualMachines", "api_versions": ["2026-01-01", "2025-01-01"], "preferred_api_version": "2026-01-01", "locations": ["East US"], "capabilities": {}, "restrictions": [], "source": "AZURE_RESOURCE_MANAGER"}]
        self.skus = [{"resource_type": "Microsoft.Compute/virtualMachines", "name": "Standard_D2s_v5", "tier": "Standard", "family": "standardDSv5Family", "size": "D2s_v5", "locations": ["eastus"], "location_info": [{"location": "eastus", "zones": ["1", "2", "3"]}], "capabilities": {"AcceleratedNetworkingEnabled": "True", "PremiumIO": "True"}, "restrictions": [], "source": "AZURE_COMPUTE_RESOURCE_SKUS"}]
        self.quotas = [{"provider_namespace": "Microsoft.Compute", "region": "eastus", "name": "cores", "current_usage": 2, "limit": 10, "unit": "Count", "source": "AZURE_COMPUTE_USAGE"}]

    def _return(self, name, value):
        self.calls.append(name)
        return value

    def get_subscription(self): return self._return("subscription", self.subscription)
    def list_locations(self): return self._return("locations", self.locations)
    def list_resource_groups(self): return self._return("resource_groups", self.resource_groups)
    def list_resources(self): return self._return("resources", self.resources)
    def list_providers(self): return self._return("providers", self.providers)
    def list_resource_types(self): return self._return("resource_types", self.resource_types)
    def list_skus(self): return self._return("skus", self.skus)
    def list_quotas(self, regions): return self._return("quotas", self.quotas)


class StatusError(Exception):
    def __init__(self, status_code):
        self.status_code = status_code


class FailingClient(FakeAzureClient):
    def __init__(self, error):
        super().__init__()
        self.error = error

    def get_subscription(self):
        raise self.error


@pytest.fixture
def azure_config():
    return Settings(
        _env_file=None,
        azure_tenant_id="tenant-a",
        azure_subscription_id="sub-a",
        azure_intelligence_cache_ttl_seconds=3600,
    )


@pytest.fixture
def snapshot(db: Session, azure_config):
    return AzureResourceIntelligenceService.refresh(db, FakeAzureClient(), azure_config, ["eastus"], "4.0.0", NOW)


def create_architecture(db: Session, sku=True, properties=None):
    db.add(ResourceCatalog(
        provider="azure",
        resource_type=VM,
        display_name="Virtual Machine",
        category="compute",
        version="1.0",
        enabled=True,
        terraform_mapping={"terraform_type": "azurerm_windows_virtual_machine", "provider": "azurerm"},
    ))
    architecture = Architecture(name="M10", provider="azure")
    db.add(architecture)
    db.flush()
    version = ArchitectureVersion(architecture_id=architecture.id, version_number="1.0", version_sequence=1, status="DRAFT")
    db.add(version)
    db.flush()
    resource = Resource(
        architecture_version_id=version.id,
        resource_key="vm",
        resource_type=VM,
        name="vm",
        location="eastus",
        sku={"name": "Standard_D2s_v5"} if sku else None,
        properties=properties or {},
    )
    db.add(resource)
    db.commit()
    return architecture, version, resource


def test_connection_success(azure_config):
    result = AzureResourceIntelligenceService.connection_status(azure_config, FakeAzureClient())
    assert result["status"] == "CONNECTED"


@pytest.mark.parametrize("error,expected", [(StatusError(401), "AUTHENTICATION_FAILED"), (StatusError(403), "AUTHORIZATION_FAILED"), (TimeoutError(), "TIMEOUT"), (ConnectionError(), "UNAVAILABLE")])
def test_connection_failure_normalization(azure_config, error, expected):
    assert AzureResourceIntelligenceService.connection_status(azure_config, FailingClient(error))["status"] == expected


def test_connection_configuration_error():
    result = AzureResourceIntelligenceService.connection_status(Settings(_env_file=None, azure_tenant_id=None, azure_subscription_id=None))
    assert result["status"] == "CONFIGURATION_ERROR"


def test_failed_refresh_persists_normalized_connection_status(db, azure_config):
    with pytest.raises(Exception) as caught:
        AzureResourceIntelligenceService.refresh(db, FailingClient(StatusError(401)), azure_config, now=NOW)
    connection = db.query(AzureConnection).one()
    assert getattr(caught.value, "code") == "AZURE_AUTHENTICATION_FAILED"
    assert connection.status == "AUTHENTICATION_FAILED"


def test_refresh_discovers_normalized_resources(snapshot):
    assert snapshot.resources[0]["type"].casefold() == VM
    assert snapshot.subscription_id == "sub-a"


def test_resource_type_discovery(snapshot):
    result = AzureResourceIntelligenceService.resource_type_intelligence(snapshot, VM)
    assert result["status"] == "SUPPORTED"
    assert result["api_version"] == "2026-01-01"


def test_unknown_resource_type_remains_unknown(snapshot):
    assert AzureResourceIntelligenceService.resource_type_intelligence(snapshot, "Microsoft.Fake/widgets")["status"] == "UNKNOWN"


def test_region_identifier_supported_from_display_name(snapshot):
    assert AzureResourceIntelligenceService.region_intelligence(snapshot, VM, "eastus")["status"] == "SUPPORTED"


def test_region_display_name_supported(snapshot):
    assert AzureResourceIntelligenceService.region_intelligence(snapshot, VM, "East US")["status"] == "SUPPORTED"


def test_region_unsupported(snapshot):
    assert AzureResourceIntelligenceService.region_intelligence(snapshot, VM, "westus")["status"] == "UNSUPPORTED"


def test_region_not_blindly_normalized(snapshot):
    assert AzureResourceIntelligenceService.region_intelligence(snapshot, VM, "east us 2")["status"] == "UNSUPPORTED"


def test_sku_supported(snapshot):
    result = AzureResourceIntelligenceService.sku_intelligence(snapshot, VM, "eastus", "Standard_D2s_v5")
    assert result["status"] == "SUPPORTED"
    assert result["capabilities"]["PremiumIO"] == "True"


def test_sku_unsupported_region(snapshot):
    assert AzureResourceIntelligenceService.sku_intelligence(snapshot, VM, "westus", "Standard_D2s_v5")["status"] == "UNSUPPORTED"


def test_sku_unknown(snapshot):
    assert AzureResourceIntelligenceService.sku_intelligence(snapshot, VM, "eastus", "Standard_Unknown")["status"] == "UNKNOWN"


def test_sku_restriction_overrides_location(snapshot):
    snapshot.skus[0]["restrictions"] = [{"type": "Location", "values": ["eastus"]}]
    assert AzureResourceIntelligenceService.sku_intelligence(snapshot, VM, "eastus", "Standard_D2s_v5")["status"] == "UNSUPPORTED"


def test_provider_registered(snapshot):
    assert AzureResourceIntelligenceService.provider_intelligence(snapshot, "microsoft.compute")["status"] == "REGISTERED"


def test_provider_not_registered(snapshot):
    snapshot.providers[0]["registration_state"] = "NotRegistered"
    assert AzureResourceIntelligenceService.provider_intelligence(snapshot, "Microsoft.Compute")["status"] == "NOT_REGISTERED"


def test_provider_unknown(snapshot):
    assert AzureResourceIntelligenceService.provider_intelligence(snapshot, "Microsoft.Storage")["status"] == "UNKNOWN"


def test_api_versions_preserved(snapshot):
    result = AzureResourceIntelligenceService.resource_type_intelligence(snapshot, VM)
    metadata = next(item for item in snapshot.resource_types if item["resource_type"] == "Microsoft.Compute/virtualMachines")
    assert result["api_version"] == metadata["api_versions"][0]


def test_capabilities_are_evidence_not_invented(snapshot):
    result = AzureResourceIntelligenceService.sku_intelligence(snapshot, VM, "eastus", "Standard_D2s_v5")
    assert result["capabilities"] == {"AcceleratedNetworkingEnabled": "True", "PremiumIO": "True"}
    assert "burst" not in result["capabilities"]


def test_quota_available(snapshot):
    assert AzureResourceIntelligenceService.quota_intelligence(snapshot, "cores", "eastus", 8)["status"] == "AVAILABLE"


def test_quota_insufficient(snapshot):
    assert AzureResourceIntelligenceService.quota_intelligence(snapshot, "cores", "eastus", 9)["status"] == "INSUFFICIENT"


def test_quota_unknown(snapshot):
    assert AzureResourceIntelligenceService.quota_intelligence(snapshot, "publicIPs", "eastus", 1)["status"] == "UNKNOWN"


def test_snapshot_creation(snapshot):
    assert snapshot.snapshot_sequence == 1
    assert len(snapshot.snapshot_hash) == 64


def test_snapshot_hash_stability():
    left = {"b": [2, 1], "a": "value"}
    right = {"a": "value", "b": [2, 1]}
    assert AzureResourceIntelligenceService.stable_hash(left) == AzureResourceIntelligenceService.stable_hash(right)


def test_new_data_creates_new_immutable_snapshot(db, azure_config, snapshot):
    original_hash = snapshot.snapshot_hash
    client = FakeAzureClient()
    client.providers.append({"namespace": "Microsoft.Storage", "registration_state": "Registered"})
    second = AzureResourceIntelligenceService.refresh(db, client, azure_config, now=NOW + timedelta(minutes=1))
    db.refresh(snapshot)
    assert second.id != snapshot.id
    assert second.snapshot_sequence == 2
    assert second.snapshot_hash != original_hash
    assert snapshot.snapshot_hash == original_hash


def test_snapshot_freshness(snapshot):
    result = AzureResourceIntelligenceService.freshness(snapshot, NOW + timedelta(minutes=30))
    assert result == {"fresh": True, "freshness": "FRESH", "retrieved_at": snapshot.retrieved_at, "expires_at": snapshot.expires_at}


def test_expired_snapshot_is_stale(snapshot):
    assert AzureResourceIntelligenceService.freshness(snapshot, NOW + timedelta(hours=2))["freshness"] == "STALE"


def test_explicit_refresh_calls_all_read_operations(db, azure_config):
    client = FakeAzureClient()
    AzureResourceIntelligenceService.refresh(db, client, azure_config, ["eastus"], now=NOW)
    assert set(client.calls) == {"subscription", "locations", "resource_groups", "resources", "providers", "resource_types", "skus", "quotas"}


def test_preflight_success(db, azure_config, snapshot):
    architecture, version, _ = create_architecture(db)
    result = AzureResourceIntelligenceService.preflight(db, architecture.id, version.id, snapshot.id, azure_config, NOW)
    assert result.status == "PASSED"
    assert result.azure_snapshot_id == snapshot.id


def test_preflight_failure_for_unavailable_sku(db, azure_config, snapshot):
    architecture, version, _ = create_architecture(db)
    snapshot.skus[0]["locations"] = ["westus"]
    result = AzureResourceIntelligenceService.preflight(db, architecture.id, version.id, snapshot.id, azure_config, NOW)
    assert result.status == "FAILED"
    assert any(item["code"] == "AZURE_SKU_UNAVAILABLE" for item in result.findings)


def test_preflight_unknown_remains_unknown(db, azure_config, snapshot):
    architecture, version, _ = create_architecture(db)
    snapshot.skus = []
    result = AzureResourceIntelligenceService.preflight(db, architecture.id, version.id, snapshot.id, azure_config, NOW)
    assert result.status == "UNKNOWN"
    assert any(item["code"] == "AZURE_SKU_AVAILABILITY_UNKNOWN" for item in result.findings)


def test_preflight_detects_capability_mismatch(db, azure_config, snapshot):
    architecture, version, _ = create_architecture(db, properties={"required_capabilities": {"PremiumIO": False}})
    result = AzureResourceIntelligenceService.preflight(db, architecture.id, version.id, snapshot.id, azure_config, NOW)
    assert result.status == "FAILED"
    assert any(item["code"] == "AZURE_CAPABILITY_UNSUPPORTED" for item in result.findings)


def test_stale_preflight_reports_warning(db, azure_config, snapshot):
    architecture, version, _ = create_architecture(db)
    result = AzureResourceIntelligenceService.preflight(db, architecture.id, version.id, snapshot.id, azure_config, NOW + timedelta(hours=2))
    assert result.status == "UNKNOWN"
    assert any(item["code"] == "AZURE_DATA_STALE" for item in result.findings)


def test_secret_fields_are_not_persisted(db, azure_config):
    client = FakeAzureClient()
    client.resources[0]["access_token"] = "unsafe"
    client.resources[0]["properties"] = {"enabled": True, "client_secret": "unsafe"}
    saved = AzureResourceIntelligenceService.refresh(db, client, azure_config, now=NOW)
    serialized = str(saved.resources).casefold()
    assert "unsafe" not in serialized
    assert "token" not in serialized
    assert saved.resources[0]["properties"] == {"enabled": True}


def test_no_write_operation_is_exposed():
    public = {name for name in dir(AzureSdkReadOnlyClient) if not name.startswith("_")}
    assert not public.intersection({"create", "update", "delete", "deploy", "register", "begin_create_or_update"})


def test_subscription_snapshots_are_isolated(db, azure_config):
    first = AzureResourceIntelligenceService.refresh(db, FakeAzureClient(), azure_config, now=NOW)
    other_config = Settings(_env_file=None, azure_tenant_id="tenant-b", azure_subscription_id="sub-b")
    other_client = FakeAzureClient()
    other_client.subscription["subscription_id"] = "sub-b"
    second = AzureResourceIntelligenceService.refresh(db, other_client, other_config, now=NOW)
    assert AzureResourceIntelligenceService.get_snapshot(db, first.id, other_config) is None
    assert AzureResourceIntelligenceService.get_snapshot(db, second.id, azure_config) is None


def test_refresh_lock_is_scoped_by_subscription():
    first = AzureResourceIntelligenceService._scope_lock("tenant:sub-a")
    assert first is AzureResourceIntelligenceService._scope_lock("tenant:sub-a")
    assert first is not AzureResourceIntelligenceService._scope_lock("tenant:sub-b")


@pytest.mark.parametrize("error,code", [(StatusError(401), "AZURE_AUTHENTICATION_FAILED"), (StatusError(403), "AZURE_AUTHORIZATION_FAILED"), (StatusError(404), "AZURE_RESOURCE_NOT_FOUND"), (StatusError(429), "AZURE_RATE_LIMITED"), (TimeoutError(), "AZURE_TIMEOUT"), (ConnectionError(), "AZURE_API_UNAVAILABLE"), (Exception(), "AZURE_UNKNOWN_ERROR")])
def test_api_error_normalization(error, code):
    normalized = AzureResourceIntelligenceService.normalize_error(error)
    assert normalized.code == code
    assert "Exception" not in str(normalized)


def test_m6_static_only_default_is_preserved(db):
    architecture, version, _ = create_architecture(db, sku=False)
    result = TerraformGenerator.generate(db, architecture.id, version.id)
    assert result["intelligence_mode"] == "STATIC_ONLY"


def test_m6_azure_validated_requires_matching_successful_preflight(db, azure_config, snapshot):
    architecture, version, _ = create_architecture(db, sku=False)
    failed = AzurePreflightResult(architecture_id=architecture.id, architecture_version_id=version.id, azure_snapshot_id=snapshot.id, architecture_snapshot_hash=ArchitectureVersioningService.snapshot_hash(db, architecture.id, version.id), status="FAILED", findings=[], result_hash="f" * 64)
    db.add(failed)
    db.commit()
    result = TerraformGenerator.generate(db, architecture.id, version.id, intelligence_mode="AZURE_VALIDATED", azure_preflight_id=failed.id)
    assert result["status"] == "BLOCKED"
    assert result["azure_preflight_id"] == failed.id


def test_m7_metadata_compatibility(db, azure_config, snapshot, tmp_path, monkeypatch):
    architecture, version, _ = create_architecture(db, sku=False)
    snapshot.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    preflight = AzurePreflightResult(architecture_id=architecture.id, architecture_version_id=version.id, azure_snapshot_id=snapshot.id, architecture_snapshot_hash=ArchitectureVersioningService.snapshot_hash(db, architecture.id, version.id), status=AzurePreflightStatus.PASSED.value, findings=[], result_hash="a" * 64)
    db.add(preflight)
    db.commit()
    monkeypatch.setattr(settings, "terraform_workspace_root", str(tmp_path))
    execution = TerraformExecutionService.prepare_workspace(db, architecture.id, version.id, azure_preflight_id=preflight.id)
    assert execution.azure_snapshot_id == snapshot.id
    assert execution.azure_preflight_id == preflight.id


def test_m6_rejects_expired_preflight(db, azure_config, snapshot):
    architecture, version, _ = create_architecture(db, sku=False)
    snapshot.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    preflight = AzurePreflightResult(architecture_id=architecture.id, architecture_version_id=version.id, azure_snapshot_id=snapshot.id, architecture_snapshot_hash=ArchitectureVersioningService.snapshot_hash(db, architecture.id, version.id), status="PASSED", findings=[], result_hash="b" * 64)
    db.add(preflight)
    db.commit()
    result = TerraformGenerator.generate(db, architecture.id, version.id, intelligence_mode="AZURE_VALIDATED", azure_preflight_id=preflight.id)
    assert any(item["code"] == "AZURE_PREFLIGHT_STALE" for item in result["errors"])


def test_m6_rejects_preflight_after_draft_change(db, azure_config, snapshot):
    architecture, version, resource = create_architecture(db, sku=False)
    snapshot.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    preflight = AzurePreflightResult(architecture_id=architecture.id, architecture_version_id=version.id, azure_snapshot_id=snapshot.id, architecture_snapshot_hash=ArchitectureVersioningService.snapshot_hash(db, architecture.id, version.id), status="PASSED", findings=[], result_hash="c" * 64)
    db.add(preflight)
    db.commit()
    resource.name = "changed-after-preflight"
    db.commit()
    result = TerraformGenerator.generate(db, architecture.id, version.id, intelligence_mode="AZURE_VALIDATED", azure_preflight_id=preflight.id)
    assert any(item["code"] == "AZURE_PREFLIGHT_STALE" for item in result["errors"])
