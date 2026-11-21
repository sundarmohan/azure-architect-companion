from __future__ import annotations

from datetime import date, datetime, timezone

from pydantic import BaseModel, Field

from app.domains.cost.schemas import ArchitectureActualCostRead, ArchitectureCostEstimateRead
from app.domains.governance.schemas import GovernanceComplianceSummaryRead, GovernanceSecuritySummaryRead
from app.domains.intelligence.schemas import IntelligenceAnalysisRead, ProviderName
from app.domains.monitoring.schemas import ArchitectureMonitoringSummaryRead, MonitoringIncidentSummaryRead
from app.domains.settings.schemas import SettingsOverviewRead


class ExecutiveReportRequest(BaseModel):
    provider: ProviderName | None = None
    frameworks: list[str] = Field(default_factory=list)
    interval: str = "PT1H"
    include_actual_cost: bool = True
    actual_cost_subscription_id: str | None = None
    actual_cost_start_date: date | None = None
    actual_cost_end_date: date | None = None


class ArchitectureSnapshotRead(BaseModel):
    id: str
    name: str
    provider: str
    environment: str
    status: str
    default_region: str | None = None
    resource_count: int
    relationship_count: int
    resource_group_count: int
    subscription_count: int


class ExecutiveHighlightsRead(BaseModel):
    findings_count: int = 0
    recommendations_count: int = 0
    incidents_count: int = 0
    critical_monitoring_count: int = 0
    monthly_estimated_cost: float = 0.0
    actual_cost_available: bool = False
    security_risk_level: str = "unknown"
    provider_used: str = "deterministic_fallback"


class ArchitectureExecutiveReportRead(BaseModel):
    report_type: str = "architecture_executive_summary"
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    architecture: ArchitectureSnapshotRead
    highlights: ExecutiveHighlightsRead
    monitoring: ArchitectureMonitoringSummaryRead
    incidents: MonitoringIncidentSummaryRead
    cost_estimate: ArchitectureCostEstimateRead
    actual_cost: ArchitectureActualCostRead | None = None
    governance_compliance: GovernanceComplianceSummaryRead
    governance_security: GovernanceSecuritySummaryRead
    intelligence: IntelligenceAnalysisRead
    settings_snapshot: SettingsOverviewRead
    notes: list[str] = Field(default_factory=list)
