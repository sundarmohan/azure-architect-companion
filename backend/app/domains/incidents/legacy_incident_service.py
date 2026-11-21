"""
Legacy incident engine reused from monitorai-main.

This module preserves the core business logic for incident creation,
severity mapping, and timeline/status metadata so V2.9 can reuse
proven incident orchestration without importing legacy UI.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class IncidentSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    CLOSED = "closed"


class IncidentService:
    """Legacy incident business logic adapter (stateless)."""

    def __init__(self, db_manager: Any | None = None) -> None:
        self.db = db_manager
        self.logger = logger

    def create_incident(
        self,
        title: str,
        description: str,
        severity: str,
        owner_id: str | None = None,
        resource_ids: list[str] | None = None,
        alert_ids: list[str] | None = None,
        security_finding_ids: list[str] | None = None,
        compliance_violation_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        try:
            if not title or not title.strip():
                raise ValueError("Incident title is required")

            if severity not in [s.value for s in IncidentSeverity]:
                severity = IncidentSeverity.MEDIUM.value

            incident_id = str(uuid.uuid4())
            now = datetime.utcnow()

            incident_data = {
                "id": incident_id,
                "title": title.strip(),
                "description": description.strip() if description else "",
                "severity": severity,
                "status": IncidentStatus.OPEN.value,
                "owner_id": owner_id,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "resolved_at": None,
                "timeline": [
                    {
                        "event_type": "created",
                        "timestamp": now.isoformat(),
                        "actor": "system",
                        "details": f"Incident created: {title}",
                    }
                ],
                "resources": resource_ids or [],
                "alerts": alert_ids or [],
                "security_findings": security_finding_ids or [],
                "compliance_violations": compliance_violation_ids or [],
                "rca_id": None,
                "remediation_plan": None,
            }

            self.logger.info("Created incident %s: %s", incident_id, title)
            return {"success": True, "incident_id": incident_id, "data": incident_data}

        except Exception as exc:
            self.logger.error("Error creating incident: %s", exc)
            return {"success": False, "error": str(exc)}

    def auto_create_from_alert(
        self,
        alert_id: str,
        alert_title: str,
        alert_severity: str,
        resource_id: str | None = None,
        alert_details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            severity_map = {
                "critical": IncidentSeverity.CRITICAL.value,
                "high": IncidentSeverity.HIGH.value,
                "medium": IncidentSeverity.MEDIUM.value,
                "low": IncidentSeverity.LOW.value,
                "warning": IncidentSeverity.MEDIUM.value,
                "info": IncidentSeverity.LOW.value,
            }

            incident_severity = severity_map.get(
                str(alert_severity or "").lower(),
                IncidentSeverity.MEDIUM.value,
            )

            title = f"Alert: {alert_title}"
            resource_ids = [resource_id] if resource_id else []

            return self.create_incident(
                title=title,
                description=f"Auto-created from alert {alert_id}. Details: {alert_details or ''}",
                severity=incident_severity,
                resource_ids=resource_ids,
                alert_ids=[alert_id],
            )

        except Exception as exc:
            self.logger.error("Error auto-creating incident from alert %s: %s", alert_id, exc)
            return {"success": False, "error": str(exc)}

    def update_status(
        self,
        incident_id: str,
        new_status: str,
        comment: str | None = None,
        actor: str = "system",
    ) -> dict[str, Any]:
        try:
            normalized = str(new_status or "").lower().strip()
            if normalized not in [s.value for s in IncidentStatus]:
                raise ValueError(f"Invalid incident status: {new_status}")

            now = datetime.utcnow().isoformat()
            event = {
                "event_type": "status_changed",
                "timestamp": now,
                "actor": actor,
                "details": comment or f"Incident status set to {normalized}",
            }

            return {
                "success": True,
                "incident_id": incident_id,
                "status": normalized,
                "resolved_at": now if normalized in {IncidentStatus.RESOLVED.value, IncidentStatus.CLOSED.value} else None,
                "timeline_event": event,
            }
        except Exception as exc:
            self.logger.error("Error updating incident %s status: %s", incident_id, exc)
            return {"success": False, "error": str(exc)}
