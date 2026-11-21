from __future__ import annotations

from typing import Any

from app.domains.governance.legacy_security_service import (
    calculate_risk_levels,
    detect_secrets_in_architecture,
    scan_architecture_security,
)
from app.domains.governance.schemas import GovernanceSecuritySummaryRead


class GovernanceSecurityAdapter:
    SOURCE = "legacy_security_engine"

    def build_summary(self, architecture_id: str, resources: list[Any], relationships: list[Any]) -> GovernanceSecuritySummaryRead:
        payload = {
            "resources": [self._resource_to_legacy_shape(resource) for resource in resources],
            "connections": [self._relationship_to_legacy_shape(relationship) for relationship in relationships],
        }

        findings = scan_architecture_security(payload)
        secrets = detect_secrets_in_architecture(payload)
        findings_with_secrets = [*findings, *secrets]
        risk = calculate_risk_levels(findings_with_secrets, payload)

        critical = sum(1 for item in findings_with_secrets if str(item.get("severity", "")).lower() == "critical")
        high = sum(1 for item in findings_with_secrets if str(item.get("severity", "")).lower() == "high")
        medium = sum(1 for item in findings_with_secrets if str(item.get("severity", "")).lower() == "medium")
        low = sum(1 for item in findings_with_secrets if str(item.get("severity", "")).lower() == "low")

        return GovernanceSecuritySummaryRead(
            architecture_id=architecture_id,
            source=self.SOURCE,
            state="evaluated",
            risk_level=str(risk.get("overall") or "low"),
            security_score=float(risk.get("score") or 0),
            evaluated_resources=len(resources),
            total_findings=len(findings_with_secrets),
            critical_count=critical,
            high_count=high,
            medium_count=medium,
            low_count=low,
            secrets_count=len(secrets),
            findings=findings,
            secrets=secrets,
            message=None,
        )

    def _resource_to_legacy_shape(self, resource: Any) -> dict[str, Any]:
        properties = resource.properties if isinstance(resource.properties, dict) else {}
        return {
            "id": str(resource.id),
            "name": resource.name,
            "resource_type": self._normalize_resource_type(resource.resource_type),
            "network_access": self._resolve_network_access(properties),
            "encryption_at_rest": bool(properties.get("encryption_at_rest") or properties.get("encryption")),
            "managed_identity": bool(properties.get("managed_identity") or properties.get("identity_enabled")),
            "nsg_applied": bool(properties.get("nsg_applied") or properties.get("nsg") or properties.get("firewall")),
            "configuration": {**properties},
        }

    def _relationship_to_legacy_shape(self, relationship: Any) -> dict[str, Any]:
        props = relationship.properties if isinstance(relationship.properties, dict) else {}
        return {
            "id": str(relationship.id),
            "source_id": str(relationship.source_resource_id),
            "source_name": str(relationship.source_resource_id),
            "target_id": str(relationship.target_resource_id),
            "is_encrypted": bool(props.get("is_encrypted") or props.get("encrypted") or props.get("tls_enabled")),
        }

    @staticmethod
    def _resolve_network_access(properties: dict[str, Any]) -> str:
        explicit = str(properties.get("network_access") or "").strip().lower()
        if explicit in {"public", "private"}:
            return explicit
        if properties.get("public_endpoint") is True or properties.get("public_network_access") is True:
            return "public"
        return "private"

    @staticmethod
    def _normalize_resource_type(resource_type: str) -> str:
        value = (resource_type or "").strip().lower()
        mapping = {
            "vm": "azure-vm",
            "sql": "azure-sql",
            "sqlserver": "azure-sql",
            "storage": "azure-blob",
            "appservice": "azure-app",
            "container": "azure-aks",
            "aks": "azure-aks",
            "vnet": "azure-vnet",
            "subnet": "azure-subnet",
        }
        return mapping.get(value, value)
