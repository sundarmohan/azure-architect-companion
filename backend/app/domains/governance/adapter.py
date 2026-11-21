from __future__ import annotations

from typing import Any

from app.domains.governance.legacy_compliance_service import normalize_frameworks, validate_architecture
from app.domains.governance.schemas import GovernanceComplianceSummaryRead


class GovernanceComplianceAdapter:
    SOURCE = "legacy_compliance_engine"

    def resolve_frameworks(self, graph_data: dict | None, requested_frameworks: list[str] | None = None) -> list[str]:
        if requested_frameworks:
            selected = normalize_frameworks(requested_frameworks)
            return selected if selected else ["HIPAA"]

        graph = graph_data if isinstance(graph_data, dict) else {}
        candidates: list[str] = []

        direct = graph.get("compliance")
        if isinstance(direct, list):
            candidates.extend([str(v) for v in direct if v])

        tags = graph.get("tags")
        if isinstance(tags, dict):
            tags_compliance = tags.get("compliance")
            if isinstance(tags_compliance, list):
                candidates.extend([str(v) for v in tags_compliance if v])

        metadata = graph.get("metadata")
        if isinstance(metadata, dict):
            frameworks = metadata.get("compliance_frameworks")
            if isinstance(frameworks, list):
                candidates.extend([str(v) for v in frameworks if v])

        selected = normalize_frameworks(candidates)
        return selected if selected else ["HIPAA"]

    def build_summary(
        self,
        architecture_id: str,
        resources: list[Any],
        frameworks: list[str],
        default_region: str | None = None,
        azure_connection_state: str | None = None,
        azure_connection_message: str | None = None,
    ) -> GovernanceComplianceSummaryRead:
        frameworks = normalize_frameworks(frameworks)
        if not frameworks:
            frameworks = ["HIPAA"]

        payload = {
            "resources": [self._resource_to_legacy_shape(resource, default_region) for resource in resources],
            "compliance": frameworks,
        }
        result = validate_architecture(payload, frameworks=frameworks)

        framework_rows = list((result.get("frameworks") or {}).values())
        summary = result.get("summary") or {}
        live_connected = azure_connection_state == "configured"

        return GovernanceComplianceSummaryRead(
            architecture_id=architecture_id,
            source=self.SOURCE,
            state="evaluated",
            frameworks=frameworks,
            compliant=bool(result.get("compliant")),
            overall_score=result.get("overall_score"),
            evaluated_resources=len(resources),
            violations=list(result.get("violations") or []),
            recommendations=list(result.get("recommendations") or []),
            controls=list(result.get("controls") or []),
            findings=list(result.get("findings") or []),
            framework_results=framework_rows,
            total_findings=int(summary.get("total_findings") or 0),
            critical_count=int(summary.get("critical_count") or 0),
            high_count=int(summary.get("high_count") or 0),
            medium_count=int(summary.get("medium_count") or 0),
            low_count=int(summary.get("low_count") or 0),
            azure_connection_state=azure_connection_state,
            azure_connection_message=azure_connection_message,
            live_connected=live_connected,
            message=result.get("message"),
        )

    def _resource_to_legacy_shape(self, resource: Any, default_region: str | None) -> dict[str, Any]:
        properties = resource.properties if isinstance(resource.properties, dict) else {}
        configuration = {**properties}
        if not configuration.get("region"):
            configuration["region"] = resource.location or default_region

        return {
            "type": self._normalize_resource_type(resource.resource_type),
            "name": resource.name,
            "configuration": configuration,
        }

    @staticmethod
    def _normalize_resource_type(resource_type: str) -> str:
        normalized = (resource_type or "").strip().lower()
        if normalized in {"sql", "sqlserver"}:
            return "db"
        return normalized
