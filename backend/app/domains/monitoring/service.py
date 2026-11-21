from __future__ import annotations

import asyncio
import os
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from app.domains.architecture.catalog import CATALOG_BY_RESOURCE_TYPE
from app.domains.architecture.models import Architecture, ArchitectureResource, AzureResourceGroup, AzureSubscription

from .azure_monitor_adapter import AzureMonitorAdapter
from .schemas import (
    ArchitectureMonitoringSummaryRead,
    MonitoringMetricSeries,
    ResourceMonitoringRead,
    UnusedResourceFindingRead,
    UnusedResourceSummaryRead,
)
from .unused_resource_detector import IdleResourceDetector


class MonitoringService:
    def __init__(self, *, adapter: AzureMonitorAdapter | None = None) -> None:
        self._adapter = adapter or AzureMonitorAdapter()
        self._max_concurrency = max(1, int(os.getenv("MONITORING_MAX_CONCURRENCY", "8")))
        self._resource_timeout_seconds = max(1.0, float(os.getenv("MONITORING_RESOURCE_TIMEOUT_SECONDS", "12")))

    async def monitor_resource(
        self,
        *,
        architecture: Architecture,
        resource: ArchitectureResource,
        resource_groups: Sequence[AzureResourceGroup],
        subscriptions: Sequence[AzureSubscription],
        start_time: datetime,
        end_time: datetime,
        interval: str,
    ) -> ResourceMonitoringRead:
        azure_resource_id = self._azure_resource_id(resource)
        if not azure_resource_id:
            return ResourceMonitoringRead(
                architecture_id=str(architecture.id),
                resource_id=str(resource.id),
                resource_name=resource.name,
                resource_type=resource.resource_type,
                state="unsupported",
                live=False,
                message="Resource is not linked to a discovered Azure resource id",
            )

        result = await self._adapter.get_resource_monitoring(
            resource_type=resource.resource_type,
            azure_resource_id=azure_resource_id,
            start_time=start_time,
            end_time=end_time,
            interval=interval,
        )

        state = str(result.get("state") or "azure_api_failure")
        metrics = [MonitoringMetricSeries(**item) for item in (result.get("metrics") or []) if isinstance(item, dict)]
        live = state == "live"

        return ResourceMonitoringRead(
            architecture_id=str(architecture.id),
            resource_id=str(resource.id),
            resource_name=resource.name,
            resource_type=resource.resource_type,
            state=state,
            live=live,
            health_status=result.get("health_status"),
            metrics=metrics,
            message=result.get("message"),
        )

    async def monitor_architecture(
        self,
        *,
        architecture: Architecture,
        resources: Sequence[ArchitectureResource],
        resource_groups: Sequence[AzureResourceGroup],
        subscriptions: Sequence[AzureSubscription],
        start_time: datetime,
        end_time: datetime,
        interval: str,
    ) -> ArchitectureMonitoringSummaryRead:
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def collect(resource: ArchitectureResource) -> ResourceMonitoringRead:
            async with semaphore:
                try:
                    return await asyncio.wait_for(
                        self.monitor_resource(
                            architecture=architecture,
                            resource=resource,
                            resource_groups=resource_groups,
                            subscriptions=subscriptions,
                            start_time=start_time,
                            end_time=end_time,
                            interval=interval,
                        ),
                        timeout=self._resource_timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    return ResourceMonitoringRead(
                        architecture_id=str(architecture.id),
                        resource_id=str(resource.id),
                        resource_name=resource.name,
                        resource_type=resource.resource_type,
                        state="azure_api_failure",
                        live=False,
                        message="Resource monitoring timed out",
                    )
                except Exception as exc:
                    return ResourceMonitoringRead(
                        architecture_id=str(architecture.id),
                        resource_id=str(resource.id),
                        resource_name=resource.name,
                        resource_type=resource.resource_type,
                        state="azure_api_failure",
                        live=False,
                        message=f"Resource monitoring failed: {exc}",
                    )

        monitored = list(await asyncio.gather(*(collect(resource) for resource in resources)))

        live_resources = [item for item in monitored if item.state == "live"]
        no_data_count = sum(1 for item in monitored if item.state == "no_data")
        unsupported_count = sum(1 for item in monitored if item.state == "unsupported")
        error_count = sum(
            1
            for item in monitored
            if item.state in {"not_configured", "authentication_failure", "permission_failure", "azure_api_failure"}
        )

        healthy_count = 0
        warning_count = 0
        critical_count = 0

        for item in live_resources:
            health = (item.health_status or "").lower()
            if health in {"available", "healthy"}:
                healthy_count += 1
            elif health in {"degraded", "unavailable", "unhealthy"}:
                critical_count += 1
            elif health:
                warning_count += 1
            else:
                warning_count += 1

        if error_count > 0 and len(live_resources) == 0:
            state = "azure_api_failure"
        elif len(live_resources) > 0:
            state = "live"
        elif no_data_count > 0:
            state = "no_data"
        elif unsupported_count == len(monitored) and monitored:
            state = "unsupported"
        else:
            state = "no_data"

        return ArchitectureMonitoringSummaryRead(
            architecture_id=str(architecture.id),
            state=state,
            total_resources=len(resources),
            monitored_resources=len(monitored),
            live_resources=len(live_resources),
            healthy_count=healthy_count,
            warning_count=warning_count,
            critical_count=critical_count,
            no_data_count=no_data_count,
            unsupported_count=unsupported_count,
            error_count=error_count,
            resources=monitored,
        )

    async def detect_unused_resources(
        self,
        *,
        architecture: Architecture,
        resources: Sequence[ArchitectureResource],
        lookback_days: int,
        azure_connection_state: str,
        azure_connection_message: str | None,
    ) -> UnusedResourceSummaryRead:
        days = max(1, min(int(lookback_days or 7), 30))
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days)

        auth = self._adapter.get_access_token()
        state = str(auth.get("state") or "unavailable")
        message = str(auth.get("message") or "Azure monitoring authentication unavailable")
        token = auth.get("token")

        eligible_resources = [
            item
            for item in resources
            if self._azure_resource_id(item)
        ]

        if state != "configured" or not token:
            return UnusedResourceSummaryRead(
                architecture_id=str(architecture.id),
                state=state,
                lookback_days=days,
                analysis_start_time=start_time.isoformat(),
                analysis_end_time=end_time.isoformat(),
                total_checked=len(eligible_resources),
                total_unused=0,
                estimated_monthly_waste=0.0,
                azure_connection_state=azure_connection_state,
                azure_connection_message=azure_connection_message,
                message=message,
                unused_resources=[],
            )

        detector_input: list[dict[str, str]] = []
        for resource in eligible_resources:
            azure_resource_id = self._azure_resource_id(resource)
            if not azure_resource_id:
                continue

            detector_input.append(
                {
                    "resource_id": str(resource.id),
                    "resource_name": resource.name,
                    "resource_type": self._azure_resource_type(resource),
                    "location": str(resource.location or ""),
                    "resource_group": self._resource_group_name(azure_resource_id),
                    "subscription_id": self._subscription_id(azure_resource_id),
                    "azure_resource_id": azure_resource_id,
                }
            )

        detector = IdleResourceDetector(str(token), days=days)
        idle_map = await asyncio.to_thread(detector.detect_batch, detector_input)

        findings: list[UnusedResourceFindingRead] = []
        for resource in detector_input:
            idle = idle_map.get(resource["azure_resource_id"]) or {}
            if not idle.get("is_idle"):
                continue
            findings.append(
                UnusedResourceFindingRead(
                    resource_id=resource["resource_id"],
                    resource_name=resource["resource_name"],
                    resource_type=resource["resource_type"],
                    location=resource["location"],
                    resource_group=resource["resource_group"],
                    subscription_id=resource["subscription_id"],
                    idle_reason=str(idle.get("idle_reason") or "No recent activity detected"),
                    idle_signals=list(idle.get("idle_signals") or []),
                    confidence=str(idle.get("confidence") or "low"),
                    recommended_action=(str(idle.get("recommended_action") or "").strip() or None),
                    days_checked=int(idle.get("days_checked") or days),
                    monthly_cost_estimate=float(idle.get("monthly_cost_estimate") or 0.0),
                    portal_link=self._portal_link(resource["azure_resource_id"]),
                )
            )

        findings.sort(
            key=lambda item: (
                {"high": 0, "medium": 1, "low": 2}.get(item.confidence, 2),
                -item.monthly_cost_estimate,
            )
        )

        return UnusedResourceSummaryRead(
            architecture_id=str(architecture.id),
            state="evaluated",
            lookback_days=days,
            analysis_start_time=start_time.isoformat(),
            analysis_end_time=end_time.isoformat(),
            total_checked=len(detector_input),
            total_unused=len(findings),
            estimated_monthly_waste=round(sum(item.monthly_cost_estimate for item in findings), 2),
            azure_connection_state=azure_connection_state,
            azure_connection_message=azure_connection_message,
            message="Unused resource analysis completed.",
            unused_resources=findings,
        )

    def _azure_resource_id(self, resource: ArchitectureResource) -> str | None:
        props = resource.properties or {}
        value = props.get("azure_resource_id") if isinstance(props, dict) else None
        if not value:
            return None
        return str(value)

    def _azure_resource_type(self, resource: ArchitectureResource) -> str:
        props = resource.properties if isinstance(resource.properties, dict) else {}
        explicit = str(props.get("azure_resource_type") or "").strip().lower()
        if explicit:
            return explicit

        catalog = CATALOG_BY_RESOURCE_TYPE.get(resource.resource_type)
        if catalog:
            provider_type = str(catalog.get("azure_provider_type") or "").strip().lower()
            if provider_type:
                return provider_type

        azure_resource_id = self._azure_resource_id(resource)
        if azure_resource_id and "/providers/" in azure_resource_id.lower():
            suffix = azure_resource_id.split("/providers/", 1)[1]
            segments = [segment for segment in suffix.split("/") if segment]
            if len(segments) >= 2:
                if segments[0].lower() == "microsoft.sql" and len(segments) >= 4 and segments[3].lower() == "databases":
                    return f"{segments[0].lower()}/{segments[1].lower()}/{segments[3].lower()}"
                return f"{segments[0].lower()}/{segments[1].lower()}"

        return str(resource.resource_type or "unknown").strip().lower()

    def _subscription_id(self, azure_resource_id: str) -> str:
        parts = [part for part in str(azure_resource_id or "").split("/") if part]
        for idx, part in enumerate(parts):
            if part.lower() == "subscriptions" and idx + 1 < len(parts):
                return parts[idx + 1]
        return ""

    def _resource_group_name(self, azure_resource_id: str) -> str:
        parts = [part for part in str(azure_resource_id or "").split("/") if part]
        for idx, part in enumerate(parts):
            if part.lower() == "resourcegroups" and idx + 1 < len(parts):
                return parts[idx + 1]
        return ""

    def _portal_link(self, azure_resource_id: str) -> str:
        if str(azure_resource_id).startswith("/subscriptions/"):
            normalized = azure_resource_id
        else:
            normalized = f"/{str(azure_resource_id).lstrip('/')}"
        return f"https://portal.azure.com/#resource{normalized}"
