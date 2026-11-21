from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field


class MonitoringRequest(BaseModel):
    start_time: datetime | None = None
    end_time: datetime | None = None
    interval: str = "PT1H"
    subscription_id: str | None = None

    def resolved_window(self) -> tuple[datetime, datetime]:
        end = self.end_time or datetime.now(timezone.utc)
        start = self.start_time or (end - timedelta(hours=24))
        return start, end


class UnusedResourceRequest(BaseModel):
    lookback_days: int = 7
    subscription_id: str | None = None


class UnusedResourceFindingRead(BaseModel):
    resource_id: str
    resource_name: str
    resource_type: str
    location: str = ""
    resource_group: str = ""
    subscription_id: str = ""
    idle_reason: str
    idle_signals: list[str] = Field(default_factory=list)
    confidence: str = "low"
    recommended_action: str | None = None
    days_checked: int
    monthly_cost_estimate: float = 0.0
    portal_link: str


class UnusedResourceSummaryRead(BaseModel):
    architecture_id: str
    source: str = "legacy_idle_detector"
    state: str
    lookback_days: int
    analysis_start_time: str
    analysis_end_time: str
    total_checked: int
    total_unused: int
    estimated_monthly_waste: float
    azure_connection_state: str = "unavailable"
    azure_connection_message: str | None = None
    message: str | None = None
    unused_resources: list[UnusedResourceFindingRead] = Field(default_factory=list)


class MonitoringMetricPoint(BaseModel):
    timestamp: str
    value: float


class MonitoringMetricSeries(BaseModel):
    name: str
    unit: str | None = None
    aggregation: str | None = None
    points: list[MonitoringMetricPoint] = Field(default_factory=list)


class ResourceMonitoringRead(BaseModel):
    architecture_id: str
    resource_id: str
    resource_name: str
    resource_type: str
    state: str
    source: str = "azure_monitor"
    live: bool = False
    health_status: str | None = None
    metrics: list[MonitoringMetricSeries] = Field(default_factory=list)
    message: str | None = None


class ArchitectureMonitoringSummaryRead(BaseModel):
    architecture_id: str
    state: str
    source: str = "azure_monitor"
    total_resources: int
    monitored_resources: int
    live_resources: int
    healthy_count: int
    warning_count: int
    critical_count: int
    no_data_count: int
    unsupported_count: int
    error_count: int
    resources: list[ResourceMonitoringRead] = Field(default_factory=list)


class MonitoringIncidentRead(BaseModel):
    incident_id: str
    title: str
    severity: str
    status: str
    source: str = "legacy_incident_engine"
    resource_id: str | None = None
    resource_name: str | None = None
    resource_type: str | None = None
    monitoring_state: str | None = None
    health_status: str | None = None
    message: str | None = None
    created_at: str


class MonitoringIncidentSummaryRead(BaseModel):
    architecture_id: str
    source: str = "legacy_incident_engine"
    incident_count: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    incidents: list[MonitoringIncidentRead] = Field(default_factory=list)


class MonitoringTimelineEventRead(BaseModel):
    event_type: str
    timestamp: str
    actor: str
    details: str


class MonitoringAlertRead(BaseModel):
    alert_id: str
    architecture_id: str
    subscription_id: str | None = None
    incident_id: str | None = None
    title: str
    severity: str
    status: str
    source: str
    resource_id: str | None = None
    resource_name: str | None = None
    resource_type: str | None = None
    monitoring_state: str | None = None
    health_status: str | None = None
    message: str | None = None
    detected_at: str
    resolved_at: str | None = None


class MonitoringAlertSummaryRead(BaseModel):
    architecture_id: str
    source: str = "legacy_incident_engine"
    alert_count: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    open_count: int
    acknowledged_count: int
    resolved_count: int
    alerts: list[MonitoringAlertRead] = Field(default_factory=list)


class MonitoringIncidentDetailRead(MonitoringIncidentRead):
    description: str = ""
    affected_resource_ids: list[str] = Field(default_factory=list)
    source_alert_ids: list[str] = Field(default_factory=list)
    timeline: list[MonitoringTimelineEventRead] = Field(default_factory=list)
    alerts: list[MonitoringAlertRead] = Field(default_factory=list)
    resolved_at: str | None = None
    updated_at: str | None = None


class MonitoringIncidentStatusUpdate(BaseModel):
    status: str
    comment: str | None = None
    actor: str = "platform_operator"
