from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.incidents import IncidentService
from app.domains.settings.service import SettingsService

from .azure_monitor_adapter import AzureMonitorAdapter
from .connection_schemas import (
    AzureSubscriptionCandidateRead,
    MonitoringAlertRead,
    MonitoringIncidentRead,
    MonitoringResourceRead,
    MonitoringSubscriptionCreate,
    MonitoringSubscriptionRead,
    MonitoringUnusedAnalysisRead,
)
from .models import MonitoringSubscription
from .unused_resource_detector import IdleResourceDetector

try:
    from azure.identity import ClientSecretCredential
except Exception:  # pragma: no cover
    ClientSecretCredential = None  # type: ignore[assignment]


ARM = "https://management.azure.com"


class MonitoringConnectionService:
    def __init__(self, settings: SettingsService | None = None):
        self.settings = settings or SettingsService()
        self.interval = max(60, int(os.getenv("MONITORING_REFRESH_INTERVAL_SECONDS", "300")))

    async def discover_subscriptions(self, db: AsyncSession) -> list[AzureSubscriptionCandidateRead]:
        token, credentials = await self._token(db)
        if not token:
            raise ValueError(credentials.get("message") or "Azure service principal is not configured in Settings.")
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{ARM}/subscriptions", params={"api-version": "2020-01-01"}, headers=self._headers(token))
        self._raise_for_azure(response, "listing subscriptions")
        return [AzureSubscriptionCandidateRead(
            subscription_id=str(item.get("subscriptionId")),
            name=str(item.get("displayName") or item.get("subscriptionId")),
            tenant_id=credentials.get("tenant_id") or None,
            state=str(item.get("state") or "") or None,
        ) for item in (response.json() or {}).get("value", []) if item.get("subscriptionId")]

    async def list_saved(self, db: AsyncSession) -> list[MonitoringSubscriptionRead]:
        result = await db.execute(select(MonitoringSubscription).order_by(MonitoringSubscription.name.asc()))
        return [self._read(item) for item in result.scalars().all()]

    async def save_subscription(self, db: AsyncSession, payload: MonitoringSubscriptionCreate) -> MonitoringSubscriptionRead:
        row = await db.scalar(select(MonitoringSubscription).where(MonitoringSubscription.subscription_id == payload.subscription_id))
        if row is None:
            row = MonitoringSubscription(subscription_id=payload.subscription_id, name=payload.name, tenant_id=payload.tenant_id, service_principal_provider="azure_credentials", summary={}, resources=[], metrics={}, alerts=[], incidents=[], unused_analysis={})
            db.add(row)
        else:
            row.name = payload.name
            row.tenant_id = payload.tenant_id or row.tenant_id
        await db.commit()
        await db.refresh(row)
        return await self.refresh_subscription(db, row.id)

    async def delete_subscription(self, db: AsyncSession, subscription_id: UUID) -> None:
        await db.execute(delete(MonitoringSubscription).where(MonitoringSubscription.id == subscription_id))
        await db.commit()

    async def refresh_subscription(self, db: AsyncSession, subscription_id: UUID) -> MonitoringSubscriptionRead:
        row = await db.scalar(select(MonitoringSubscription).where(MonitoringSubscription.id == subscription_id))
        if row is None:
            raise LookupError("Monitoring subscription not found")
        checked_at = datetime.now(timezone.utc)
        token, credentials = await self._token(db)
        if not token:
            self._set_error(row, credentials.get("state", "not_configured"), credentials.get("message"), checked_at)
            await db.commit()
            return self._read(row)
        try:
            resources = await self._list_resources(row.subscription_id, token)
            await self._update_health(resources, token)
            metrics, metrics_state = await self._collect_metrics(resources, token, hours=24)
            alerts, alerts_state = await self._list_alerts(row.subscription_id, token)
            resource_names = {item["azure_resource_id"].lower(): item["name"] for item in resources}
            for alert in alerts:
                target = str(alert.get("resource_id") or "").lower()
                alert["resource_name"] = resource_names.get(target)
            incidents = self._sync_incidents(alerts, row.incidents if isinstance(row.incidents, list) else [])
            unused = await self._analyze_unused(resources, token)
            row.connection_state = "connected"
            row.last_error = None
            row.refresh_state = "available"
            row.refresh_error = None
            row.last_successful_at = checked_at
            row.summary = self._summary(resources)
            row.resources = resources
            row.metrics = metrics
            row.metrics_state = metrics_state
            row.alerts = alerts
            row.alerts_state = alerts_state
            row.incidents = incidents
            row.incidents_state = "available"
            row.unused_analysis = unused
            row.last_checked_at = checked_at
            row.tenant_id = row.tenant_id or credentials.get("tenant_id")
        except AzureRequestError as exc:
            self._set_error(row, exc.state, str(exc), checked_at)
        except Exception as exc:
            self._set_error(row, "provider_error", f"Azure monitoring refresh failed: {exc}", checked_at)
        await db.commit()
        await db.refresh(row)
        return self._read(row)

    async def get_metrics(self, db: AsyncSession, subscription_id: UUID, hours: int, interval: str) -> MonitoringSubscriptionRead:
        row = await db.scalar(select(MonitoringSubscription).where(MonitoringSubscription.id == subscription_id))
        if row is None:
            raise LookupError("Monitoring subscription not found")
        token, details = await self._token(db)
        if not token:
            row.metrics_state = details.get("state", "not_configured")
            await db.commit()
            return self._read(row)
        resources = row.resources if isinstance(row.resources, list) else []
        metrics, state = await self._collect_metrics(resources, token, hours=max(1, min(hours, 24 * 30)), interval=interval)
        row.resources = resources
        row.metrics = metrics
        row.metrics_state = state
        await db.commit()
        await db.refresh(row)
        return self._read(row)

    async def update_incident_status(self, db: AsyncSession, subscription_id: UUID, incident_id: str, status: str, comment: str | None, actor: str) -> MonitoringSubscriptionRead:
        row = await db.scalar(select(MonitoringSubscription).where(MonitoringSubscription.id == subscription_id))
        if row is None:
            raise LookupError("Monitoring subscription not found")
        normalized = status.strip().lower()
        if normalized not in {"open", "acknowledged", "resolved"}:
            raise ValueError("Incident status must be Open, Acknowledged, or Resolved.")
        incidents = row.incidents if isinstance(row.incidents, list) else []
        incident = next((item for item in incidents if str(item.get("id")) == incident_id), None)
        if incident is None:
            raise LookupError("Incident not found")
        now = datetime.now(timezone.utc).isoformat()
        incident["status"] = normalized
        incident["updated_at"] = now
        incident["resolved_at"] = now if normalized == "resolved" else None
        incident.setdefault("timeline", []).append({"event_type": "status_changed", "timestamp": now, "actor": actor or "platform_operator", "details": comment or f"Incident status set to {normalized}."})
        row.incidents = incidents
        await db.commit()
        await db.refresh(row)
        return self._read(row)

    async def refresh_all(self, db: AsyncSession) -> None:
        result = await db.execute(select(MonitoringSubscription.id))
        for subscription_id in result.scalars().all():
            try:
                await self.refresh_subscription(db, subscription_id)
            except Exception:
                await db.rollback()

    async def _token(self, db: AsyncSession) -> tuple[str | None, dict[str, str]]:
        credentials = await self.settings.get_azure_credentials_for_backend(db=db)
        if ClientSecretCredential is None:
            return None, {"state": "not_configured", "message": "azure-identity is not installed."}
        if not all(credentials.get(key) for key in ("tenant_id", "client_id", "client_secret")):
            return None, {"state": "not_configured", "message": "Configure the Azure service principal in Settings."}
        try:
            credential = ClientSecretCredential(tenant_id=credentials["tenant_id"], client_id=credentials["client_id"], client_secret=credentials["client_secret"])
            access = await asyncio.to_thread(credential.get_token, "https://management.azure.com/.default")
            return access.token, credentials
        except Exception as exc:
            return None, {"state": "authentication_failure", "message": f"Azure authentication failed: {exc}"}

    async def _list_resources(self, subscription_id: str, token: str) -> list[dict[str, Any]]:
        headers = self._headers(token)
        async with httpx.AsyncClient(timeout=30.0) as client:
            groups = await self._paged(client, f"{ARM}/subscriptions/{subscription_id}/resourcegroups", "2021-04-01", headers)
            raw = await self._paged(client, f"{ARM}/subscriptions/{subscription_id}/resources", "2021-04-01", headers)
        locations = {str(item.get("name")): item.get("location") for item in groups}
        resources = []
        for item in raw:
            resource_id = str(item.get("id") or "")
            if not resource_id or not item.get("name"):
                continue
            group = self._resource_group(resource_id)
            resources.append({"id": resource_id, "name": str(item["name"]), "resource_type": str(item.get("type") or "unknown"), "resource_group": group, "region": str(item.get("location") or locations.get(group) or "") or None, "status": "unknown", "status_source": None, "last_checked": None, "azure_resource_id": resource_id, "metrics": [], "metric_state": "not_checked", "metric_message": None})
        return resources

    async def _update_health(self, resources: list[dict[str, Any]], token: str) -> None:
        semaphore = asyncio.Semaphore(8)
        async def check(resource: dict[str, Any]) -> None:
            async with semaphore:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        response = await client.get(f"{ARM}{resource['azure_resource_id']}/providers/Microsoft.ResourceHealth/availabilityStatuses/current", params={"api-version": "2022-10-01"}, headers=self._headers(token))
                    if response.status_code >= 400:
                        return
                    state = str(((response.json() or {}).get("properties") or {}).get("availabilityState") or "").lower()
                    if state in {"available", "degraded", "unavailable", "unknown"}:
                        resource["status"] = "healthy" if state == "available" else state
                        resource["status_source"] = "Azure Resource Health"
                        resource["last_checked"] = datetime.now(timezone.utc).isoformat()
                except Exception:
                    return
        await asyncio.gather(*(check(item) for item in resources))

    async def _collect_metrics(self, resources: list[dict[str, Any]], token: str, hours: int, interval: str = "PT1H") -> tuple[dict[str, list[dict]], str]:
        adapter = AzureMonitorAdapter()
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)
        semaphore = asyncio.Semaphore(8)
        states = []
        metrics: dict[str, list[dict]] = {}
        async def collect(resource: dict[str, Any]) -> None:
            async with semaphore:
                result = await adapter.get_resource_monitoring(resource_type=self._monitorai_type(resource["resource_type"]), azure_resource_id=resource["azure_resource_id"], start_time=start, end_time=end, interval=interval)
            resource["metrics"] = result.get("metrics") or []
            resource["metric_state"] = str(result.get("state") or "no_data")
            resource["metric_message"] = result.get("message")
            metrics[resource["azure_resource_id"]] = resource["metrics"]
            states.append(resource["metric_state"])
        await asyncio.gather(*(collect(item) for item in resources))
        if not resources:
            return metrics, "no_data"
        if any(state == "live" for state in states):
            return metrics, "available"
        if any(state == "permission_failure" for state in states):
            return metrics, "permission_failure"
        if any(state == "authentication_failure" for state in states):
            return metrics, "authentication_failure"
        if all(state == "unsupported" for state in states):
            return metrics, "unsupported"
        return metrics, "no_data"

    async def _list_alerts(self, subscription_id: str, token: str) -> tuple[list[dict[str, Any]], str]:
        url = f"{ARM}/subscriptions/{subscription_id}/providers/Microsoft.AlertsManagement/alerts"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params={"api-version": "2019-05-05-preview"}, headers=self._headers(token))
            self._raise_for_azure(response, "listing alerts")
        except AzureRequestError as exc:
            return [], exc.state
        except Exception:
            return [], "provider_error"
        alerts = []
        for item in (response.json() or {}).get("value") or []:
            properties = item.get("properties") or {}
            essentials = properties.get("essentials") or {}
            targets = essentials.get("targetResourceIds") or []
            alerts.append({"id": str(item.get("id") or item.get("name") or ""), "name": str(essentials.get("alertRule") or item.get("name") or "Azure alert"), "severity": str(essentials.get("severity") or "unknown").lower(), "status": "open" if str(essentials.get("monitorCondition") or "").lower() == "fired" else "resolved", "resource_id": str(targets[0]) if targets else None, "resource_name": None, "timestamp": essentials.get("firedDateTime") or essentials.get("lastModifiedDateTime"), "condition": str(essentials.get("monitorCondition") or "") or None, "fired_time": essentials.get("firedDateTime"), "last_updated": essentials.get("lastModifiedDateTime"), "description": essentials.get("description") or (properties.get("context") or {}).get("description"), "source": "Azure Monitor Alerts"})
        return [item for item in alerts if item["id"]], "available"

    async def _analyze_unused(self, resources: list[dict[str, Any]], token: str) -> dict[str, Any]:
        checked = datetime.now(timezone.utc).isoformat()
        if not resources:
            return {"state": "no_data", "message": "No Azure resources were available for analysis.", "checked_at": checked, "total_checked": 0, "total_unused": 0, "estimated_monthly_waste": None, "findings": []}
        detector = IdleResourceDetector(token, days=7)
        inputs = [{"azure_resource_id": item["azure_resource_id"], "resource_name": item["name"], "resource_type": item["resource_type"], "location": item.get("region") or "", "resource_group": item.get("resource_group") or "", "subscription_id": ""} for item in resources]
        results = await asyncio.to_thread(detector.detect_batch, inputs)
        findings = [{**item, **results[item["azure_resource_id"]]} for item in inputs if (results.get(item["azure_resource_id"]) or {}).get("is_idle")]
        has_metric_data = any(item.get("metrics") for item in resources)
        state = "evaluated" if findings or has_metric_data else "no_data"
        message = "Azure utilization and configuration signals evaluated." if state == "evaluated" else "Insufficient Azure utilization data was returned for this analysis window."
        return {"state": state, "message": message, "checked_at": checked, "total_checked": len(inputs), "total_unused": len(findings), "estimated_monthly_waste": sum(float(item.get("monthly_cost_estimate") or 0) for item in findings) if findings else None, "findings": findings}

    @staticmethod
    def _sync_incidents(alerts: list[dict[str, Any]], previous: list[dict[str, Any]]) -> list[dict[str, Any]]:
        previous_by_alert = {alert_id: incident for incident in previous for alert_id in incident.get("alert_ids", [])}
        incidents = []
        service = IncidentService()
        now = datetime.now(timezone.utc).isoformat()
        seen_alert_ids = set()
        for alert in alerts:
            seen_alert_ids.add(alert["id"])
            incident = previous_by_alert.get(alert["id"])
            if alert["status"] == "open":
                if incident is None:
                    generated = service.auto_create_from_alert(alert_id=alert["id"], alert_title=alert["name"], alert_severity=alert["severity"], resource_id=alert.get("resource_id"), alert_details={"source": "Azure Monitor Alerts"})
                    data = generated.get("data") or {}
                    incident = {"id": hashlib.sha1(alert["id"].encode()).hexdigest(), "title": data.get("title") or f"Alert: {alert['name']}", "severity": data.get("severity") or alert["severity"], "status": "open", "description": data.get("description") or "Incident created from Azure Monitor alert.", "created_at": now, "updated_at": now, "resolved_at": None, "resource_ids": [alert["resource_id"]] if alert.get("resource_id") else [], "alert_ids": [alert["id"]], "timeline": [{"event_type": "created", "timestamp": now, "actor": "monitoring_system", "details": "Incident created from Azure Monitor alert."}]}
                incidents.append(incident)
            elif incident is not None:
                incident["status"] = "resolved"
                incident["resolved_at"] = incident.get("resolved_at") or now
                incident["updated_at"] = now
                incidents.append(incident)
        for incident in previous:
            if not any(alert_id in seen_alert_ids for alert_id in incident.get("alert_ids", [])):
                incidents.append(incident)
        return incidents

    @staticmethod
    def _monitorai_type(resource_type: str) -> str:
        value = str(resource_type or "").lower()
        return {"microsoft.compute/virtualmachines": "vm", "microsoft.web/sites": "appservice", "microsoft.web/serverfarms": "appserviceplan", "microsoft.storage/storageaccounts": "storage", "microsoft.sql/servers/databases": "sql", "microsoft.sql/servers": "sqlserver", "microsoft.containerservice/managedclusters": "aks", "microsoft.keyvault/vaults": "keyvault", "microsoft.network/virtualnetworks": "vnet"}.get(value, value)

    @staticmethod
    def _summary(resources: list[dict[str, Any]]) -> dict[str, int]:
        return {"total_resources": len(resources), "healthy_count": sum(item["status"] == "healthy" for item in resources), "warning_count": sum(item["status"] in {"degraded", "warning"} for item in resources), "critical_count": sum(item["status"] == "unavailable" for item in resources), "unknown_count": sum(item["status"] == "unknown" for item in resources)}

    @staticmethod
    def _set_error(row: MonitoringSubscription, state: str, message: str | None, checked_at: datetime) -> None:
        # Keep the last known-good snapshot. A failed refresh is not an empty Azure inventory.
        if row.resources or row.last_successful_at:
            row.connection_state = "connected"
        else:
            row.connection_state = state
        row.last_error = message
        row.refresh_state = state
        row.refresh_error = message
        row.last_checked_at = checked_at

    @staticmethod
    def _read(row: MonitoringSubscription) -> MonitoringSubscriptionRead:
        summary = row.summary if isinstance(row.summary, dict) else {}
        resources = row.resources if isinstance(row.resources, list) else []
        return MonitoringSubscriptionRead(id=str(row.id), subscription_id=row.subscription_id, name=row.name, tenant_id=row.tenant_id, service_principal_provider=row.service_principal_provider, connection_status=row.connection_state, connection_message=row.last_error, total_resources=int(summary.get("total_resources", len(resources))), healthy_count=int(summary.get("healthy_count", 0)), warning_count=int(summary.get("warning_count", 0)), critical_count=int(summary.get("critical_count", 0)), unknown_count=int(summary.get("unknown_count", 0)), last_checked_at=row.last_checked_at.isoformat() if row.last_checked_at else None, resources=[MonitoringResourceRead(**item) for item in resources], metrics=row.metrics if isinstance(row.metrics, dict) else {}, alerts=[MonitoringAlertRead(**item) for item in (row.alerts if isinstance(row.alerts, list) else [])], incidents=[MonitoringIncidentRead(**item) for item in (row.incidents if isinstance(row.incidents, list) else [])], unused_analysis=MonitoringUnusedAnalysisRead(**(row.unused_analysis if isinstance(row.unused_analysis, dict) else {})), metrics_state=row.metrics_state, alerts_state=row.alerts_state, incidents_state=row.incidents_state, refresh_state=row.refresh_state, refresh_error=row.refresh_error, last_successful_at=row.last_successful_at.isoformat() if row.last_successful_at else None)

    @staticmethod
    def _headers(token: str) -> dict[str, str]: return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    @staticmethod
    def _resource_group(resource_id: str) -> str | None:
        marker = "/resourcegroups/"; lower = resource_id.lower()
        return resource_id[lower.index(marker) + len(marker):].split("/", 1)[0] if marker in lower else None
    async def _paged(self, client: httpx.AsyncClient, url: str, api_version: str, headers: dict[str, str]) -> list[dict[str, Any]]:
        items = []; next_url: str | None = url; params: dict[str, str] | None = {"api-version": api_version}
        while next_url:
            response = await client.get(next_url, params=params, headers=headers); self._raise_for_azure(response, "listing resources"); payload = response.json() or {}; items.extend(item for item in payload.get("value", []) if isinstance(item, dict)); next_url = payload.get("nextLink"); params = None
        return items
    @staticmethod
    def _raise_for_azure(response: httpx.Response, operation: str) -> None:
        if response.status_code < 400: return
        state = {401: "authentication_failure", 403: "permission_failure"}.get(response.status_code, "provider_error")
        try: message = ((response.json() or {}).get("error") or {}).get("message")
        except Exception: message = None
        raise AzureRequestError(state, str(message or f"Azure error while {operation} ({response.status_code})."))


class AzureRequestError(RuntimeError):
    def __init__(self, state: str, message: str): super().__init__(message); self.state = state
