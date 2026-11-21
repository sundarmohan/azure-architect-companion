"""Tests for M8 deterministic architecture snapshot versioning."""

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    ArchitectureVersion,
    ArchitectureVersionEvent,
    Dependency,
    Relationship,
    Resource,
    TerraformExecution,
)
from app.schemas import (
    ArchitectureCreate,
    ArchitectureVersionCreate,
    DependencyCreate,
    RelationshipCreate,
    ResourceCreate,
)
from app.services import (
    ArchitectureService,
    ArchitectureVersionService,
    ArchitectureVersioningError,
    ArchitectureVersioningService,
    DependencyService,
    RelationshipService,
    ResourceService,
)


def create_v1(db, name="Versioned Architecture"):
    architecture = ArchitectureService.create(
        db, ArchitectureCreate(name=name, provider="azure")
    )
    version = ArchitectureVersionService.create(
        db,
        architecture.id,
        ArchitectureVersionCreate(
            version_number="1.0",
            status="draft",
            created_by="architect@example.test",
            change_description="Initial architecture",
        ),
    )
    resource_group = ResourceService.create(
        db,
        version.id,
        ResourceCreate(
            resource_key="core-rg",
            resource_type="microsoft.resources/resourcegroups",
            name="core-rg",
            location="eastus",
            tags={"environment": "test"},
        ),
    )
    virtual_machine = ResourceService.create(
        db,
        version.id,
        ResourceCreate(
            resource_key="web-vm",
            resource_type="microsoft.compute/virtualmachines",
            name="web-vm",
            location="eastus",
            sku={"name": "Standard_B1s"},
            properties={"zone": "1"},
            parent_resource_id=resource_group.id,
        ),
    )
    storage = ResourceService.create(
        db,
        version.id,
        ResourceCreate(
            resource_key="data-storage",
            resource_type="microsoft.storage/storageaccounts",
            name="datastore",
            location="eastus",
        ),
    )
    RelationshipService.create(
        db,
        version.id,
        RelationshipCreate(
            source_resource_id=virtual_machine.id,
            target_resource_id=storage.id,
            relationship_type="uses",
            metadata={"protocol": "https"},
        ),
    )
    DependencyService.create(
        db,
        version.id,
        DependencyCreate(
            resource_id=virtual_machine.id,
            depends_on_resource_id=resource_group.id,
            dependency_type="requires",
            reason="VM placement",
        ),
    )
    ArchitectureVersioningService.activate(db, architecture.id, version.id)
    return architecture, version


def clone(db, architecture, source, description="Version change"):
    return ArchitectureVersioningService.create_version(
        db,
        architecture.id,
        source.id,
        description,
        "architect@example.test",
    )


def resource(db, version, key):
    return db.query(Resource).filter(
        Resource.architecture_version_id == version.id,
        Resource.resource_key == key,
    ).one()


def compare(db, architecture, before, after):
    return ArchitectureVersioningService.compare_versions(
        db, architecture.id, before.id, after.id
    )


