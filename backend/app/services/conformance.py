"""Deterministic comparison of canonical desired state with normalized M10 evidence."""

from __future__ import annotations

import hashlib
import json
import threading
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from ..core.config import Settings, settings
from ..enums import (
    ConformanceEventType,
    ConformanceOverallStatus,
    DriftCategory,
    ResourceConformanceStatus,
    ValidationFindingSeverity,
)
from ..models import (
    Architecture,
    ArchitectureVersion,
    AzureIntelligenceSnapshot,
    ConformanceAssessment,
    ConformanceEvent,
    ConformanceFinding,
    Dependency,
    Relationship,
    Resource,
    ResourceCatalog,
    TerraformExecution,
)
from .architecture_versioning import ArchitectureVersioningService
from .azure_intelligence import AzureResourceIntelligenceService


class ConformanceError(ValueError):
    """Safe M11 application error."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class ConformanceEngine:
    """Create immutable, secret-safe conformance assessments in linear time."""

    ENGINE_VERSION = "1.0.0"
    SECRET_VALUE_REDACTED = "SECRET_VALUE_REDACTED"
    RESOURCE_KEY_TAG = "azure-architect-resource-key"
    _locks_guard = threading.Lock()
    _locks: dict[str, threading.Lock] = {}
    _secret_fragments = (
        "password", "passwd", "secret", "token", "api_key", "apikey",
        "access_key", "private_key", "connection_string", "credential", "authorization",
    )

    @classmethod
    def assess(
        cls,
        db: Session,
        architecture_id: UUID,
        version_id: UUID,
        azure_snapshot_id: UUID,
        terraform_execution_id: UUID | None = None,
        config: Settings = settings,
    ) -> ConformanceAssessment:
        architecture = db.query(Architecture).filter(Architecture.id == architecture_id).first()
        version = db.query(ArchitectureVersion).filter(
            ArchitectureVersion.id == version_id,
            ArchitectureVersion.architecture_id == architecture_id,
        ).first()
        if not architecture or not version:
            raise ConformanceError("ARCHITECTURE_VERSION_NOT_FOUND", "Architecture version not found", 404)
        snapshot = AzureResourceIntelligenceService.get_snapshot(db, azure_snapshot_id, config)
        if snapshot is None:
            raise ConformanceError("AZURE_SNAPSHOT_NOT_FOUND", "Azure intelligence snapshot not found for the configured subscription", 404)
        execution = cls._execution(db, architecture_id, version_id, terraform_execution_id)
        desired_hash = ArchitectureVersioningService.snapshot_hash(db, architecture_id, version_id)
        comparison_hash = cls.comparison_hash(desired_hash, snapshot.snapshot_hash)
        lock_key = f"{architecture_id}:{version_id}:{azure_snapshot_id}"

        with cls._scope_lock(lock_key):
            locked_version = db.query(ArchitectureVersion).filter(
                ArchitectureVersion.id == version_id,
                ArchitectureVersion.architecture_id == architecture_id,
            ).with_for_update().first()
            if locked_version is None:
                raise ConformanceError("ARCHITECTURE_VERSION_NOT_FOUND", "Architecture version not found", 404)
            version = locked_version
            assessment = ConformanceAssessment(
                architecture_id=architecture_id,
                architecture_version_id=version_id,
                azure_snapshot_id=snapshot.id,
                terraform_execution_id=execution.id if execution else None,
                architecture_snapshot_hash=desired_hash,
                azure_snapshot_hash=snapshot.snapshot_hash,
                terraform_generation_hash=execution.generation_hash if execution else None,
                terraform_plan_hash=execution.plan_artifact_hash if execution else None,
                terraform_execution_state=execution.state if execution else None,
                engine_version=cls.ENGINE_VERSION,
                comparison_hash=comparison_hash,
                overall_status=ConformanceOverallStatus.ERROR.value,
                summary={},
            )
            db.add(assessment)
            db.flush()
            cls._event(db, assessment, ConformanceEventType.CONFORMANCE_STARTED.value, {
                "architecture_version_id": str(version_id),
                "azure_snapshot_id": str(snapshot.id),
                "comparison_hash": comparison_hash,
            })
            db.commit()
            try:
                compared = cls._compare(db, version, snapshot)
                findings = list({item["finding_key"]: item for item in compared}.values())
                for item in findings:
                    db.add(ConformanceFinding(assessment_id=assessment.id, desired_version=version.version_number, **item))
                assessment.summary = cls._summary(findings)
                assessment.overall_status = cls._overall_status(assessment.summary)
                cls._event(db, assessment, ConformanceEventType.CONFORMANCE_COMPLETED.value, {
                    "overall_status": assessment.overall_status,
                    "summary": assessment.summary,
                })
                previous = cls._previous(db, architecture_id, version_id, assessment.id)
                if assessment.overall_status == ConformanceOverallStatus.DRIFTED.value:
                    cls._event(db, assessment, ConformanceEventType.DRIFT_DETECTED.value, {"comparison_hash": comparison_hash})
                elif previous and previous.overall_status == ConformanceOverallStatus.DRIFTED.value:
                    cls._event(db, assessment, ConformanceEventType.DRIFT_RESOLVED.value, {"previous_assessment_id": str(previous.id)})
                db.commit()
                return cls.get(db, architecture_id, version_id, assessment.id)
            except Exception as error:
                db.rollback()
                assessment = db.query(ConformanceAssessment).filter(ConformanceAssessment.id == assessment.id).one()
                assessment.summary = {"error": "Conformance assessment could not complete"}
                cls._event(db, assessment, ConformanceEventType.CONFORMANCE_FAILED.value, {"code": "CONFORMANCE_ENGINE_ERROR"})
                db.commit()
                if isinstance(error, ConformanceError):
                    raise
                raise ConformanceError("CONFORMANCE_ENGINE_ERROR", "Conformance assessment could not complete", 500) from None

    @classmethod
    def list_assessments(cls, db: Session, architecture_id: UUID, version_id: UUID) -> list[ConformanceAssessment]:
        cls._version(db, architecture_id, version_id)
        return (
            db.query(ConformanceAssessment)
            .options(joinedload(ConformanceAssessment.findings), joinedload(ConformanceAssessment.events))
            .filter(
                ConformanceAssessment.architecture_id == architecture_id,
                ConformanceAssessment.architecture_version_id == version_id,
            )
            .order_by(ConformanceAssessment.created_at.desc(), ConformanceAssessment.id.desc())
            .all()
        )

    @classmethod
    def get(cls, db: Session, architecture_id: UUID, version_id: UUID, assessment_id: UUID) -> ConformanceAssessment:
        assessment = (
            db.query(ConformanceAssessment)
            .options(joinedload(ConformanceAssessment.findings), joinedload(ConformanceAssessment.events))
            .filter(
                ConformanceAssessment.id == assessment_id,
                ConformanceAssessment.architecture_id == architecture_id,
                ConformanceAssessment.architecture_version_id == version_id,
            )
            .first()
        )
        if assessment is None:
            raise ConformanceError("CONFORMANCE_ASSESSMENT_NOT_FOUND", "Conformance assessment not found", 404)
        return assessment

    @classmethod
    def compare_assessments(
        cls,
        db: Session,
        architecture_id: UUID,
        version_id: UUID,
        assessment_id: UUID,
        other_assessment_id: UUID,
    ) -> dict[str, Any]:
        left = cls.get(db, architecture_id, version_id, assessment_id)
        right = cls.get(db, architecture_id, version_id, other_assessment_id)
        left_map = {item.finding_key: cls._finding_signature(item) for item in left.findings if item.status != ResourceConformanceStatus.CONFORMANT.value}
        right_map = {item.finding_key: cls._finding_signature(item) for item in right.findings if item.status != ResourceConformanceStatus.CONFORMANT.value}
        left_keys, right_keys = set(left_map), set(right_map)
        return {
            "architecture_id": architecture_id,
            "architecture_version_id": version_id,
            "from_assessment_id": left.id,
            "to_assessment_id": right.id,
            "new_drift": [right_map[key] for key in sorted(right_keys - left_keys)],
            "resolved_drift": [left_map[key] for key in sorted(left_keys - right_keys)],
            "persistent_drift": [right_map[key] for key in sorted(left_keys & right_keys)],
        }

    @classmethod
    def _compare(cls, db: Session, version: ArchitectureVersion, snapshot: AzureIntelligenceSnapshot) -> list[dict[str, Any]]:
        desired_resources = db.query(Resource).filter(Resource.architecture_version_id == version.id).order_by(Resource.resource_key).all()
        relationships = db.query(Relationship).filter(Relationship.architecture_version_id == version.id).all()
        dependencies = db.query(Dependency).filter(Dependency.architecture_version_id == version.id).all()
        catalog_entries = db.query(ResourceCatalog).filter(ResourceCatalog.resource_type.in_({item.resource_type for item in desired_resources})).all() if desired_resources else []
        catalogs = {item.resource_type.casefold(): item for item in catalog_entries}
        desired_by_id = {item.id: item for item in desired_resources}
        actual_resources = [cls.normalize_actual(item, snapshot) for item in (snapshot.resources or [])]
        actual_by_explicit_key = cls._unique_index(actual_resources, "resource_key")
        actual_by_id = cls._unique_index(actual_resources, "resource_id")
        actual_by_type_name = cls._unique_tuple_index(actual_resources, ("resource_type", "name"))
        consumed: set[str] = set()
        ambiguous: set[str] = set()
        findings: list[dict[str, Any]] = []

        for desired in desired_resources:
            actual, confidence, candidates = cls._correlate(desired, actual_by_explicit_key, actual_by_id, actual_by_type_name)
            if actual is None:
                status = ResourceConformanceStatus.UNKNOWN.value if candidates else ResourceConformanceStatus.MISSING.value
                category = DriftCategory.RESOURCE.value
                severity = ValidationFindingSeverity.WARNING.value if candidates else ValidationFindingSeverity.ERROR.value
                explanation = "Resource correlation is ambiguous" if candidates else "Desired resource was not found in the Azure snapshot"
                findings.append(cls._finding(desired.resource_key, desired.resource_type, None, category, severity, status, None, None, None, explanation, snapshot, version))
                ambiguous.update(candidates)
                continue
            consumed.add(actual["resource_id"])
            resource_findings = cls._compare_resource(desired, actual, catalogs.get(desired.resource_type.casefold()), snapshot, version, desired_by_id)
            resource_findings.extend(cls._compare_relationships(desired, actual, relationships, dependencies, desired_by_id, snapshot, version))
            if resource_findings:
                findings.extend(resource_findings)
            else:
                findings.append(cls._finding(desired.resource_key, desired.resource_type, actual["resource_id"], DriftCategory.RESOURCE.value, ValidationFindingSeverity.INFO.value, ResourceConformanceStatus.CONFORMANT.value, None, None, None, f"Resource matched by {confidence}", snapshot, version))

        for actual in actual_resources:
            if actual["resource_id"] in consumed or actual["resource_id"] in ambiguous:
                continue
            findings.append(cls._finding(actual.get("resource_key") or actual.get("name"), actual.get("resource_type"), actual["resource_id"], DriftCategory.RESOURCE.value, ValidationFindingSeverity.WARNING.value, ResourceConformanceStatus.UNEXPECTED.value, None, cls._safe_resource_identity(actual), None, "Azure resource has no corresponding desired resource", snapshot, version))
        return sorted(findings, key=lambda item: item["finding_key"])

    @classmethod
    def normalize_actual(cls, raw: dict[str, Any], snapshot: AzureIntelligenceSnapshot) -> dict[str, Any]:
        resource_id = str(raw.get("id") or raw.get("resource_id") or "")
        resource_type = str(raw.get("type") or raw.get("resource_type") or "")
        tags = cls._safe(raw.get("tags")) if isinstance(raw.get("tags"), dict) else None
        properties = cls._safe(raw.get("properties") if isinstance(raw.get("properties"), dict) else {})
        explicit_key = raw.get("resource_key") or ((tags or {}).get(cls.RESOURCE_KEY_TAG))
        if not resource_id:
            resource_id = f"unknown:{cls.stable_hash({'type': resource_type, 'name': raw.get('name'), 'location': raw.get('location')})}"
        return {
            "resource_key": str(explicit_key) if explicit_key else None,
            "resource_id": resource_id,
            "resource_type": resource_type,
            "provider": resource_type.split("/", 1)[0] if "/" in resource_type else None,
            "name": str(raw.get("name") or cls._name_from_id(resource_id) or ""),
            "location": raw.get("location"),
            "sku": cls._safe(raw.get("sku") if isinstance(raw.get("sku"), dict) else {}),
            "properties": properties,
            "tags": tags,
            "parent_resource_id": raw.get("parent_id") or raw.get("parent_resource_id"),
            "resource_group": raw.get("resourceGroup") or raw.get("resource_group"),
            "relationships": cls._safe(raw.get("relationships")) if isinstance(raw.get("relationships"), list) else None,
            "dependencies": cls._safe(raw.get("dependencies")) if isinstance(raw.get("dependencies"), list) else None,
            "source": raw.get("source") or "AZURE_RESOURCE_GRAPH",
            "snapshot_id": str(snapshot.id),
        }

    @classmethod
    def _compare_resource(cls, desired: Resource, actual: dict[str, Any], catalog: ResourceCatalog | None, snapshot: AzureIntelligenceSnapshot, version: ArchitectureVersion, desired_by_id: dict[UUID, Resource]) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        cls._compare_scalar(findings, desired, actual, "resource_type", desired.resource_type, actual.get("resource_type"), DriftCategory.RESOURCE.value, ValidationFindingSeverity.ERROR.value, snapshot, version)
        cls._compare_scalar(findings, desired, actual, "name", desired.name, actual.get("name"), DriftCategory.RESOURCE.value, ValidationFindingSeverity.ERROR.value, snapshot, version)
        cls._compare_location(findings, desired, actual, snapshot, version)
        desired_sku = desired.sku if isinstance(desired.sku, dict) else {}
        actual_sku = actual.get("sku") or {}
        for field in ("name", "tier"):
            if field in desired_sku:
                cls._compare_scalar(findings, desired, actual, f"sku.{field}", desired_sku[field], actual_sku.get(field), DriftCategory.SKU.value, ValidationFindingSeverity.ERROR.value, snapshot, version)
        cls._compare_tags(findings, desired, actual, snapshot, version)
        cls._compare_hierarchy(findings, desired, actual, desired_by_id, snapshot, version)
        specifications = (((catalog.resource_metadata or {}).get("conformance") or {}).get("properties") or []) if catalog else []
        for specification in specifications:
            if not isinstance(specification, dict) or not isinstance(specification.get("path"), str):
                continue
            path = specification["path"]
            desired_value, desired_known = cls._path(desired.properties or {}, path)
            if not desired_known:
                continue
            actual_value, actual_known = cls._path(actual.get("properties") or {}, path)
            category = cls._category(specification.get("category"), path)
            severity = specification.get("severity") if specification.get("severity") in {"ERROR", "WARNING", "INFO"} else ValidationFindingSeverity.WARNING.value
            cls._compare_scalar(findings, desired, actual, f"properties.{path}", desired_value, actual_value if actual_known else None, category, severity, snapshot, version, actual_known)
        return findings

    @classmethod
    def _compare_location(cls, findings: list[dict[str, Any]], desired: Resource, actual: dict[str, Any], snapshot: AzureIntelligenceSnapshot, version: ArchitectureVersion) -> None:
        if desired.location is None:
            return
        actual_location = actual.get("location")
        if actual_location is None:
            cls._compare_scalar(findings, desired, actual, "location", desired.location, None, DriftCategory.LOCATION.value, ValidationFindingSeverity.ERROR.value, snapshot, version)
            return
        if cls._location_identity(desired.location, snapshot) != cls._location_identity(str(actual_location), snapshot):
            findings.append(cls._finding(desired.resource_key, desired.resource_type, actual["resource_id"], DriftCategory.LOCATION.value, ValidationFindingSeverity.ERROR.value, ResourceConformanceStatus.MODIFIED.value, desired.location, actual_location, "location", "Actual location differs from desired state", snapshot, version))

    @classmethod
    def _compare_scalar(cls, findings: list[dict[str, Any]], desired: Resource, actual: dict[str, Any], path: str, desired_value: Any, actual_value: Any, category: str, severity: str, snapshot: AzureIntelligenceSnapshot, version: ArchitectureVersion, actual_known: bool | None = None) -> None:
        if desired_value is None:
            return
        known = actual_known if actual_known is not None else actual_value is not None
        if not known:
            findings.append(cls._finding(desired.resource_key, desired.resource_type, actual["resource_id"], category, ValidationFindingSeverity.WARNING.value, ResourceConformanceStatus.UNKNOWN.value, cls._safe_value(path, desired_value), None, path, f"Azure evidence for {path} is unavailable", snapshot, version))
        elif cls._is_secret(path):
            return
        elif cls._normalize_value(desired_value) != cls._normalize_value(actual_value):
            findings.append(cls._finding(desired.resource_key, desired.resource_type, actual["resource_id"], category, severity, ResourceConformanceStatus.MODIFIED.value, cls._safe_value(path, desired_value), cls._safe_value(path, actual_value), path, f"Actual {path} differs from desired state", snapshot, version))

    @classmethod
    def _compare_tags(cls, findings: list[dict[str, Any]], desired: Resource, actual: dict[str, Any], snapshot: AzureIntelligenceSnapshot, version: ArchitectureVersion) -> None:
        desired_tags = desired.tags if isinstance(desired.tags, dict) else {}
        actual_tags = actual.get("tags")
        if actual_tags is None:
            if desired_tags:
                findings.append(cls._finding(desired.resource_key, desired.resource_type, actual["resource_id"], DriftCategory.TAG.value, ValidationFindingSeverity.WARNING.value, ResourceConformanceStatus.UNKNOWN.value, sorted(desired_tags), None, "tags", "Azure tag evidence is unavailable", snapshot, version))
            return
        for key in sorted(set(desired_tags) | set(actual_tags)):
            if key == cls.RESOURCE_KEY_TAG:
                continue
            if key not in actual_tags:
                code, explanation, severity = "MISSING_TAG", "Desired tag is missing", ValidationFindingSeverity.WARNING.value
            elif key not in desired_tags:
                code, explanation, severity = "UNEXPECTED_TAG", "Unexpected Azure tag was discovered", ValidationFindingSeverity.INFO.value
            elif desired_tags[key] != actual_tags[key]:
                code, explanation, severity = "TAG_VALUE_CHANGED", "Azure tag value differs from desired state", ValidationFindingSeverity.WARNING.value
            else:
                continue
            finding = cls._finding(desired.resource_key, desired.resource_type, actual["resource_id"], DriftCategory.TAG.value, severity, ResourceConformanceStatus.MODIFIED.value, cls._safe_value(f"tags.{key}", desired_tags.get(key)), cls._safe_value(f"tags.{key}", actual_tags.get(key)), f"tags.{key}", explanation, snapshot, version)
            finding["evidence"]["difference_code"] = code
            findings.append(finding)

    @classmethod
    def _compare_hierarchy(cls, findings: list[dict[str, Any]], desired: Resource, actual: dict[str, Any], desired_by_id: dict[UUID, Resource], snapshot: AzureIntelligenceSnapshot, version: ArchitectureVersion) -> None:
        if desired.parent_resource_id is None:
            if actual.get("parent_resource_id") or (actual.get("resource_group") and not desired.resource_type.casefold().endswith("/resourcegroups")):
                findings.append(cls._finding(desired.resource_key, desired.resource_type, actual["resource_id"], DriftCategory.HIERARCHY.value, ValidationFindingSeverity.WARNING.value, ResourceConformanceStatus.MODIFIED.value, None, actual.get("parent_resource_id") or actual.get("resource_group"), "parent", "Azure reports an unexpected parent", snapshot, version))
            return
        parent = desired_by_id.get(desired.parent_resource_id)
        actual_parent = actual.get("parent_resource_id")
        actual_group = actual.get("resource_group")
        if not parent:
            findings.append(cls._finding(desired.resource_key, desired.resource_type, actual["resource_id"], DriftCategory.HIERARCHY.value, ValidationFindingSeverity.WARNING.value, ResourceConformanceStatus.UNKNOWN.value, None, None, "parent", "Desired parent could not be resolved", snapshot, version))
        elif actual_parent and cls._identity_in_id(parent.name, str(actual_parent)):
            return
        elif actual_group and cls._same(parent.name, actual_group):
            return
        elif actual_parent is None and actual_group is None:
            findings.append(cls._finding(desired.resource_key, desired.resource_type, actual["resource_id"], DriftCategory.HIERARCHY.value, ValidationFindingSeverity.WARNING.value, ResourceConformanceStatus.UNKNOWN.value, parent.resource_key, None, "parent", "Azure parent evidence is unavailable", snapshot, version))
        else:
            findings.append(cls._finding(desired.resource_key, desired.resource_type, actual["resource_id"], DriftCategory.HIERARCHY.value, ValidationFindingSeverity.ERROR.value, ResourceConformanceStatus.MODIFIED.value, parent.resource_key, actual_parent or actual_group, "parent", "Actual parent differs from desired hierarchy", snapshot, version))

    @classmethod
    def _compare_relationships(cls, desired: Resource, actual: dict[str, Any], relationships: list[Relationship], dependencies: list[Dependency], desired_by_id: dict[UUID, Resource], snapshot: AzureIntelligenceSnapshot, version: ArchitectureVersion) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        desired_relationships = [item for item in relationships if item.source_resource_id == desired.id]
        desired_dependencies = [item for item in dependencies if item.resource_id == desired.id]
        findings.extend(cls._edge_findings(desired, actual, desired_relationships, desired_by_id, "relationships", "target_resource_id", "relationship_type", DriftCategory.RELATIONSHIP.value, snapshot, version))
        findings.extend(cls._edge_findings(desired, actual, desired_dependencies, desired_by_id, "dependencies", "depends_on_resource_id", "dependency_type", DriftCategory.DEPENDENCY.value, snapshot, version))
        return findings

    @classmethod
    def _edge_findings(cls, desired: Resource, actual: dict[str, Any], desired_edges: list[Any], desired_by_id: dict[UUID, Resource], actual_field: str, target_field: str, type_field: str, category: str, snapshot: AzureIntelligenceSnapshot, version: ArchitectureVersion) -> list[dict[str, Any]]:
        actual_edges = actual.get(actual_field)
        if actual_edges is None:
            if not desired_edges:
                return []
            return [cls._finding(desired.resource_key, desired.resource_type, actual["resource_id"], category, ValidationFindingSeverity.WARNING.value, ResourceConformanceStatus.UNKNOWN.value, len(desired_edges), None, actual_field, f"Azure {actual_field} evidence is unavailable", snapshot, version)]
        normalized_actual = {
            (str(item.get("target_resource_key") or item.get("target_id") or "").casefold(), str(item.get("type") or "").casefold())
            for item in actual_edges if isinstance(item, dict)
        }
        findings = []
        expected_aliases: set[tuple[str, str]] = set()
        for edge in desired_edges:
            target = desired_by_id.get(getattr(edge, target_field))
            edge_type = str(getattr(edge, type_field)).casefold()
            target_aliases = {target.resource_key.casefold(), target.name.casefold()} if target else {""}
            recorded_id = (target.properties or {}).get("azure_resource_id") if target and isinstance(target.properties, dict) else None
            if isinstance(recorded_id, str):
                target_aliases.add(recorded_id.casefold())
            expected_aliases.update((alias, edge_type) for alias in target_aliases)
            if not any((alias, edge_type) in normalized_actual for alias in target_aliases):
                findings.append(cls._finding(desired.resource_key, desired.resource_type, actual["resource_id"], category, ValidationFindingSeverity.WARNING.value, ResourceConformanceStatus.MODIFIED.value, {"target": target.resource_key if target else None, "type": getattr(edge, type_field)}, None, actual_field, f"Desired {actual_field[:-1]} is not present in Azure evidence", snapshot, version))
        for target_identity, edge_type in sorted(normalized_actual - expected_aliases):
            findings.append(cls._finding(desired.resource_key, desired.resource_type, actual["resource_id"], category, ValidationFindingSeverity.INFO.value, ResourceConformanceStatus.MODIFIED.value, None, {"target": target_identity, "type": edge_type}, actual_field, f"Unexpected Azure {actual_field[:-1]} was discovered", snapshot, version))
        return findings

    @classmethod
    def _correlate(cls, desired: Resource, by_key: dict[str, list[dict[str, Any]]], by_id: dict[str, list[dict[str, Any]]], by_type_name: dict[tuple[str, str], list[dict[str, Any]]]) -> tuple[dict[str, Any] | None, str | None, set[str]]:
        candidates = by_key.get(desired.resource_key.casefold(), [])
        if len(candidates) == 1:
            return candidates[0], "explicit resource_key", set()
        recorded_id = (desired.properties or {}).get("azure_resource_id") if isinstance(desired.properties, dict) else None
        if isinstance(recorded_id, str):
            candidates = by_id.get(recorded_id.casefold(), [])
            if len(candidates) == 1:
                return candidates[0], "recorded Azure resource ID", set()
        candidates = by_type_name.get((desired.resource_type.casefold(), desired.name.casefold()), [])
        if len(candidates) == 1:
            return candidates[0], "exact resource type and name", set()
        return None, None, {item["resource_id"] for item in candidates}

    @classmethod
    def _finding(cls, resource_key: str | None, resource_type: str | None, actual_resource_id: str | None, category: str, severity: str, status: str, desired: Any, actual: Any, path: str | None, explanation: str, snapshot: AzureIntelligenceSnapshot, version: ArchitectureVersion) -> dict[str, Any]:
        semantic = {"resource_key": resource_key, "resource_type": resource_type, "actual_resource_id": actual_resource_id, "category": category, "status": status, "property_path": path}
        return {
            "finding_key": cls.stable_hash(semantic),
            "resource_key": resource_key,
            "resource_type": resource_type,
            "actual_resource_id": actual_resource_id,
            "category": category,
            "severity": severity,
            "status": status,
            "desired_value_safe": cls._safe(desired),
            "actual_value_safe": cls._safe(actual),
            "property_path": path,
            "explanation": explanation,
            "evidence": {"source": "M10_AZURE_SNAPSHOT", "azure_snapshot_id": str(snapshot.id), "retrieved_at": snapshot.retrieved_at.isoformat(), "actual_resource_id": actual_resource_id},
        }

    @staticmethod
    def _summary(findings: list[dict[str, Any]]) -> dict[str, int]:
        summary = {"conformant": 0, "modified": 0, "missing": 0, "unexpected": 0, "unknown": 0, "total_findings": len(findings)}
        resource_states: dict[str, set[str]] = {}
        for finding in findings:
            identity = finding.get("resource_key") or finding.get("actual_resource_id") or finding["finding_key"]
            resource_states.setdefault(str(identity), set()).add(finding["status"])
        for states in resource_states.values():
            if ResourceConformanceStatus.MISSING.value in states:
                summary["missing"] += 1
            elif ResourceConformanceStatus.UNEXPECTED.value in states:
                summary["unexpected"] += 1
            elif ResourceConformanceStatus.MODIFIED.value in states:
                summary["modified"] += 1
            elif ResourceConformanceStatus.UNKNOWN.value in states:
                summary["unknown"] += 1
            else:
                summary["conformant"] += 1
        return summary

    @staticmethod
    def _overall_status(summary: dict[str, int]) -> str:
        deterministic = summary["modified"] + summary["missing"] + summary["unexpected"]
        if deterministic:
            return ConformanceOverallStatus.PARTIAL.value if summary["unknown"] else ConformanceOverallStatus.DRIFTED.value
        if summary["unknown"]:
            return ConformanceOverallStatus.UNKNOWN.value
        return ConformanceOverallStatus.CONFORMANT.value

    @classmethod
    def comparison_hash(cls, architecture_hash: str, azure_hash: str) -> str:
        return cls.stable_hash({"architecture_snapshot_hash": architecture_hash, "azure_snapshot_hash": azure_hash, "engine_version": cls.ENGINE_VERSION})

    @staticmethod
    def stable_hash(value: Any) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()

    @classmethod
    def _safe(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): cls.SECRET_VALUE_REDACTED if cls._is_secret(str(key)) else cls._safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._safe(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    @classmethod
    def _safe_value(cls, path: str, value: Any) -> Any:
        return cls.SECRET_VALUE_REDACTED if cls._is_secret(path) else cls._safe(value)

    @classmethod
    def _is_secret(cls, name: str) -> bool:
        normalized = name.casefold().replace("-", "_")
        return any(fragment in normalized for fragment in cls._secret_fragments)

    @staticmethod
    def _normalize_value(value: Any) -> Any:
        if isinstance(value, str):
            return value.casefold()
        if isinstance(value, dict):
            return {str(key): ConformanceEngine._normalize_value(item) for key, item in sorted(value.items())}
        if isinstance(value, list):
            return [ConformanceEngine._normalize_value(item) for item in value]
        return value

    @staticmethod
    def _path(value: dict[str, Any], path: str) -> tuple[Any, bool]:
        current: Any = value
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                return None, False
            current = current[part]
        return current, True

    @staticmethod
    def _category(value: Any, path: str) -> str:
        allowed = {item.value for item in DriftCategory}
        if value in allowed:
            return str(value)
        root = path.split(".", 1)[0].casefold()
        return {
            "network": DriftCategory.NETWORK.value,
            "networking": DriftCategory.NETWORK.value,
            "security": DriftCategory.SECURITY.value,
            "identity": DriftCategory.SECURITY.value,
            "monitoring": DriftCategory.MONITORING.value,
            "backup": DriftCategory.BACKUP.value,
        }.get(root, DriftCategory.CONFIGURATION.value)

    @staticmethod
    def _unique_index(items: list[dict[str, Any]], field: str) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            value = item.get(field)
            if value:
                result.setdefault(str(value).casefold(), []).append(item)
        return result

    @staticmethod
    def _unique_tuple_index(items: list[dict[str, Any]], fields: tuple[str, str]) -> dict[tuple[str, str], list[dict[str, Any]]]:
        result: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for item in items:
            values = tuple(str(item.get(field) or "").casefold() for field in fields)
            result.setdefault(values, []).append(item)
        return result

    @staticmethod
    def _name_from_id(resource_id: str) -> str | None:
        return resource_id.rstrip("/").split("/")[-1] if resource_id else None

    @staticmethod
    def _parent_id(resource_id: str) -> str | None:
        parts = resource_id.rstrip("/").split("/")
        return "/".join(parts[:-2]) if len(parts) >= 2 else None

    @staticmethod
    def _identity_in_id(name: str, resource_id: str) -> bool:
        return resource_id.rstrip("/").split("/")[-1].casefold() == name.casefold()

    @staticmethod
    def _same(left: Any, right: Any) -> bool:
        return isinstance(left, str) and isinstance(right, str) and left.casefold() == right.casefold()

    @staticmethod
    def _location_identity(location: str, snapshot: AzureIntelligenceSnapshot) -> str:
        requested = location.casefold()
        for item in snapshot.regions or []:
            values = [item.get("name"), item.get("display_name"), item.get("regional_display_name"), *(item.get("aliases") or [])]
            normalized = {str(value).casefold() for value in values if value}
            if requested in normalized:
                return str(item.get("name") or location).casefold()
        return requested

    @staticmethod
    def _safe_resource_identity(actual: dict[str, Any]) -> dict[str, Any]:
        return {key: actual.get(key) for key in ("resource_type", "name", "location")}

    @classmethod
    def _execution(cls, db: Session, architecture_id: UUID, version_id: UUID, execution_id: UUID | None) -> TerraformExecution | None:
        if execution_id is None:
            return None
        execution = db.query(TerraformExecution).filter(
            TerraformExecution.id == execution_id,
            TerraformExecution.architecture_id == architecture_id,
            TerraformExecution.architecture_version_id == version_id,
        ).first()
        if execution is None:
            raise ConformanceError("TERRAFORM_EXECUTION_NOT_FOUND", "Terraform execution does not belong to this architecture version", 404)
        return execution

    @staticmethod
    def _version(db: Session, architecture_id: UUID, version_id: UUID) -> ArchitectureVersion:
        version = db.query(ArchitectureVersion).filter(ArchitectureVersion.id == version_id, ArchitectureVersion.architecture_id == architecture_id).first()
        if version is None:
            raise ConformanceError("ARCHITECTURE_VERSION_NOT_FOUND", "Architecture version not found", 404)
        return version

    @staticmethod
    def _previous(db: Session, architecture_id: UUID, version_id: UUID, current_id: UUID) -> ConformanceAssessment | None:
        return db.query(ConformanceAssessment).filter(
            ConformanceAssessment.architecture_id == architecture_id,
            ConformanceAssessment.architecture_version_id == version_id,
            ConformanceAssessment.id != current_id,
        ).order_by(ConformanceAssessment.created_at.desc()).first()

    @staticmethod
    def _event(db: Session, assessment: ConformanceAssessment, event_type: str, details: dict[str, Any]) -> None:
        db.add(ConformanceEvent(assessment_id=assessment.id, event_type=event_type, details=ConformanceEngine._safe(details)))

    @classmethod
    def _scope_lock(cls, key: str) -> threading.Lock:
        with cls._locks_guard:
            return cls._locks.setdefault(key, threading.Lock())

    @staticmethod
    def _finding_signature(finding: ConformanceFinding) -> dict[str, Any]:
        return {
            "finding_key": finding.finding_key,
            "resource_key": finding.resource_key,
            "resource_type": finding.resource_type,
            "category": finding.category,
            "severity": finding.severity,
            "status": finding.status,
            "property_path": finding.property_path,
            "explanation": finding.explanation,
        }
