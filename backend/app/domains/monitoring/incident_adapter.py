from __future__ import annotations

from app.domains.incidents import IncidentService

from .schemas import (
    ArchitectureMonitoringSummaryRead,
    MonitoringIncidentRead,
    MonitoringIncidentSummaryRead,
    ResourceMonitoringRead,
)


class MonitoringIncidentAdapter:
    """Bridge monitoring states into reusable legacy incident engine calls."""

    def __init__(self, *, incident_service: IncidentService | None = None) -> None:
        self._incident_service = incident_service or IncidentService()

    def build_summary(
        self,
        *,
        architecture_id: str,
        monitoring_summary: ArchitectureMonitoringSummaryRead,
    ) -> MonitoringIncidentSummaryRead:
        incidents: list[MonitoringIncidentRead] = []
        seen: set[tuple[str, str, str]] = set()

        for signal in monitoring_summary.resources:
            incident = self._incident_from_signal(signal)
            if not incident:
                continue

            key = (
                incident.resource_id or "",
                incident.monitoring_state or "",
                incident.severity,
            )
            if key in seen:
                continue
            seen.add(key)
            incidents.append(incident)

        return MonitoringIncidentSummaryRead(
            architecture_id=architecture_id,
            incident_count=len(incidents),
            critical_count=sum(1 for item in incidents if item.severity == "critical"),
            high_count=sum(1 for item in incidents if item.severity == "high"),
            medium_count=sum(1 for item in incidents if item.severity == "medium"),
            low_count=sum(1 for item in incidents if item.severity == "low"),
            incidents=incidents,
        )

    def _incident_from_signal(self, signal: ResourceMonitoringRead) -> MonitoringIncidentRead | None:
        severity = self._severity_from_signal(signal)
        if not severity:
            return None

        alert_id = f"monitoring:{signal.resource_id}:{signal.state}:{signal.health_status or 'n/a'}"
        alert_title = f"{signal.resource_name} ({signal.resource_type}) {signal.state}"

        created = self._incident_service.auto_create_from_alert(
            alert_id=alert_id,
            alert_title=alert_title,
            alert_severity=severity,
            resource_id=signal.resource_id,
            alert_details={
                "monitoring_state": signal.state,
                "health_status": signal.health_status,
                "message": signal.message,
            },
        )
        if not created.get("success"):
            return None

        data = created.get("data") or {}
        return MonitoringIncidentRead(
            incident_id=str(data.get("id") or created.get("incident_id") or ""),
            title=str(data.get("title") or alert_title),
            severity=str(data.get("severity") or severity),
            status=str(data.get("status") or "open"),
            resource_id=signal.resource_id,
            resource_name=signal.resource_name,
            resource_type=signal.resource_type,
            monitoring_state=signal.state,
            health_status=signal.health_status,
            message=signal.message,
            created_at=str(data.get("created_at") or ""),
        )

    def _severity_from_signal(self, signal: ResourceMonitoringRead) -> str | None:
        state = (signal.state or "").lower()
        health = (signal.health_status or "").lower()

        if state in {"authentication_failure", "permission_failure", "azure_api_failure"}:
            return "high"
        if state == "not_configured":
            return "medium"
        if state == "no_data":
            return "low"
        if state == "live" and health in {"unavailable", "degraded", "unhealthy"}:
            return "critical"
        return None
