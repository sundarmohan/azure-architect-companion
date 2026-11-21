"""Deterministic, immutable architecture snapshot versioning."""

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..enums import ArchitectureVersionEventType, ArchitectureVersionStatus
from ..models import (
    Architecture,
    ArchitectureVersion,
    ArchitectureVersionEvent,
    Dependency,
    Relationship,
    Resource,
)
from .terraform_generator import TerraformGenerator


class ArchitectureVersioningError(ValueError):
    """Controlled architecture version lifecycle error."""

    def __init__(self, code: str, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


class ArchitectureVersioningService:
    """Own complete canonical snapshots and deterministic version comparisons."""

    FINALIZED_STATUSES = {
        ArchitectureVersionStatus.ACTIVE.value,
        ArchitectureVersionStatus.SUPERSEDED.value,
        ArchitectureVersionStatus.ARCHIVED.value,
        "validated",
        "deployed",
    }
    REDACTED = "[REDACTED]"

    @classmethod
    def create_version(
        cls,
        db: Session,
        architecture_id: UUID,
        source_version_id: UUID,
        change_description: Optional[str] = None,
        created_by: Optional[str] = None,
        version_metadata: Optional[dict] = None,
    ) -> ArchitectureVersion:
        """Create one complete editable snapshot from an existing version."""
        cls.assert_safe_metadata(version_metadata)
        cls.assert_safe_description(change_description)
        return cls._copy_snapshot(
            db=db,
            architecture_id=architecture_id,
            content_version_id=source_version_id,
            parent_version_id=source_version_id,
            change_description=change_description,
            created_by=created_by,
            version_metadata=version_metadata,
            event_type=ArchitectureVersionEventType.VERSION_CREATED.value,
        )

    @classmethod
    def revert(
        cls,
        db: Session,
        architecture_id: UUID,
        target_version_id: UUID,
        change_description: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> ArchitectureVersion:
        """Create a new draft whose content matches an older snapshot."""
        target = cls._get_version(db, architecture_id, target_version_id)
        cls.assert_safe_description(change_description)
        current = (
            db.query(ArchitectureVersion)
            .filter(
                ArchitectureVersion.architecture_id == architecture_id,
                ArchitectureVersion.status == ArchitectureVersionStatus.ACTIVE.value,
            )
            .first()
        )
        if current is None:
            current = (
                db.query(ArchitectureVersion)
                .filter(ArchitectureVersion.architecture_id == architecture_id)
                .order_by(
                    ArchitectureVersion.version_sequence.desc(),
                    ArchitectureVersion.created_at.desc(),
                )
                .first()
            )
        return cls._copy_snapshot(
            db=db,
            architecture_id=architecture_id,
            content_version_id=target.id,
            parent_version_id=current.id if current else target.id,
            change_description=change_description or f"Revert to {target.version_number}",
            created_by=created_by,
            version_metadata={"reverted_from_version_id": str(target.id)},
            event_type=ArchitectureVersionEventType.VERSION_REVERTED.value,
        )

    @classmethod
    def activate(
        cls,
        db: Session,
        architecture_id: UUID,
        version_id: UUID,
        actor: Optional[str] = None,
    ) -> ArchitectureVersion:
        """Finalize a draft and make it the architecture's sole active version."""
        cls._lock_architecture(db, architecture_id)
        version = cls._get_version(db, architecture_id, version_id)
        if version.status not in {ArchitectureVersionStatus.DRAFT.value, "draft"}:
            raise ArchitectureVersioningError(
                "VERSION_NOT_DRAFT", "Only a draft architecture version can be activated"
            )
        snapshot_hash = cls.snapshot_hash(db, architecture_id, version_id)
        if version.parent_version_id:
            parent_hash = cls.snapshot_hash(
                db, architecture_id, version.parent_version_id
            )
            if snapshot_hash == parent_hash:
                raise ArchitectureVersioningError(
                    "NO_CHANGES",
                    "No semantic changes from the parent version",
                    {
                        "source_version_id": str(version.parent_version_id),
                        "candidate_version_id": str(version.id),
                        "snapshot_hash": snapshot_hash,
                    },
                )

        active_versions = (
            db.query(ArchitectureVersion)
            .filter(
                ArchitectureVersion.architecture_id == architecture_id,
                ArchitectureVersion.status == ArchitectureVersionStatus.ACTIVE.value,
                ArchitectureVersion.id != version_id,
            )
            .all()
        )
        for active in active_versions:
            active.status = ArchitectureVersionStatus.SUPERSEDED.value

        version.status = ArchitectureVersionStatus.ACTIVE.value
        version.snapshot_hash = snapshot_hash
        version.finalized_at = datetime.now(timezone.utc)
        cls._audit(
            db,
            version,
            ArchitectureVersionEventType.VERSION_ACTIVATED.value,
            actor,
            {"snapshot_hash": snapshot_hash},
        )
        try:
            db.commit()
        except IntegrityError as error:
            db.rollback()
            raise ArchitectureVersioningError(
                "VERSION_ACTIVATION_CONFLICT",
                "Another architecture version was activated concurrently",
            ) from error
        db.refresh(version)
        return version

    @classmethod
    def compare_versions(
        cls,
        db: Session,
        architecture_id: UUID,
        from_version_id: UUID,
        to_version_id: UUID,
        actor: Optional[str] = None,
    ) -> dict:
        """Return a deterministic, secret-redacted canonical architecture diff."""
        from_version = cls._get_version(db, architecture_id, from_version_id)
        to_version = cls._get_version(db, architecture_id, to_version_id)
        from_snapshot = cls._snapshot(db, from_version.id)
        to_snapshot = cls._snapshot(db, to_version.id)

        resource_changes = cls._compare_resources(
            from_snapshot["resources"], to_snapshot["resources"]
        )
        relationship_changes = cls._compare_records(
            from_snapshot["relationships"],
            to_snapshot["relationships"],
            "RELATIONSHIP",
        )
        dependency_changes = cls._compare_records(
            from_snapshot["dependencies"],
            to_snapshot["dependencies"],
            "DEPENDENCY",
        )
        hierarchy_changes = [
            change
            for change in resource_changes
            if any(item["category"] == "HIERARCHY_CHANGED" for item in change.get("changes", []))
        ]
        summary = cls._summary(
            resource_changes, relationship_changes, dependency_changes
        )
        result = {
            "architecture_id": architecture_id,
            "from_version_id": from_version.id,
            "to_version_id": to_version.id,
            "from_snapshot_hash": cls._hash_snapshot(from_snapshot),
            "to_snapshot_hash": cls._hash_snapshot(to_snapshot),
            "has_changes": summary["total_changes"] > 0,
            "resource_changes": resource_changes,
            "relationship_changes": relationship_changes,
            "dependency_changes": dependency_changes,
            "hierarchy_changes": hierarchy_changes,
            "summary": summary,
        }
        cls._audit(
            db,
            to_version,
            ArchitectureVersionEventType.VERSION_COMPARED.value,
            actor,
            {
                "from_version_id": str(from_version.id),
                "to_version_id": str(to_version.id),
                "total_changes": summary["total_changes"],
            },
        )
        db.commit()
        return result

    @classmethod
    def snapshot_hash(
        cls, db: Session, architecture_id: UUID, version_id: UUID
    ) -> str:
        cls._get_version(db, architecture_id, version_id)
        return cls._hash_snapshot(cls._snapshot(db, version_id))

    @classmethod
    def list_events(
        cls, db: Session, architecture_id: UUID, version_id: UUID
    ) -> List[ArchitectureVersionEvent]:
        cls._get_version(db, architecture_id, version_id)
        return (
            db.query(ArchitectureVersionEvent)
            .filter(
                ArchitectureVersionEvent.architecture_id == architecture_id,
                ArchitectureVersionEvent.architecture_version_id == version_id,
            )
            .order_by(
                ArchitectureVersionEvent.created_at,
                ArchitectureVersionEvent.id,
            )
            .all()
        )

    @classmethod
    def assert_editable(cls, version: ArchitectureVersion) -> None:
        if version.status in cls.FINALIZED_STATUSES or version.status.upper() in {
            item.value for item in ArchitectureVersionStatus if item != ArchitectureVersionStatus.DRAFT
        }:
            raise ArchitectureVersioningError(
                "VERSION_IMMUTABLE", "Finalized architecture versions cannot be modified"
            )

    @classmethod
    def assert_safe_metadata(cls, value: Any, key: str = "metadata") -> None:
        if TerraformGenerator._is_secret_key(key):
            raise ArchitectureVersioningError(
                "SECRET_METADATA_NOT_ALLOWED",
                "Secret-bearing values are not allowed in architecture version metadata",
            )
        if isinstance(value, dict):
            for item_key, item in value.items():
                cls.assert_safe_metadata(item, str(item_key))
        elif isinstance(value, list):
            for item in value:
                cls.assert_safe_metadata(item, key)

    @classmethod
    def assert_safe_description(cls, value: Optional[str]) -> None:
        if not value:
            return
        words = re.findall(r"[A-Za-z][A-Za-z0-9_-]*", value)
        if any(TerraformGenerator._is_secret_key(word) for word in words):
            raise ArchitectureVersioningError(
                "SECRET_DESCRIPTION_NOT_ALLOWED",
                "Secret-bearing labels are not allowed in architecture version descriptions",
            )

    @classmethod
    def _copy_snapshot(
        cls,
        db: Session,
        architecture_id: UUID,
        content_version_id: UUID,
        parent_version_id: UUID,
        change_description: Optional[str],
        created_by: Optional[str],
        version_metadata: Optional[dict],
        event_type: str,
    ) -> ArchitectureVersion:
        cls._lock_architecture(db, architecture_id)
        source = cls._get_version(db, architecture_id, content_version_id)
        source_id = source.id
        cls._get_version(db, architecture_id, parent_version_id)
        sequence = cls._next_sequence(db, architecture_id)
        version = ArchitectureVersion(
            architecture_id=architecture_id,
            version_number=str(sequence),
            version_sequence=sequence,
            status=ArchitectureVersionStatus.DRAFT.value,
            parent_version_id=parent_version_id,
            change_description=change_description,
            version_metadata=deepcopy(version_metadata),
            created_by=created_by,
        )
        try:
            db.add(version)
            db.flush()
            resources = (
                db.query(Resource)
                .filter(Resource.architecture_version_id == source.id)
                .order_by(Resource.resource_key)
                .all()
            )
            resource_map: Dict[UUID, Resource] = {}
            for resource in resources:
                clone = Resource(
                    architecture_version_id=version.id,
                    resource_key=resource.resource_key,
                    resource_type=resource.resource_type,
                    name=resource.name,
                    location=resource.location,
                    sku=deepcopy(resource.sku),
                    properties=deepcopy(resource.properties),
                    tags=deepcopy(resource.tags),
                )
                db.add(clone)
                resource_map[resource.id] = clone
            db.flush()
            for resource in resources:
                if resource.parent_resource_id:
                    resource_map[resource.id].parent_resource_id = resource_map[
                        resource.parent_resource_id
                    ].id

            relationships = (
                db.query(Relationship)
                .filter(Relationship.architecture_version_id == source.id)
                .all()
            )
            for relationship in relationships:
                db.add(
                    Relationship(
                        architecture_version_id=version.id,
                        source_resource_id=resource_map[relationship.source_resource_id].id,
                        target_resource_id=resource_map[relationship.target_resource_id].id,
                        relationship_type=relationship.relationship_type,
                        relationship_metadata=deepcopy(relationship.relationship_metadata),
                    )
                )

            dependencies = (
                db.query(Dependency)
                .filter(Dependency.architecture_version_id == source.id)
                .all()
            )
            for dependency in dependencies:
                db.add(
                    Dependency(
                        architecture_version_id=version.id,
                        resource_id=resource_map[dependency.resource_id].id,
                        depends_on_resource_id=resource_map[dependency.depends_on_resource_id].id,
                        dependency_type=dependency.dependency_type,
                        required=dependency.required,
                        reason=dependency.reason,
                    )
                )
            db.flush()
            cls._audit(
                db,
                version,
                event_type,
                created_by,
                {
                    "source_version_id": str(source.id),
                    "parent_version_id": str(parent_version_id),
                    "resource_count": len(resources),
                    "relationship_count": len(relationships),
                    "dependency_count": len(dependencies),
                },
            )
            db.commit()
        except Exception:
            db.rollback()
            db.add(
                ArchitectureVersionEvent(
                    architecture_id=architecture_id,
                    architecture_version_id=source_id,
                    event_type=ArchitectureVersionEventType.VERSION_CREATION_FAILED.value,
                    actor=created_by,
                    details={"code": "SNAPSHOT_CREATION_FAILED"},
                )
            )
            db.commit()
            raise
        db.refresh(version)
        return version

    @classmethod
    def _snapshot(cls, db: Session, version_id: UUID) -> dict:
        resources = (
            db.query(Resource)
            .filter(Resource.architecture_version_id == version_id)
            .order_by(Resource.resource_key)
            .all()
        )
        key_by_id = {resource.id: resource.resource_key for resource in resources}
        resource_records = {
            resource.resource_key: {
                "resource_key": resource.resource_key,
                "resource_type": resource.resource_type,
                "name": resource.name,
                "location": resource.location,
                "sku": resource.sku,
                "properties": resource.properties,
                "tags": resource.tags,
                "parent_resource_key": key_by_id.get(resource.parent_resource_id),
            }
            for resource in resources
        }
        relationships = (
            db.query(Relationship)
            .filter(Relationship.architecture_version_id == version_id)
            .all()
        )
        relationship_items = [
            {
                "source_resource_key": key_by_id[item.source_resource_id],
                "target_resource_key": key_by_id[item.target_resource_id],
                "relationship_type": item.relationship_type,
                "metadata": item.relationship_metadata,
            }
            for item in relationships
        ]
        relationship_records = cls._indexed_records(
            relationship_items,
            ("source_resource_key", "target_resource_key", "relationship_type"),
        )
        dependencies = (
            db.query(Dependency)
            .filter(Dependency.architecture_version_id == version_id)
            .all()
        )
        dependency_items = [
            {
                "resource_key": key_by_id[item.resource_id],
                "depends_on_resource_key": key_by_id[item.depends_on_resource_id],
                "dependency_type": item.dependency_type,
                "required": item.required,
                "reason": item.reason,
            }
            for item in dependencies
        ]
        dependency_records = cls._indexed_records(
            dependency_items,
            ("resource_key", "depends_on_resource_key", "dependency_type"),
        )
        return {
            "resources": resource_records,
            "relationships": relationship_records,
            "dependencies": dependency_records,
        }

    @classmethod
    def _compare_resources(cls, before: dict, after: dict) -> List[dict]:
        changes = []
        for key in sorted(set(before) | set(after)):
            if key not in before:
                changes.append({"resource_key": key, "change_type": "RESOURCE_ADDED", "changes": []})
                continue
            if key not in after:
                changes.append({"resource_key": key, "change_type": "RESOURCE_REMOVED", "changes": []})
                continue
            field_changes = []
            categories = {
                "properties": "PROPERTY_CHANGED",
                "tags": "TAG_CHANGED",
                "sku": "SKU_CHANGED",
                "location": "LOCATION_CHANGED",
                "resource_type": "RESOURCE_TYPE_CHANGED",
                "parent_resource_key": "HIERARCHY_CHANGED",
            }
            for field in sorted(set(before[key]) | set(after[key])):
                if before[key].get(field) != after[key].get(field):
                    field_changes.append(
                        {
                            "category": categories.get(field, "PROPERTY_CHANGED"),
                            "field": field,
                            "from": cls._redact(before[key].get(field), field),
                            "to": cls._redact(after[key].get(field), field),
                        }
                    )
            changes.append(
                {
                    "resource_key": key,
                    "change_type": "RESOURCE_MODIFIED" if field_changes else "RESOURCE_UNCHANGED",
                    "changes": field_changes,
                }
            )
        return changes

    @classmethod
    def _compare_records(cls, before: dict, after: dict, prefix: str) -> List[dict]:
        changes = []
        for key in sorted(set(before) | set(after)):
            if key not in before:
                change_type = f"{prefix}_ADDED"
                field_changes = []
            elif key not in after:
                change_type = f"{prefix}_REMOVED"
                field_changes = []
            else:
                field_changes = [
                    {
                        "field": field,
                        "from": cls._redact(before[key].get(field), field),
                        "to": cls._redact(after[key].get(field), field),
                    }
                    for field in sorted(set(before[key]) | set(after[key]))
                    if before[key].get(field) != after[key].get(field)
                ]
                change_type = f"{prefix}_MODIFIED" if field_changes else f"{prefix}_UNCHANGED"
            changes.append({"semantic_key": key, "change_type": change_type, "changes": field_changes})
        return changes

    @staticmethod
    def _summary(resources: List[dict], relationships: List[dict], dependencies: List[dict]) -> dict:
        counts: Dict[str, int] = {}
        for item in resources + relationships + dependencies:
            change_type = item["change_type"]
            counts[change_type] = counts.get(change_type, 0) + 1
        total = sum(count for key, count in counts.items() if not key.endswith("_UNCHANGED"))
        return {
            "resources": {
                "added": sorted(item["resource_key"] for item in resources if item["change_type"] == "RESOURCE_ADDED"),
                "removed": sorted(item["resource_key"] for item in resources if item["change_type"] == "RESOURCE_REMOVED"),
                "modified": sorted(item["resource_key"] for item in resources if item["change_type"] == "RESOURCE_MODIFIED"),
                "unchanged": sorted(item["resource_key"] for item in resources if item["change_type"] == "RESOURCE_UNCHANGED"),
            },
            "relationships": {
                "added": counts.get("RELATIONSHIP_ADDED", 0),
                "removed": counts.get("RELATIONSHIP_REMOVED", 0),
                "modified": counts.get("RELATIONSHIP_MODIFIED", 0),
            },
            "dependencies": {
                "added": counts.get("DEPENDENCY_ADDED", 0),
                "removed": counts.get("DEPENDENCY_REMOVED", 0),
                "modified": counts.get("DEPENDENCY_MODIFIED", 0),
            },
            "counts": dict(sorted(counts.items())),
            "total_changes": total,
        }

    @classmethod
    def _redact(cls, value: Any, key: str = "") -> Any:
        if TerraformGenerator._is_secret_key(key):
            return cls.REDACTED
        if isinstance(value, dict):
            return {item_key: cls._redact(item, str(item_key)) for item_key, item in sorted(value.items())}
        if isinstance(value, list):
            return [cls._redact(item, key) for item in value]
        return value

    @staticmethod
    def _hash_snapshot(snapshot: dict) -> str:
        payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _record_key(source: str, target: str, record_type: str) -> str:
        return json.dumps([source, target, record_type], separators=(",", ":"))

    @classmethod
    def _indexed_records(cls, records: List[dict], identity_fields: tuple) -> dict:
        indexed = {}
        occurrences: Dict[str, int] = {}
        for record in sorted(
            records,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
        ):
            base_key = json.dumps(
                [record[field] for field in identity_fields], separators=(",", ":")
            )
            occurrence = occurrences.get(base_key, 0)
            occurrences[base_key] = occurrence + 1
            indexed[f"{base_key}#{occurrence}"] = record
        return indexed

    @staticmethod
    def _get_version(db: Session, architecture_id: UUID, version_id: UUID) -> ArchitectureVersion:
        version = (
            db.query(ArchitectureVersion)
            .filter(
                ArchitectureVersion.id == version_id,
                ArchitectureVersion.architecture_id == architecture_id,
            )
            .first()
        )
        if version is None:
            raise ArchitectureVersioningError("VERSION_NOT_FOUND", "Architecture version not found")
        return version

    @staticmethod
    def _lock_architecture(db: Session, architecture_id: UUID) -> Architecture:
        architecture = (
            db.query(Architecture)
            .filter(Architecture.id == architecture_id)
            .with_for_update()
            .first()
        )
        if architecture is None:
            raise ArchitectureVersioningError("ARCHITECTURE_NOT_FOUND", "Architecture not found")
        return architecture

    @staticmethod
    def _next_sequence(db: Session, architecture_id: UUID) -> int:
        maximum = (
            db.query(func.max(ArchitectureVersion.version_sequence))
            .filter(ArchitectureVersion.architecture_id == architecture_id)
            .scalar()
        )
        return int(maximum or 0) + 1

    @staticmethod
    def _audit(
        db: Session,
        version: ArchitectureVersion,
        event_type: str,
        actor: Optional[str],
        details: Optional[dict] = None,
    ) -> None:
        db.add(
            ArchitectureVersionEvent(
                architecture_id=version.architecture_id,
                architecture_version_id=version.id,
                event_type=event_type,
                actor=actor,
                details=details,
            )
        )