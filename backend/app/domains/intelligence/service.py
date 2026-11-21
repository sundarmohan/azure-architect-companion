from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.domains.architecture.models import Architecture
from app.domains.cost.service import CostEstimationService
from app.domains.governance import GovernanceComplianceAdapter, GovernanceSecurityAdapter
from app.domains.monitoring.incident_adapter import MonitoringIncidentAdapter
from app.domains.monitoring.schemas import ArchitectureMonitoringSummaryRead
from sqlalchemy.ext.asyncio import AsyncSession
from app.domains.intelligence.providers import (
    DeterministicIntelligenceProvider,
    GeminiIntelligenceProvider,
    IntelligenceContext,
    OpenAIIntelligenceProvider,
    ProviderExecutionResult,
    compact_intelligence_context,
)
from app.domains.intelligence.schemas import IntelligenceAnalysisRead
from app.domains.monitoring.service import MonitoringService
from app.domains.settings.service import SettingsService


class IntelligenceService:
    def __init__(self, settings_service: SettingsService | None = None) -> None:
        self._settings = settings_service or SettingsService()
        self._deterministic_provider = DeterministicIntelligenceProvider()

    async def analyze_architecture(
        self,
        *,
        architecture: Architecture,
        resources: list[Any],
        relationships: list[Any],
        resource_groups: list[Any],
        subscriptions: list[Any],
        requested_provider: str | None = None,
        db: AsyncSession | None = None,
    ) -> IntelligenceAnalysisRead:
        monitoring_summary = await self._load_monitoring(
            architecture=architecture,
            resources=resources,
            resource_groups=resource_groups,
            subscriptions=subscriptions,
        )
        incident_summary = self._load_incident_summary(
            architecture_id=str(architecture.id),
            monitoring_summary=monitoring_summary,
        )
        cost_estimate, actual_cost = await self._load_cost(
            architecture=architecture,
            resources=resources,
            resource_groups=resource_groups,
            subscriptions=subscriptions,
        )

        compliance_adapter = GovernanceComplianceAdapter()
        frameworks = compliance_adapter.resolve_frameworks(architecture.graph_data, None)
        compliance_summary = compliance_adapter.build_summary(
            architecture_id=str(architecture.id),
            resources=resources,
            frameworks=frameworks,
            default_region=architecture.default_region,
        )

        security_adapter = GovernanceSecurityAdapter()
        security_summary = security_adapter.build_summary(
            architecture_id=str(architecture.id),
            resources=resources,
            relationships=relationships,
        )

        context = IntelligenceContext(
            architecture_id=str(architecture.id),
            architecture_name=architecture.name,
            architecture_provider=architecture.provider,
            resources=[self._resource_to_dict(item) for item in resources],
            relationships=[self._relationship_to_dict(item) for item in relationships],
            resource_groups=[self._resource_group_to_dict(item) for item in resource_groups],
            subscriptions=[self._subscription_to_dict(item) for item in subscriptions],
            monitoring_summary=monitoring_summary,
            cost_estimate=cost_estimate,
            actual_cost=actual_cost,
            compliance_summary=compliance_summary.model_dump(),
            security_summary=security_summary.model_dump(),
            incident_summary=incident_summary,
        )

        provider_result = await self._analyze_with_provider(context=context, requested_provider=requested_provider, db=db)
        return self._build_response(
            architecture_id=str(architecture.id),
            requested_provider=requested_provider,
            provider_result=provider_result,
        )

    async def _analyze_with_provider(
        self,
        *,
        context: IntelligenceContext,
        requested_provider: str | None,
        db: AsyncSession | None,
    ) -> ProviderExecutionResult:
        order = self._provider_order(requested_provider)
        fallback_reason: ProviderExecutionResult | None = None

        for provider_name in order:
            if provider_name == "deterministic_fallback":
                deterministic = await self._deterministic_provider.analyze(context)
                if fallback_reason is not None:
                    deterministic.message = self._fallback_message(fallback_reason)
                return deterministic

            result = await self._run_external_provider(provider_name, context, db=db)
            if result.state == "configured":
                return result
            if fallback_reason is None:
                fallback_reason = result

        deterministic = await self._deterministic_provider.analyze(context)
        if fallback_reason is not None:
            deterministic.message = self._fallback_message(fallback_reason)
        return deterministic

    async def _run_external_provider(self, provider_name: str, context: IntelligenceContext, db: AsyncSession | None) -> ProviderExecutionResult:
        if provider_name == "openai":
            provider = OpenAIIntelligenceProvider(await self._settings.get_provider_secret("openai", db=db))
            return await provider.analyze(context)
        provider = GeminiIntelligenceProvider(await self._settings.get_provider_secret("gemini", db=db))
        return await provider.analyze(context)

    def _provider_order(self, requested_provider: str | None) -> list[str]:
        requested = (requested_provider or "").strip().lower() or None
        if requested == "deterministic_fallback":
            return ["deterministic_fallback"]
        if requested in {"openai", "gemini"}:
            secondary = "gemini" if requested == "openai" else "openai"
            return [requested, secondary, "deterministic_fallback"]
        return ["openai", "gemini", "deterministic_fallback"]

    def _build_response(
        self,
        *,
        architecture_id: str,
        requested_provider: str | None,
        provider_result: ProviderExecutionResult,
    ) -> IntelligenceAnalysisRead:
        findings = provider_result.findings
        recommendations = provider_result.recommendations
        risks = provider_result.risks
        observed_facts = provider_result.observed_facts
        rca = provider_result.rca
        incident_correlations = provider_result.incident_correlations

        if not findings and not recommendations and not risks:
            state = "no_data"
            status = "no_data"
        elif provider_result.source == "monitorai_deterministic_intelligence" and not findings and not recommendations:
            state = "insufficient_data"
            status = "insufficient_data"
        else:
            state = "success"
            status = "success"

        severity_summary = self._severity_summary(findings)
        overall = provider_result.overall_assessment or self._overall_from_findings(severity_summary)

        error_state = None
        if provider_result.source == "monitorai_deterministic_intelligence":
            message = provider_result.message
            if message and "fallback" in message.lower():
                error_state = self._extract_error_state_from_message(message)
        else:
            message = provider_result.message

        return IntelligenceAnalysisRead(
            architecture_id=architecture_id,
            status=status,
            source=provider_result.source,
            provider="deterministic_fallback" if provider_result.source == "monitorai_deterministic_intelligence" else provider_result.provider,
            requested_provider=self._normalize_requested_provider(requested_provider),
            error_state=error_state,
            state=state,
            overall_assessment=overall,
            finding_count=len(findings),
            severity_summary=severity_summary,
            observed_facts=observed_facts,
            findings=findings,
            recommendations=recommendations,
            risks=risks,
            rca=rca,
            incident_correlations=incident_correlations,
            analysis_confidence=provider_result.analysis_confidence,
            limitations=provider_result.limitations,
            generated_at=datetime.now(timezone.utc).isoformat(),
            message=message,
        )

    @staticmethod
    def _normalize_requested_provider(requested_provider: str | None) -> str | None:
        value = (requested_provider or "").strip().lower()
        if value in {"openai", "gemini", "deterministic_fallback"}:
            return value
        return None

    @staticmethod
    def _extract_error_state_from_message(message: str) -> str | None:
        lowered = message.lower()
        for candidate in [
            "not_configured",
            "authentication_failure",
            "permission_failure",
            "provider_error",
            "unavailable",
            "configured",
        ]:
            if candidate in lowered:
                return candidate
        return None

    @staticmethod
    def _fallback_message(result: ProviderExecutionResult) -> str:
        base = result.message or "Selected provider was unavailable."
        return f"Fallback to deterministic intelligence because provider '{result.provider}' returned state '{result.state}'. {base}"

    @staticmethod
    def _severity_summary(findings: list[Any]) -> dict[str, int]:
        summary = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for item in findings:
            sev = str(getattr(item, "severity", "") or "").lower()
            if sev in summary:
                summary[sev] += 1
        return summary

    @staticmethod
    def _overall_from_findings(summary: dict[str, int]) -> str:
        if summary.get("critical", 0) > 0:
            return "Critical architecture risks detected; immediate remediation is recommended."
        if summary.get("high", 0) > 0:
            return "High-priority architecture issues detected; remediation should be planned promptly."
        if summary.get("medium", 0) > 0:
            return "Architecture is operational but has medium-priority optimization and risk findings."
        return "Architecture appears stable with low-severity or no detected risks."

    def build_compact_context(self, context: IntelligenceContext) -> dict[str, Any]:
        return compact_intelligence_context(context)

    async def _load_monitoring(
        self,
        *,
        architecture: Architecture,
        resources: list[Any],
        resource_groups: list[Any],
        subscriptions: list[Any],
    ) -> dict[str, Any] | None:
        try:
            service = MonitoringService()
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(hours=24)
            summary = await service.monitor_architecture(
                architecture=architecture,
                resources=resources,
                resource_groups=resource_groups,
                subscriptions=subscriptions,
                start_time=start_time,
                end_time=end_time,
                interval="PT1H",
            )
            return summary.model_dump()
        except Exception:
            return None

    async def _load_cost(
        self,
        *,
        architecture: Architecture,
        resources: list[Any],
        resource_groups: list[Any],
        subscriptions: list[Any],
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        service = CostEstimationService()

        estimate_payload: dict[str, Any] | None
        try:
            estimate = await service.estimate_architecture_cost(
                architecture=architecture,
                resources=resources,
                resource_groups=resource_groups,
                subscriptions=subscriptions,
                region_override=None,
            )
            estimate_payload = estimate.model_dump()
        except Exception:
            estimate_payload = None

        actual_payload: dict[str, Any] | None
        try:
            actual = await service.get_architecture_actual_cost(
                architecture=architecture,
                subscriptions=subscriptions,
                requested_subscription_id=None,
                start_date=None,
                end_date=None,
            )
            actual_payload = actual.model_dump()
        except Exception:
            actual_payload = None

        return estimate_payload, actual_payload

    @staticmethod
    def _load_incident_summary(
        *,
        architecture_id: str,
        monitoring_summary: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not monitoring_summary:
            return None
        try:
            monitoring_read = ArchitectureMonitoringSummaryRead.model_validate(monitoring_summary)
            summary = MonitoringIncidentAdapter().build_summary(
                architecture_id=architecture_id,
                monitoring_summary=monitoring_read,
            )
            return summary.model_dump()
        except Exception:
            return None

    @staticmethod
    def _resource_to_dict(resource: Any) -> dict[str, Any]:
        return {
            "id": str(resource.id),
            "name": resource.name,
            "resource_type": str(resource.resource_type or "").lower(),
            "parent_resource_id": str(resource.parent_resource_id) if resource.parent_resource_id else None,
            "resource_group_id": str(resource.resource_group_id) if resource.resource_group_id else None,
            "location": resource.location,
            "properties": resource.properties if isinstance(resource.properties, dict) else {},
        }

    @staticmethod
    def _relationship_to_dict(relationship: Any) -> dict[str, Any]:
        return {
            "id": str(relationship.id),
            "source_resource_id": str(relationship.source_resource_id),
            "target_resource_id": str(relationship.target_resource_id),
            "relationship_type": relationship.relationship_type,
            "properties": relationship.properties if isinstance(relationship.properties, dict) else {},
        }

    @staticmethod
    def _resource_group_to_dict(resource_group: Any) -> dict[str, Any]:
        return {
            "id": str(resource_group.id),
            "name": resource_group.name,
            "location": resource_group.location,
            "subscription_id": str(resource_group.subscription_id) if resource_group.subscription_id else None,
        }

    @staticmethod
    def _subscription_to_dict(subscription: Any) -> dict[str, Any]:
        return {
            "id": str(subscription.id),
            "name": subscription.name,
            "subscription_id": subscription.subscription_id,
            "tenant_id": subscription.tenant_id,
        }
