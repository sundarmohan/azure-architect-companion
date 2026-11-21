from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.architecture.models import Architecture, ArchitectureRelationship, ArchitectureResource, AzureResourceGroup, AzureSubscription
from app.domains.cost.service import CostEstimationService
from app.domains.governance import GovernanceComplianceAdapter, GovernanceSecurityAdapter
from app.domains.intelligence.service import IntelligenceService
from app.domains.monitoring.incident_adapter import MonitoringIncidentAdapter
from app.domains.monitoring.schemas import MonitoringRequest
from app.domains.monitoring.service import MonitoringService
from app.domains.settings.service import SettingsService

from .schemas import ArchitectureExecutiveReportRead, ArchitectureSnapshotRead, ExecutiveHighlightsRead, ExecutiveReportRequest


class ExecutiveReportService:
    def __init__(self, *, settings_service: SettingsService | None = None) -> None:
        self._settings_service = settings_service or SettingsService()

    async def build_architecture_executive_report(
        self,
        *,
        db: AsyncSession,
        architecture: Architecture,
        resources: list[ArchitectureResource],
        relationships: list[ArchitectureRelationship],
        resource_groups: list[AzureResourceGroup],
        subscriptions: list[AzureSubscription],
        request: ExecutiveReportRequest,
    ) -> ArchitectureExecutiveReportRead:
        monitoring_request = MonitoringRequest(
            start_time=datetime.now(timezone.utc) - timedelta(hours=24),
            end_time=datetime.now(timezone.utc),
            interval=request.interval,
        )
        start_time, end_time = monitoring_request.resolved_window()

        monitoring_service = MonitoringService()
        monitoring_summary = await monitoring_service.monitor_architecture(
            architecture=architecture,
            resources=resources,
            resource_groups=resource_groups,
            subscriptions=subscriptions,
            start_time=start_time,
            end_time=end_time,
            interval=request.interval,
        )

        incident_summary = MonitoringIncidentAdapter().build_summary(
            architecture_id=str(architecture.id),
            monitoring_summary=monitoring_summary,
        )

        cost_service = CostEstimationService()
        cost_estimate = await cost_service.estimate_architecture_cost(
            architecture=architecture,
            resources=resources,
            resource_groups=resource_groups,
            subscriptions=subscriptions,
            region_override=architecture.default_region,
        )

        actual_cost = None
        if request.include_actual_cost:
            actual_cost = await cost_service.get_architecture_actual_cost(
                architecture=architecture,
                subscriptions=subscriptions,
                requested_subscription_id=request.actual_cost_subscription_id,
                start_date=request.actual_cost_start_date,
                end_date=request.actual_cost_end_date,
            )

        compliance_adapter = GovernanceComplianceAdapter()
        frameworks = compliance_adapter.resolve_frameworks(architecture.graph_data, request.frameworks or None)
        compliance_summary = compliance_adapter.build_summary(
            architecture_id=str(architecture.id),
            resources=resources,
            frameworks=frameworks,
            default_region=architecture.default_region,
        )

        security_summary = GovernanceSecurityAdapter().build_summary(
            architecture_id=str(architecture.id),
            resources=resources,
            relationships=relationships,
        )

        intelligence_summary = await IntelligenceService(settings_service=self._settings_service).analyze_architecture(
            architecture=architecture,
            resources=resources,
            relationships=relationships,
            resource_groups=resource_groups,
            subscriptions=subscriptions,
            requested_provider=request.provider,
            db=db,
        )

        settings_snapshot = await self._settings_service.get_settings_overview(db=db)

        notes: list[str] = []
        if monitoring_summary.state in {"not_configured", "authentication_failure", "permission_failure", "azure_api_failure"}:
            notes.append("Monitoring contains controlled Azure connectivity/permission states.")
        if not actual_cost or not actual_cost.available:
            notes.append("Actual billed cost is unavailable; verify Azure Cost Management credentials and subscription linkage.")
        if intelligence_summary.provider == "deterministic_fallback":
            notes.append("Intelligence used deterministic fallback or provider fallback path.")

        highlights = ExecutiveHighlightsRead(
            findings_count=intelligence_summary.finding_count,
            recommendations_count=len(intelligence_summary.recommendations),
            incidents_count=incident_summary.incident_count,
            critical_monitoring_count=monitoring_summary.critical_count,
            monthly_estimated_cost=cost_estimate.total_monthly_cost,
            actual_cost_available=bool(actual_cost and actual_cost.available),
            security_risk_level=security_summary.risk_level,
            provider_used=intelligence_summary.provider,
        )

        architecture_snapshot = ArchitectureSnapshotRead(
            id=str(architecture.id),
            name=architecture.name,
            provider=architecture.provider,
            environment=architecture.environment,
            status=architecture.status,
            default_region=architecture.default_region,
            resource_count=len(resources),
            relationship_count=len(relationships),
            resource_group_count=len(resource_groups),
            subscription_count=len(subscriptions),
        )

        return ArchitectureExecutiveReportRead(
            architecture=architecture_snapshot,
            highlights=highlights,
            monitoring=monitoring_summary,
            incidents=incident_summary,
            cost_estimate=cost_estimate,
            actual_cost=actual_cost,
            governance_compliance=compliance_summary,
            governance_security=security_summary,
            intelligence=intelligence_summary,
            settings_snapshot=settings_snapshot,
            notes=notes,
        )
