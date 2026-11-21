from pydantic import BaseModel, Field


class AzureSubscriptionCandidateRead(BaseModel):
    subscription_id: str
    name: str
    tenant_id: str | None = None
    state: str | None = None


class MonitoringSubscriptionCreate(BaseModel):
    subscription_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    tenant_id: str | None = Field(default=None, max_length=100)


class MonitoringResourceRead(BaseModel):
    id: str
    name: str
    resource_type: str
    resource_group: str | None = None
    region: str | None = None
    status: str = "unknown"
    status_source: str | None = None
    last_checked: str | None = None
    azure_resource_id: str
    metrics: list[dict] = Field(default_factory=list)
    metric_state: str = "not_checked"
    metric_message: str | None = None


class MonitoringAlertRead(BaseModel):
    id: str
    name: str
    severity: str
    status: str
    resource_name: str | None = None
    resource_id: str | None = None
    timestamp: str | None = None
    condition: str | None = None
    fired_time: str | None = None
    last_updated: str | None = None
    description: str | None = None
    source: str = "Azure Monitor Alerts"


class MonitoringIncidentRead(BaseModel):
    id: str
    title: str
    severity: str
    status: str
    description: str
    created_at: str
    updated_at: str | None = None
    resolved_at: str | None = None
    resource_ids: list[str] = Field(default_factory=list)
    alert_ids: list[str] = Field(default_factory=list)
    timeline: list[dict] = Field(default_factory=list)


class MonitoringUnusedAnalysisRead(BaseModel):
    state: str = "not_checked"
    message: str | None = None
    checked_at: str | None = None
    total_checked: int = 0
    total_unused: int = 0
    estimated_monthly_waste: float | None = None
    findings: list[dict] = Field(default_factory=list)


class MonitoringSubscriptionRead(BaseModel):
    id: str
    subscription_id: str
    name: str
    tenant_id: str | None = None
    service_principal_provider: str
    connection_status: str
    connection_message: str | None = None
    total_resources: int = 0
    healthy_count: int = 0
    warning_count: int = 0
    critical_count: int = 0
    unknown_count: int = 0
    last_checked_at: str | None = None
    resources: list[MonitoringResourceRead] = Field(default_factory=list)
    metrics: dict[str, list[dict]] = Field(default_factory=dict)
    alerts: list[MonitoringAlertRead] = Field(default_factory=list)
    incidents: list[MonitoringIncidentRead] = Field(default_factory=list)
    unused_analysis: MonitoringUnusedAnalysisRead = Field(default_factory=MonitoringUnusedAnalysisRead)
    metrics_state: str = "not_checked"
    alerts_state: str = "not_checked"
    incidents_state: str = "not_checked"
    refresh_state: str = "not_checked"
    refresh_error: str | None = None
    last_successful_at: str | None = None