class TestSnapshotCreation:
    def test_create_v1(self, db):
        architecture, version = create_v1(db)
        assert version.architecture_id == architecture.id
        assert version.version_sequence == 1
        assert version.status == "ACTIVE"

    def test_create_v2_from_v1(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        assert v2.version_sequence == 2
        assert v2.parent_version_id == v1.id
        assert v2.status == "DRAFT"

    def test_v2_is_complete_snapshot(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        assert db.query(Resource).filter(Resource.architecture_version_id == v2.id).count() == 3
        assert db.query(Relationship).filter(Relationship.architecture_version_id == v2.id).count() == 1
        assert db.query(Dependency).filter(Dependency.architecture_version_id == v2.id).count() == 1

    def test_v1_remains_unchanged_when_v2_changes(self, db):
        architecture, v1 = create_v1(db)
        v1_hash = ArchitectureVersioningService.snapshot_hash(db, architecture.id, v1.id)
        v2 = clone(db, architecture, v1)
        resource(db, v2, "web-vm").sku = {"name": "Standard_D2s_v5"}
        db.commit()
        assert ArchitectureVersioningService.snapshot_hash(db, architecture.id, v1.id) == v1_hash
        assert resource(db, v1, "web-vm").sku == {"name": "Standard_B1s"}

    def test_v3_can_be_created_after_v2(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        v3 = clone(db, architecture, v2)
        assert (v2.version_sequence, v3.version_sequence) == (2, 3)
        assert v3.parent_version_id == v2.id

    def test_activation_supersedes_previous_active_version(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        resource(db, v2, "web-vm").location = "westus2"
        db.commit()

        ArchitectureVersioningService.activate(db, architecture.id, v2.id)

        db.refresh(v1)
        assert v1.status == "SUPERSEDED"
        assert v2.status == "ACTIVE"


class TestResourceComparison:
    def test_resource_added(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        ResourceService.create(db, v2.id, ResourceCreate(resource_key="logs", resource_type="microsoft.storage/storageaccounts", name="logs"))
        result = compare(db, architecture, v1, v2)
        assert any(item["resource_key"] == "logs" and item["change_type"] == "RESOURCE_ADDED" for item in result["resource_changes"])

    def test_resource_removed(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        db.delete(resource(db, v2, "data-storage"))
        db.query(Relationship).filter(Relationship.architecture_version_id == v2.id).delete()
        db.commit()
        result = compare(db, architecture, v1, v2)
        assert any(item["resource_key"] == "data-storage" and item["change_type"] == "RESOURCE_REMOVED" for item in result["resource_changes"])

    def test_resource_modified(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        resource(db, v2, "web-vm").name = "renamed-vm"
        db.commit()
        item = next(item for item in compare(db, architecture, v1, v2)["resource_changes"] if item["resource_key"] == "web-vm")
        assert item["change_type"] == "RESOURCE_MODIFIED"

    @pytest.mark.parametrize(
        ("field", "value", "category"),
        [
            ("properties", {"zone": "2"}, "PROPERTY_CHANGED"),
            ("sku", {"name": "Standard_D2s_v5"}, "SKU_CHANGED"),
            ("tags", {"environment": "production"}, "TAG_CHANGED"),
            ("location", "westus2", "LOCATION_CHANGED"),
            ("resource_type", "microsoft.compute/virtualmachinescalesets", "RESOURCE_TYPE_CHANGED"),
        ],
    )
    def test_resource_field_changes(self, db, field, value, category):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        setattr(resource(db, v2, "web-vm"), field, value)
        db.commit()
        item = next(item for item in compare(db, architecture, v1, v2)["resource_changes"] if item["resource_key"] == "web-vm")
        assert any(change["category"] == category for change in item["changes"])

    def test_hierarchy_changed(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        resource(db, v2, "web-vm").parent_resource_id = None
        db.commit()
        result = compare(db, architecture, v1, v2)
        assert result["hierarchy_changes"][0]["resource_key"] == "web-vm"


class TestLinkComparison:
    def test_duplicate_semantic_relationships_are_preserved(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        original = db.query(Relationship).filter(
            Relationship.architecture_version_id == v2.id
        ).one()
        db.add(
            Relationship(
                architecture_version_id=v2.id,
                source_resource_id=original.source_resource_id,
                target_resource_id=original.target_resource_id,
                relationship_type=original.relationship_type,
                relationship_metadata={"protocol": "private-link"},
            )
        )
        db.commit()

        result = compare(db, architecture, v1, v2)

        assert len(result["relationship_changes"]) == 2
        assert any(
            item["change_type"] == "RELATIONSHIP_ADDED"
            for item in result["relationship_changes"]
        )

    def test_relationship_added(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        RelationshipService.create(db, v2.id, RelationshipCreate(source_resource_id=resource(db, v2, "core-rg").id, target_resource_id=resource(db, v2, "web-vm").id, relationship_type="contains"))
        assert any(item["change_type"] == "RELATIONSHIP_ADDED" for item in compare(db, architecture, v1, v2)["relationship_changes"])

    def test_relationship_removed(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        db.query(Relationship).filter(Relationship.architecture_version_id == v2.id).delete()
        db.commit()
        assert any(item["change_type"] == "RELATIONSHIP_REMOVED" for item in compare(db, architecture, v1, v2)["relationship_changes"])

    def test_relationship_modified(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        link = db.query(Relationship).filter(Relationship.architecture_version_id == v2.id).one()
        link.relationship_metadata = {"protocol": "private-link"}
        db.commit()
        assert any(item["change_type"] == "RELATIONSHIP_MODIFIED" for item in compare(db, architecture, v1, v2)["relationship_changes"])

    def test_dependency_added(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        DependencyService.create(db, v2.id, DependencyCreate(resource_id=resource(db, v2, "data-storage").id, depends_on_resource_id=resource(db, v2, "core-rg").id, dependency_type="requires"))
        assert any(item["change_type"] == "DEPENDENCY_ADDED" for item in compare(db, architecture, v1, v2)["dependency_changes"])

    def test_dependency_removed(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        db.query(Dependency).filter(Dependency.architecture_version_id == v2.id).delete()
        db.commit()
        assert any(item["change_type"] == "DEPENDENCY_REMOVED" for item in compare(db, architecture, v1, v2)["dependency_changes"])

    def test_dependency_modified(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        item = db.query(Dependency).filter(Dependency.architecture_version_id == v2.id).one()
        item.required = False
        db.commit()
        assert any(change["change_type"] == "DEPENDENCY_MODIFIED" for change in compare(db, architecture, v1, v2)["dependency_changes"])


class TestHashingAndLifecycle:
    def test_no_change_detection(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        with pytest.raises(ArchitectureVersioningError) as error:
            ArchitectureVersioningService.activate(db, architecture.id, v2.id)
        assert error.value.code == "NO_CHANGES"

    def test_snapshot_hash_is_stable(self, db):
        architecture, v1 = create_v1(db)
        assert ArchitectureVersioningService.snapshot_hash(db, architecture.id, v1.id) == ArchitectureVersioningService.snapshot_hash(db, architecture.id, v1.id)

    def test_snapshot_hash_changes_with_content(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        resource(db, v2, "web-vm").location = "westus2"
        db.commit()
        assert ArchitectureVersioningService.snapshot_hash(db, architecture.id, v1.id) != ArchitectureVersioningService.snapshot_hash(db, architecture.id, v2.id)

    def test_database_uuids_do_not_affect_semantic_hash(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        assert resource(db, v1, "web-vm").id != resource(db, v2, "web-vm").id
        assert ArchitectureVersioningService.snapshot_hash(db, architecture.id, v1.id) == ArchitectureVersioningService.snapshot_hash(db, architecture.id, v2.id)

    def test_finalized_version_cannot_be_modified(self, db):
        architecture, v1 = create_v1(db)
        with pytest.raises(ArchitectureVersioningError) as error:
            ResourceService.create(db, v1.id, ResourceCreate(resource_key="blocked", resource_type="microsoft.storage/storageaccounts", name="blocked"))
        assert error.value.code == "VERSION_IMMUTABLE"

    def test_version_comparison_is_deterministic(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        resource(db, v2, "web-vm").location = "westus2"
        db.commit()
        first = compare(db, architecture, v1, v2)
        second = compare(db, architecture, v1, v2)
        assert first == second

    def test_cross_architecture_comparison_is_rejected(self, db):
        architecture, v1 = create_v1(db)
        other, other_v1 = create_v1(db, "Other")
        with pytest.raises(ArchitectureVersioningError) as error:
            ArchitectureVersioningService.compare_versions(db, architecture.id, v1.id, other_v1.id)
        assert error.value.code == "VERSION_NOT_FOUND"

    def test_invalid_source_version_is_rejected(self, db):
        architecture, _ = create_v1(db)
        with pytest.raises(ArchitectureVersioningError) as error:
            ArchitectureVersioningService.create_version(db, architecture.id, uuid4())
        assert error.value.code == "VERSION_NOT_FOUND"

    def test_version_number_uniqueness_protects_concurrent_allocation(self, db):
        architecture, _ = create_v1(db)
        db.add(ArchitectureVersion(architecture_id=architecture.id, version_number="other", version_sequence=1, status="DRAFT"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


class TestRevertIntegrationAndSecurity:
    def test_revert_v3_to_v1_creates_v4(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        resource(db, v2, "web-vm").location = "westus2"
        db.commit()
        ArchitectureVersioningService.activate(db, architecture.id, v2.id)
        v3 = clone(db, architecture, v2)
        resource(db, v3, "web-vm").sku = {"name": "Standard_D2s_v5"}
        db.commit()
        ArchitectureVersioningService.activate(db, architecture.id, v3.id)
        v4 = ArchitectureVersioningService.revert(db, architecture.id, v1.id, created_by="architect")
        assert v4.version_sequence == 4
        assert v4.parent_version_id == v3.id
        assert ArchitectureVersioningService.snapshot_hash(db, architecture.id, v4.id) == ArchitectureVersioningService.snapshot_hash(db, architecture.id, v1.id)

    def test_v1_remains_unchanged_after_revert(self, db):
        architecture, v1 = create_v1(db)
        original = ArchitectureVersioningService.snapshot_hash(db, architecture.id, v1.id)
        clone(db, architecture, v1)
        ArchitectureVersioningService.revert(db, architecture.id, v1.id)
        assert ArchitectureVersioningService.snapshot_hash(db, architecture.id, v1.id) == original

    def test_creation_failure_rolls_back_complete_candidate(self, db, monkeypatch):
        architecture, v1 = create_v1(db)
        original_audit = ArchitectureVersioningService._audit

        def fail_audit(*args, **kwargs):
            raise RuntimeError("forced clone failure")

        monkeypatch.setattr(ArchitectureVersioningService, "_audit", fail_audit)
        with pytest.raises(RuntimeError):
            clone(db, architecture, v1)
        monkeypatch.setattr(ArchitectureVersioningService, "_audit", original_audit)
        assert db.query(ArchitectureVersion).filter(ArchitectureVersion.architecture_id == architecture.id).count() == 1
        assert db.query(ArchitectureVersionEvent).filter(ArchitectureVersionEvent.event_type == "VERSION_CREATION_FAILED").count() == 1

    def test_m6_semantic_identity_is_preserved(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        assert sorted(item.resource_key for item in v1.resources) == sorted(item.resource_key for item in v2.resources)
        assert {item.id for item in v1.resources}.isdisjoint({item.id for item in v2.resources})

    def test_m7_metadata_remains_version_specific(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        execution = TerraformExecution(architecture_id=architecture.id, architecture_version_id=v2.id, state="GENERATED", generator_version="1.0.0", generation_hash="a" * 64)
        db.add(execution)
        db.commit()
        assert execution.architecture_version_id == v2.id
        assert execution.architecture_version_id != v1.id

    def test_secrets_are_redacted_from_diff_but_affect_hash(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        resource(db, v2, "web-vm").properties = {"administrator_password": "new-secret"}
        db.commit()
        result = compare(db, architecture, v1, v2)
        assert "new-secret" not in str(result)
        assert "[REDACTED]" in str(result)
        assert result["from_snapshot_hash"] != result["to_snapshot_hash"]

    def test_audit_events_are_generated(self, db):
        architecture, v1 = create_v1(db)
        v2 = clone(db, architecture, v1)
        compare(db, architecture, v1, v2)
        events = ArchitectureVersioningService.list_events(db, architecture.id, v2.id)
        assert {item.event_type for item in events} >= {"VERSION_CREATED", "VERSION_COMPARED"}

    def test_api_error_behavior(self, client, db):
        architecture, _ = create_v1(db)
        response = client.post(
            f"/architectures/{architecture.id}/versions",
            json={"source_version_id": str(uuid4()), "change_description": "invalid"},
        )
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "VERSION_NOT_FOUND"
