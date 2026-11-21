"""Deterministic M11 conformance and drift tests using M10 snapshot fixtures."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    Architecture,
    ArchitectureVersion,
    AzureConnection,
    AzureIntelligenceSnapshot,
    ConformanceAssessment,
    ConformanceEvent,
    Dependency,
    Relationship,
    Resource,
    ResourceCatalog,
    TerraformExecution,
)
from app.services import ConformanceEngine, ConformanceError


NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
VM = "microsoft.compute/virtualmachines"
RG = "microsoft.resources/resourcegroups"


@pytest.fixture
def config():
    return Settings(_env_file=None, azure_tenant_id="tenant-a", azure_subscription_id="sub-a")


def create_desired(db: Session, *, properties=None, tags=None, location="eastus", sku="Standard_D2s_v5", name="web-vm", parent=False):
    architecture = Architecture(name="Conformance", provider="azure")
    db.add(architecture)
    db.flush()
    version = ArchitectureVersion(architecture_id=architecture.id, version_number="1.0", version_sequence=1, status="DRAFT")
    db.add(version)
    db.flush()
    resource_group = None
    if parent:
        resource_group = Resource(architecture_version_id=version.id, resource_key="rg-main", resource_type=RG, name="rg-main", location=location, properties={}, tags={})
        db.add(resource_group)
        db.flush()
    resource = Resource(
        architecture_version_id=version.id,
        resource_key="web-vm",
        resource_type=VM,
        name=name,
        location=location,
        sku={"name": sku},
        properties=properties or {},
        tags=tags if tags is not None else {"env": "prod"},
        parent_resource_id=resource_group.id if resource_group else None,
    )
    db.add(resource)
    db.commit()
    return architecture, version, resource_group, resource


def add_catalog(db: Session, conformance_properties=None):
    existing = db.query(ResourceCatalog).filter(ResourceCatalog.resource_type == VM).first()
    if existing:
        existing.resource_metadata = {"conformance": {"properties": conformance_properties or []}}
        db.commit()
        return existing
    db.add(ResourceCatalog(
        provider="azure", resource_type=VM, display_name="VM", category="compute", version="1", enabled=True,
        resource_metadata={"conformance": {"properties": conformance_properties or []}},
    ))
    db.commit()


def create_snapshot(db: Session, resources, *, subscription="sub-a", sequence=1, snapshot_hash=None):
    connection = db.query(AzureConnection).filter(AzureConnection.subscription_id == subscription).first()
    if connection is None:
        tenant_id = "tenant-a" if subscription == "sub-a" else "tenant-b"
        connection = AzureConnection(tenant_id=tenant_id, subscription_id=subscription, status="CONNECTED")
        db.add(connection)
        db.flush()
    payload_hash = snapshot_hash or ConformanceEngine.stable_hash(resources)
    snapshot = AzureIntelligenceSnapshot(
        connection_id=connection.id,
        subscription_id=subscription,
        tenant_id=connection.tenant_id,
        snapshot_sequence=sequence,
        snapshot_hash=payload_hash,
        source_version="m10-v1",
        subscription_metadata={}, resource_groups=[], resource_types=[], regions=[], skus=[], providers=[], quotas=[], resources=resources,
        retrieved_at=NOW + timedelta(minutes=sequence), expires_at=NOW + timedelta(hours=2),
    )
    db.add(snapshot)
    db.commit()
    return snapshot


def actual_vm(**overrides):
    value = {
        "id": "/subscriptions/sub-a/resourceGroups/rg-main/providers/Microsoft.Compute/virtualMachines/web-vm",
        "resource_key": "web-vm",
        "name": "web-vm",
        "type": VM,
        "location": "eastus",
        "sku": {"name": "Standard_D2s_v5"},
        "tags": {"env": "prod"},
        "properties": {},
    }
    value.update(overrides)
    return value


def assess(db, config, resources, **desired):
    architecture, version, _, _ = create_desired(db, **desired)
    add_catalog(db)
    snapshot = create_snapshot(db, resources)
    return ConformanceEngine.assess(db, architecture.id, version.id, snapshot.id, config=config), architecture, version, snapshot


def statuses(assessment):
    return {item.status for item in assessment.findings}


def test_fully_conformant_architecture(db, config):
    assessment, _, _, _ = assess(db, config, [actual_vm()])
    assert assessment.overall_status == "CONFORMANT"
    assert assessment.summary["conformant"] == 1


def test_missing_resource(db, config):
    assessment, _, _, _ = assess(db, config, [])
    assert assessment.overall_status == "DRIFTED"
    assert "MISSING" in statuses(assessment)


def test_unexpected_resource(db, config):
    assessment, _, _, _ = assess(db, config, [actual_vm(), {**actual_vm(), "id": "/subscriptions/sub-a/resourceGroups/rg-main/providers/Microsoft.Compute/virtualMachines/temp", "resource_key": "temp", "name": "temp"}])
    assert assessment.summary["unexpected"] == 1


def test_modified_resource_type(db, config):
    assessment, _, _, _ = assess(db, config, [{**actual_vm(), "type": "microsoft.web/sites"}])
    assert any(item.property_path == "resource_type" and item.status == "MODIFIED" for item in assessment.findings)


def test_location_drift(db, config):
    assessment, _, _, _ = assess(db, config, [{**actual_vm(), "location": "westus"}])
    assert any(item.category == "LOCATION_DRIFT" for item in assessment.findings)


def test_sku_drift(db, config):
    assessment, _, _, _ = assess(db, config, [{**actual_vm(), "sku": {"name": "Standard_B2s"}}])
    assert any(item.category == "SKU_DRIFT" for item in assessment.findings)


@pytest.mark.parametrize("actual_tags,code", [({}, "MISSING_TAG"), ({"env": "dev"}, "TAG_VALUE_CHANGED"), ({"env": "prod", "owner": "ops"}, "UNEXPECTED_TAG")])
def test_tag_drift(db, config, actual_tags, code):
    assessment, _, _, _ = assess(db, config, [{**actual_vm(), "tags": actual_tags}])
    assert any(item.evidence.get("difference_code") == code for item in assessment.findings)


@pytest.mark.parametrize("path,category", [
    ("configuration.mode", "CONFIGURATION_DRIFT"),
    ("network.private", "NETWORK_DRIFT"),
    ("security.encryption", "SECURITY_DRIFT"),
    ("monitoring.enabled", "MONITORING_DRIFT"),
    ("backup.enabled", "BACKUP_DRIFT"),
])
def test_catalog_aware_property_drift(db, config, path, category):
    root, leaf = path.split(".")
    architecture, version, _, _ = create_desired(db, properties={root: {leaf: True}})
    add_catalog(db, [{"path": path, "category": category, "severity": "WARNING"}])
    snapshot = create_snapshot(db, [{**actual_vm(), "properties": {root: {leaf: False}}}])
    assessment = ConformanceEngine.assess(db, architecture.id, version.id, snapshot.id, config=config)
    assert any(item.category == category and item.status == "MODIFIED" for item in assessment.findings)


def test_unknown_azure_property(db, config):
    architecture, version, _, _ = create_desired(db, properties={"security": {"encryption": True}})
    add_catalog(db, [{"path": "security.encryption", "category": "SECURITY_DRIFT"}])
    snapshot = create_snapshot(db, [actual_vm(properties={})])
    assessment = ConformanceEngine.assess(db, architecture.id, version.id, snapshot.id, config=config)
    assert assessment.overall_status == "UNKNOWN"
    assert "UNKNOWN" in statuses(assessment)


def test_unknown_resource_correlation(db, config):
    duplicate = {**actual_vm()}
    duplicate.pop("resource_key")
    second = {**duplicate, "id": duplicate["id"] + "-two"}
    architecture, version, _, _ = create_desired(db)
    add_catalog(db)
    snapshot = create_snapshot(db, [duplicate, second])
    assessment = ConformanceEngine.assess(db, architecture.id, version.id, snapshot.id, config=config)
    assert assessment.overall_status == "UNKNOWN"
    assert assessment.summary["unexpected"] == 0
    assert any(item.status == "UNKNOWN" and "ambiguous" in item.explanation for item in assessment.findings)


def test_secret_property_compares_presence_only(db, config):
    architecture, version, _, _ = create_desired(db, properties={"security": {"client_secret": "desired-secret"}})
    add_catalog(db, [{"path": "security.client_secret", "category": "SECURITY_DRIFT"}])
    snapshot = create_snapshot(db, [actual_vm(properties={"security": {"client_secret": "different-secret"}})])
    assessment = ConformanceEngine.assess(db, architecture.id, version.id, snapshot.id, config=config)
    assert assessment.overall_status == "CONFORMANT"
    assert "desired-secret" not in str(assessment.findings)
    assert "different-secret" not in str(assessment.findings)


def test_secret_never_appears_in_unknown_finding(db, config):
    architecture, version, _, _ = create_desired(db, properties={"password": "never-return"})
    add_catalog(db, [{"path": "password", "category": "SECURITY_DRIFT"}])
    snapshot = create_snapshot(db, [actual_vm(properties={})])
    assessment = ConformanceEngine.assess(db, architecture.id, version.id, snapshot.id, config=config)
    assert "never-return" not in str(assessment.findings)
    assert any(item.desired_value_safe == "SECRET_VALUE_REDACTED" for item in assessment.findings)


def test_hierarchy_conformant_via_resource_group(db, config):
    architecture, version, _, resource = create_desired(db, parent=True)
    add_catalog(db)
    actual_rg = {"id": "/subscriptions/sub-a/resourceGroups/rg-main", "resource_key": "rg-main", "name": "rg-main", "type": RG, "location": "eastus", "tags": {}, "properties": {}}
    snapshot = create_snapshot(db, [actual_rg, {**actual_vm(), "resourceGroup": "rg-main"}])
    assessment = ConformanceEngine.assess(db, architecture.id, version.id, snapshot.id, config=config)
    assert not any(item.category == "HIERARCHY_DRIFT" for item in assessment.findings if item.resource_key == resource.resource_key)


def test_hierarchy_drift(db, config):
    architecture, version, _, _ = create_desired(db, parent=True)
    add_catalog(db)
    snapshot = create_snapshot(db, [{**actual_vm(), "resourceGroup": "wrong-rg"}])
    assessment = ConformanceEngine.assess(db, architecture.id, version.id, snapshot.id, config=config)
    assert any(item.category == "HIERARCHY_DRIFT" and item.status == "MODIFIED" for item in assessment.findings)


def create_edge_fixture(db, config, edge_kind):
    architecture, version, _, resource = create_desired(db)
    target = Resource(architecture_version_id=version.id, resource_key="nic", resource_type="microsoft.network/networkinterfaces", name="nic", location="eastus", properties={}, tags={})
    db.add(target)
    db.flush()
    if edge_kind == "relationship":
        db.add(Relationship(architecture_version_id=version.id, source_resource_id=resource.id, target_resource_id=target.id, relationship_type="uses"))
    else:
        db.add(Dependency(architecture_version_id=version.id, resource_id=resource.id, depends_on_resource_id=target.id, dependency_type="requires", required=True))
    db.commit()
    add_catalog(db)
    actual_target = {"id": "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Network/networkInterfaces/nic", "resource_key": "nic", "name": "nic", "type": target.resource_type, "location": "eastus", "tags": {}, "properties": {}}
    snapshot = create_snapshot(db, [actual_vm(**{f"{edge_kind}s": []}), actual_target])
    return ConformanceEngine.assess(db, architecture.id, version.id, snapshot.id, config=config)


def test_relationship_drift(db, config):
    assert any(item.category == "RELATIONSHIP_DRIFT" for item in create_edge_fixture(db, config, "relationship").findings)


def test_dependency_drift(db, config):
    assert any(item.category == "DEPENDENCY_DRIFT" for item in create_edge_fixture(db, config, "dependency").findings)


def test_unexpected_relationship_drift(db, config):
    assessment, _, _, _ = assess(db, config, [actual_vm(relationships=[{"target_resource_key": "other", "type": "uses"}])])
    assert any(item.category == "RELATIONSHIP_DRIFT" and "Unexpected" in item.explanation for item in assessment.findings)


def test_unexpected_dependency_drift(db, config):
    assessment, _, _, _ = assess(db, config, [actual_vm(dependencies=[{"target_resource_key": "other", "type": "requires"}])])
    assert any(item.category == "DEPENDENCY_DRIFT" and "Unexpected" in item.explanation for item in assessment.findings)


def test_relationship_unknown_without_evidence(db, config):
    architecture, version, _, resource = create_desired(db)
    target = Resource(architecture_version_id=version.id, resource_key="nic", resource_type="microsoft.network/networkinterfaces", name="nic", location="eastus", properties={}, tags={})
    db.add(target); db.flush(); db.add(Relationship(architecture_version_id=version.id, source_resource_id=resource.id, target_resource_id=target.id, relationship_type="uses")); db.commit(); add_catalog(db)
    snapshot = create_snapshot(db, [actual_vm(), {"id": "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Network/networkInterfaces/nic", "resource_key": "nic", "name": "nic", "type": target.resource_type, "location": "eastus", "tags": {}, "properties": {}}])
    assessment = ConformanceEngine.assess(db, architecture.id, version.id, snapshot.id, config=config)
    assert any(item.category == "RELATIONSHIP_DRIFT" and item.status == "UNKNOWN" for item in assessment.findings)


def test_empty_architecture_is_conformant_when_azure_empty(db, config):
    architecture = Architecture(name="Empty", provider="azure"); db.add(architecture); db.flush()
    version = ArchitectureVersion(architecture_id=architecture.id, version_number="1", version_sequence=1, status="DRAFT"); db.add(version); db.commit()
    snapshot = create_snapshot(db, [])
    assessment = ConformanceEngine.assess(db, architecture.id, version.id, snapshot.id, config=config)
    assert assessment.overall_status == "CONFORMANT"


@pytest.mark.parametrize("resource_type,names", [(RG, ["rg-a", "rg-b"]), ("microsoft.network/virtualnetworks", ["vnet-a", "vnet-b"]), ("microsoft.network/virtualnetworks/subnets", ["subnet-a", "subnet-b"])])
def test_multiple_resources_correlate_independently(db, config, resource_type, names):
    architecture = Architecture(name="Multiple", provider="azure"); db.add(architecture); db.flush()
    version = ArchitectureVersion(architecture_id=architecture.id, version_number="1", version_sequence=1, status="DRAFT"); db.add(version); db.flush()
    actual = []
    for name in names:
        db.add(Resource(architecture_version_id=version.id, resource_key=name, resource_type=resource_type, name=name, location="eastus", properties={}, tags={}))
        actual.append({"id": f"/subscriptions/sub-a/resourceGroups/rg/providers/{resource_type}/{name}", "resource_key": name, "name": name, "type": resource_type, "location": "eastus", "tags": {}, "properties": {}})
    db.commit()
    snapshot = create_snapshot(db, actual)
    assessment = ConformanceEngine.assess(db, architecture.id, version.id, snapshot.id, config=config)
    assert assessment.summary["conformant"] == 2


def test_same_desired_and_actual_produces_same_comparison_identity(db, config):
    first, architecture, version, _ = assess(db, config, [actual_vm()])
    second_snapshot = create_snapshot(db, [actual_vm()], sequence=2, snapshot_hash=first.azure_snapshot_hash)
    second = ConformanceEngine.assess(db, architecture.id, version.id, second_snapshot.id, config=config)
    assert first.comparison_hash == second.comparison_hash
    assert first.id != second.id


def test_different_snapshot_produces_different_identity(db, config):
    first, architecture, version, _ = assess(db, config, [actual_vm()])
    second_snapshot = create_snapshot(db, [{**actual_vm(), "location": "westus"}], sequence=2)
    second = ConformanceEngine.assess(db, architecture.id, version.id, second_snapshot.id, config=config)
    assert first.comparison_hash != second.comparison_hash


def test_assessment_persistence_and_immutability(db, config):
    assessment, architecture, version, snapshot = assess(db, config, [actual_vm()])
    saved_hash = assessment.comparison_hash
    snapshot.resources = [{**actual_vm(), "location": "westus"}]
    db.commit(); db.refresh(assessment)
    assert assessment.comparison_hash == saved_hash
    assert assessment.azure_snapshot_hash != ConformanceEngine.stable_hash(snapshot.resources)


def test_audit_events_are_recorded(db, config):
    assessment, _, _, _ = assess(db, config, [])
    events = {item.event_type for item in assessment.events}
    assert {"CONFORMANCE_STARTED", "CONFORMANCE_COMPLETED", "DRIFT_DETECTED"}.issubset(events)


def test_failed_assessment_records_safe_audit(db, config, monkeypatch):
    architecture, version, _, _ = create_desired(db); add_catalog(db); snapshot = create_snapshot(db, [actual_vm()])
    monkeypatch.setattr(ConformanceEngine, "_compare", lambda *args: (_ for _ in ()).throw(RuntimeError("secret internal failure")))
    with pytest.raises(ConformanceError):
        ConformanceEngine.assess(db, architecture.id, version.id, snapshot.id, config=config)
    assessment = db.query(ConformanceAssessment).one()
    assert assessment.overall_status == "ERROR"
    assert "secret internal failure" not in str(assessment.summary)
    assert {item.event_type for item in db.query(ConformanceEvent).all()} == {"CONFORMANCE_STARTED", "CONFORMANCE_FAILED"}


def test_historical_new_resolved_and_persistent_drift(db, config):
    first, architecture, version, _ = assess(db, config, [])
    second_snapshot = create_snapshot(db, [{**actual_vm(), "location": "westus"}], sequence=2)
    second = ConformanceEngine.assess(db, architecture.id, version.id, second_snapshot.id, config=config)
    comparison = ConformanceEngine.compare_assessments(db, architecture.id, version.id, first.id, second.id)
    assert comparison["new_drift"]
    assert comparison["resolved_drift"]


def test_persistent_drift(db, config):
    first, architecture, version, _ = assess(db, config, [{**actual_vm(), "location": "westus"}])
    second_snapshot = create_snapshot(db, [{**actual_vm(), "location": "westus"}], sequence=2)
    second = ConformanceEngine.assess(db, architecture.id, version.id, second_snapshot.id, config=config)
    assert ConformanceEngine.compare_assessments(db, architecture.id, version.id, first.id, second.id)["persistent_drift"]


def test_azure_snapshot_unavailable(db, config):
    architecture, version, _, _ = create_desired(db)
    with pytest.raises(ConformanceError, match="snapshot"):
        ConformanceEngine.assess(db, architecture.id, version.id, uuid4(), config=config)


def test_cross_subscription_isolation(db, config):
    architecture, version, _, _ = create_desired(db); add_catalog(db)
    snapshot = create_snapshot(db, [actual_vm()], subscription="sub-b")
    with pytest.raises(ConformanceError) as caught:
        ConformanceEngine.assess(db, architecture.id, version.id, snapshot.id, config=config)
    assert caught.value.code == "AZURE_SNAPSHOT_NOT_FOUND"


def test_wrong_version_rejected(db, config):
    architecture, _, _, _ = create_desired(db)
    snapshot = create_snapshot(db, [])
    with pytest.raises(ConformanceError) as caught:
        ConformanceEngine.assess(db, architecture.id, uuid4(), snapshot.id, config=config)
    assert caught.value.code == "ARCHITECTURE_VERSION_NOT_FOUND"


def test_cross_architecture_comparison_rejected(db, config):
    first, architecture, version, _ = assess(db, config, [actual_vm()])
    other_architecture, other_version, _, _ = create_desired(db, name="other")
    add_catalog(db)
    other_snapshot = create_snapshot(db, [], sequence=2)
    other = ConformanceEngine.assess(db, other_architecture.id, other_version.id, other_snapshot.id, config=config)
    with pytest.raises(ConformanceError):
        ConformanceEngine.compare_assessments(db, architecture.id, version.id, first.id, other.id)


def test_m6_m7_metadata_correlation(db, config):
    architecture, version, _, _ = create_desired(db); add_catalog(db)
    snapshot = create_snapshot(db, [actual_vm()])
    execution = TerraformExecution(architecture_id=architecture.id, architecture_version_id=version.id, state="SUCCEEDED", generation_hash="g" * 64, plan_artifact_hash="p" * 64, compliance_frameworks=[], command_results={})
    db.add(execution); db.commit()
    assessment = ConformanceEngine.assess(db, architecture.id, version.id, snapshot.id, execution.id, config)
    assert assessment.terraform_generation_hash == "g" * 64
    assert assessment.terraform_plan_hash == "p" * 64
    assert assessment.terraform_execution_state == "SUCCEEDED"


def test_foreign_execution_rejected(db, config):
    architecture, version, _, _ = create_desired(db); add_catalog(db); snapshot = create_snapshot(db, [actual_vm()])
    other = Architecture(name="Other", provider="azure"); db.add(other); db.flush()
    other_version = ArchitectureVersion(architecture_id=other.id, version_number="1", version_sequence=1, status="DRAFT"); db.add(other_version); db.flush()
    execution = TerraformExecution(architecture_id=other.id, architecture_version_id=other_version.id, state="SUCCEEDED", compliance_frameworks=[], command_results={}); db.add(execution); db.commit()
    with pytest.raises(ConformanceError):
        ConformanceEngine.assess(db, architecture.id, version.id, snapshot.id, execution.id, config)


def test_concurrency_lock_is_stable_per_comparison():
    first = ConformanceEngine._scope_lock("a:v:s")
    assert first is ConformanceEngine._scope_lock("a:v:s")
    assert first is not ConformanceEngine._scope_lock("a:v:other")


def test_no_azure_or_terraform_operations_exposed():
    public = {name for name in dir(ConformanceEngine) if not name.startswith("_")}
    assert not public.intersection({"apply", "plan", "deploy", "refresh", "create_resource", "update_resource", "delete_resource"})
