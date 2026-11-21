from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.architecture.models import ArchitectureResource, AzureResourceGroup, AzureSubscription
from app.domains.incidents import IncidentService
from app.domains.incidents.models import MonitoringAlert, MonitoringIncident

from .schemas import (
    ArchitectureMonitoringSummaryRead,
    MonitoringAlertRead,
    MonitoringAlertSummaryRead,
    MonitoringIncidentDetailRead,
    MonitoringIncidentRead,
    MonitoringIncidentStatusUpdate,
    MonitoringIncidentSummaryRead,
    MonitoringTimelineEventRead,
    ResourceMonitoringRead,
)


class MonitoringAlertIncidentWorkflow:
    """Sync monitoring signals into reusable alert/incident lifecycle records."""

    def __init__(self, *, incident_service: IncidentService | None = None) -> None:
        self._incident_service = incident_service or IncidentService()

    async def sync_from_monitoring(
        self,
        *,
        architecture_id: UUID,
        monitoring_summary: ArchitectureMonitoringSummaryRead,
        resources: list[ArchitectureResource],
        resource_groups: list[AzureResourceGroup],
        subscriptions: list[AzureSubscription],
        selected_subscription_id: UUID | None,
        db: AsyncSession,
    ) -> MonitoringIncidentSummaryRead:
        resource_by_id = {str(item.id): item for item in resources}
        group_subscription_by_id = {
            item.id: item.subscription_id
            for item in resource_groups
            if item.subscription_id is not None
        }

        alert_query = select(MonitoringAlert).where(MonitoringAlert.architecture_id == architecture_id)
        if selected_subscription_id is not None:
            alert_query = alert_query.where(MonitoringAlert.subscription_id == selected_subscription_id)
        existing_rows = await db.execute(alert_query)
        existing_alerts = list(existing_rows.scalars().all())

        alert_by_fingerprint = {
            item.fingerprint: item
            for item in existing_alerts
            if item.status in {"open", "acknowledged", "investigating"}
        }

        active_fingerprints: set[str] = set()

        for signal in monitoring_summary.resources:
            severity = self._severity_from_signal(signal)
            if not severity:
                continue

            fingerprint = self._fingerprint(signal)
            active_fingerprints.add(fingerprint)

            resource = resource_by_id.get(signal.resource_id)
            subscription_id = self._resolve_subscription_id(
                resource=resource,
                group_subscription_by_id=group_subscription_by_id,
                subscriptions=subscriptions,
                selected_subscription_id=selected_subscription_id,
            )

            alert = alert_by_fingerprint.get(fingerprint)
            if not alert:
                alert = MonitoringAlert(
                    architecture_id=architecture_id,
                    resource_id=resource.id if resource else None,
                    subscription_id=subscription_id,
                    title=f"{signal.resource_name} ({signal.resource_type}) {signal.state}",
                    severity=severity,
                    status="open",
                    source="monitoring_signal",
                    signal_state=signal.state,
                    health_status=signal.health_status,
                    resource_name=signal.resource_name,
                    resource_type=signal.resource_type,
                    message=signal.message,
                    fingerprint=fingerprint,
                    details={"source": signal.source, "live": signal.live},
                )
                db.add(alert)
                await db.flush()

            if alert.status == "resolved":
                alert.status = "open"
                alert.resolved_at = None

            if not alert.incident_id:
                created = self._incident_service.auto_create_from_alert(
                    alert_id=str(alert.id),
                    alert_title=alert.title,
                    alert_severity=alert.severity,
                    resource_id=signal.resource_id,
                    alert_details={
                        "monitoring_state": signal.state,
                        "health_status": signal.health_status,
                        "message": signal.message,
                    },
                )
                if created.get("success"):
                    payload = created.get("data") or {}
                    incident = MonitoringIncident(
                        architecture_id=architecture_id,
                        title=str(payload.get("title") or f"Alert: {alert.title}"),
                        description=str(payload.get("description") or ""),
                        severity=str(payload.get("severity") or alert.severity),
                        status=str(payload.get("status") or "open"),
                        owner_id=payload.get("owner_id"),
                        timeline=list(payload.get("timeline") or []),
                        affected_resource_ids=list(payload.get("resources") or []),
                        source_alert_ids=list(payload.get("alerts") or []),
                        metadata_json={
                            "security_findings": list(payload.get("security_findings") or []),
                            "compliance_violations": list(payload.get("compliance_violations") or []),
                        },
                    )
                    db.add(incident)
                    await db.flush()
                    alert.incident_id = incident.id

        now = datetime.now(timezone.utc)
        for alert in existing_alerts:
            if alert.status in {"open", "acknowledged", "investigating"} and alert.fingerprint not in active_fingerprints:
                alert.status = "resolved"
                alert.resolved_at = now
                if alert.incident_id:
                    incident = await db.get(MonitoringIncident, alert.incident_id)
                    if incident and incident.status not in {"resolved", "closed"}:
                        update = self._incident_service.update_status(
                            incident_id=str(incident.id),
                            new_status="resolved",
                            comment="Auto-resolved because triggering monitoring signal is no longer active.",
                            actor="monitoring_system",
                        )
                        if update.get("success"):
                            incident.status = "resolved"
                            incident.resolved_at = now
                            incident.timeline = list(incident.timeline or []) + [update["timeline_event"]]

        await db.commit()

        return await self.build_incident_summary(
            architecture_id=architecture_id,
            selected_subscription_id=selected_subscription_id,
            db=db,
        )

    async def build_alert_summary(
        self,
        *,
        architecture_id: UUID,
        selected_subscription_id: UUID | None,
        db: AsyncSession,
    ) -> MonitoringAlertSummaryRead:
        query = (
            select(MonitoringAlert)
            .where(MonitoringAlert.architecture_id == architecture_id)
            .order_by(MonitoringAlert.detected_at.desc())
        )
        if selected_subscription_id is not None:
            query = query.where(MonitoringAlert.subscription_id == selected_subscription_id)
        rows = await db.execute(query)
        alerts = list(rows.scalars().all())
        payload = [self._to_alert_read(item) for item in alerts]
        return MonitoringAlertSummaryRead(
            architecture_id=str(architecture_id),
            alert_count=len(payload),
            critical_count=sum(1 for item in payload if item.severity == "critical"),
            high_count=sum(1 for item in payload if item.severity == "high"),
            medium_count=sum(1 for item in payload if item.severity == "medium"),
            low_count=sum(1 for item in payload if item.severity == "low"),
            open_count=sum(1 for item in payload if item.status == "open"),
            acknowledged_count=sum(1 for item in payload if item.status == "acknowledged"),
            resolved_count=sum(1 for item in payload if item.status == "resolved"),
            alerts=payload,
        )

    async def build_incident_summary(
        self,
        *,
        architecture_id: UUID,
        selected_subscription_id: UUID | None,
        db: AsyncSession,
    ) -> MonitoringIncidentSummaryRead:
        query = (
            select(MonitoringIncident)
            .where(MonitoringIncident.architecture_id == architecture_id)
            .order_by(MonitoringIncident.created_at.desc())
        )
        rows = await db.execute(query)
        incidents = list(rows.scalars().all())

        if selected_subscription_id is not None:
            link_rows = await db.execute(
                select(MonitoringAlert.incident_id)
                .where(MonitoringAlert.architecture_id == architecture_id)
                .where(MonitoringAlert.subscription_id == selected_subscription_id)
                .where(MonitoringAlert.incident_id.is_not(None))
            )
            allowed_incident_ids = {
                item[0]
                for item in link_rows.all()
                if item[0] is not None
            }
            incidents = [item for item in incidents if item.id in allowed_incident_ids]

        payload = [self._to_incident_read(item) for item in incidents]

        return MonitoringIncidentSummaryRead(
            architecture_id=str(architecture_id),
            incident_count=len(payload),
            critical_count=sum(1 for item in payload if item.severity == "critical"),
            high_count=sum(1 for item in payload if item.severity == "high"),
            medium_count=sum(1 for item in payload if item.severity == "medium"),
            low_count=sum(1 for item in payload if item.severity == "low"),
            incidents=payload,
        )

    async def list_incidents(
        self,
        *,
        architecture_id: UUID,
        selected_subscription_id: UUID | None,
        db: AsyncSession,
    ) -> list[MonitoringIncidentRead]:
        summary = await self.build_incident_summary(
            architecture_id=architecture_id,
            selected_subscription_id=selected_subscription_id,
            db=db,
        )
        return summary.incidents

    async def get_incident_detail(self, *, architecture_id: UUID, incident_id: UUID, db: AsyncSession) -> MonitoringIncidentDetailRead | None:
        incident = await db.get(MonitoringIncident, incident_id)
        if not incident or incident.architecture_id != architecture_id:
            return None

        alerts_rows = await db.execute(
            select(MonitoringAlert)
            .where(MonitoringAlert.architecture_id == architecture_id)
            .where(MonitoringAlert.incident_id == incident_id)
            .order_by(MonitoringAlert.detected_at.desc())
        )
        linked_alerts = [self._to_alert_read(item) for item in alerts_rows.scalars().all()]

        return MonitoringIncidentDetailRead(
            **self._to_incident_read(incident).model_dump(),
            description=incident.description,
            affected_resource_ids=list(incident.affected_resource_ids or []),
            source_alert_ids=list(incident.source_alert_ids or []),
            timeline=[MonitoringTimelineEventRead(**item) for item in (incident.timeline or []) if isinstance(item, dict)],
            alerts=linked_alerts,
            resolved_at=incident.resolved_at.isoformat() if incident.resolved_at else None,
            updated_at=incident.updated_at.isoformat() if incident.updated_at else None,
        )

    async def update_incident_status(
        self,
        *,
        architecture_id: UUID,
        incident_id: UUID,
        payload: MonitoringIncidentStatusUpdate,
        db: AsyncSession,
    ) -> MonitoringIncidentDetailRead | None:
        incident = await db.get(MonitoringIncident, incident_id)
        if not incident or incident.architecture_id != architecture_id:
            return None

        status = payload.status.lower().strip()
        mapped = "investigating" if status == "acknowledged" else status

        update = self._incident_service.update_status(
            incident_id=str(incident.id),
            new_status=mapped,
            comment=payload.comment,
            actor=payload.actor,
        )
        if not update.get("success"):
            return None

        incident.status = status
        if status == "resolved":
            incident.resolved_at = datetime.now(timezone.utc)
        incident.timeline = list(incident.timeline or []) + [update["timeline_event"]]

        alert_rows = await db.execute(
            select(MonitoringAlert)
            .where(MonitoringAlert.architecture_id == architecture_id)
            .where(MonitoringAlert.incident_id == incident_id)
        )
        alerts = list(alert_rows.scalars().all())
        for alert in alerts:
            if status in {"acknowledged", "resolved", "open"}:
                alert.status = status
                if status == "resolved":
                    alert.resolved_at = datetime.now(timezone.utc)
                elif status == "open":
                    alert.resolved_at = None

        await db.commit()
        await db.refresh(incident)
        return await self.get_incident_detail(architecture_id=architecture_id, incident_id=incident_id, db=db)

    def _fingerprint(self, signal: ResourceMonitoringRead) -> str:
        return f"{signal.resource_id}:{signal.state}:{signal.health_status or 'n/a'}"

    def _resolve_subscription_id(
        self,
        *,
        resource: ArchitectureResource | None,
        group_subscription_by_id: dict[UUID, UUID],
        subscriptions: list[AzureSubscription],
        selected_subscription_id: UUID | None,
    ) -> UUID | None:
        known_subscription_ids = {item.id for item in subscriptions}
        by_external_id = {
            str(item.subscription_id or "").strip().lower(): item.id
            for item in subscriptions
            if str(item.subscription_id or "").strip()
        }

        if selected_subscription_id in known_subscription_ids:
            return selected_subscription_id

        if not resource:
            if len(subscriptions) == 1:
                return subscriptions[0].id
            return None

        if resource.resource_group_id and resource.resource_group_id in group_subscription_by_id:
            return group_subscription_by_id[resource.resource_group_id]

        props = resource.properties if isinstance(resource.properties, dict) else {}

        db_sub = props.get("subscription_id")
        if db_sub:
            try:
                parsed = UUID(str(db_sub))
                if parsed in known_subscription_ids:
                    return parsed
            except ValueError:
                pass

        external_sub = str(props.get("azure_subscription_id") or "").strip().lower()
        if external_sub and external_sub in by_external_id:
            return by_external_id[external_sub]

        sub = props.get("subscription_id")
        if not sub:
            if len(subscriptions) == 1:
                return subscriptions[0].id
            return None
        try:
            parsed = UUID(str(sub))
            if parsed in known_subscription_ids:
                return parsed
            return None
        except ValueError:
            if len(subscriptions) == 1:
                return subscriptions[0].id
            return None

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

    def _to_alert_read(self, alert: MonitoringAlert) -> MonitoringAlertRead:
        return MonitoringAlertRead(
            alert_id=str(alert.id),
            architecture_id=str(alert.architecture_id),
            subscription_id=str(alert.subscription_id) if alert.subscription_id else None,
            incident_id=str(alert.incident_id) if alert.incident_id else None,
            title=alert.title,
            severity=alert.severity,
            status=alert.status,
            source=alert.source,
            resource_id=str(alert.resource_id) if alert.resource_id else None,
            resource_name=alert.resource_name,
            resource_type=alert.resource_type,
            monitoring_state=alert.signal_state,
            health_status=alert.health_status,
            message=alert.message,
            detected_at=alert.detected_at.isoformat() if alert.detected_at else "",
            resolved_at=alert.resolved_at.isoformat() if alert.resolved_at else None,
        )

    def _to_incident_read(self, incident: MonitoringIncident) -> MonitoringIncidentRead:
        primary_resource = (incident.affected_resource_ids or [None])[0]
        return MonitoringIncidentRead(
            incident_id=str(incident.id),
            title=incident.title,
            severity=incident.severity,
            status=incident.status,
            resource_id=str(primary_resource) if primary_resource else None,
            resource_name=None,
            resource_type=None,
            monitoring_state=None,
            health_status=None,
            message=incident.description,
            created_at=incident.created_at.isoformat() if incident.created_at else "",
        )
