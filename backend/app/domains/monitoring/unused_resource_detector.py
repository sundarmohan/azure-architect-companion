from __future__ import annotations

import concurrent.futures
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


_METRICS_API_VERSION = "2023-10-01"

_RESOURCE_API_VERSION_MAP: dict[str, str] = {
    "microsoft.compute/virtualmachines": "2023-09-01",
    "microsoft.compute/disks": "2023-04-02",
    "microsoft.storage/storageaccounts": "2023-01-01",
    "microsoft.sql/servers/databases": "2021-11-01",
    "microsoft.web/sites": "2022-09-01",
    "microsoft.web/serverfarms": "2022-09-01",
    "microsoft.network/publicipaddresses": "2023-09-01",
    "microsoft.network/networkinterfaces": "2023-09-01",
    "microsoft.network/networksecuritygroups": "2023-09-01",
    "microsoft.containerservice/managedclusters": "2023-08-01",
    "microsoft.containerinstance/containergroups": "2023-05-01",
}
_DEFAULT_API_VERSION = "2021-04-01"

# (metric_name, aggregation_label, threshold, comparison: "lt"|"eq", signal_label)
_IDLE_METRIC_RULES: dict[str, list[tuple[str, str, float, str, str]]] = {
    "microsoft.compute/virtualmachines": [
        ("Percentage CPU", "Average", 5.0, "lt", "cpu_avg_below_5pct"),
        ("Network In Total", "Total", 104857600.0, "lt", "network_in_below_100mb"),
    ],
    "microsoft.sql/servers/databases": [
        ("dtu_consumption_percent", "Average", 3.0, "lt", "dtu_avg_below_3pct"),
        ("cpu_percent", "Average", 3.0, "lt", "cpu_avg_below_3pct"),
    ],
    "microsoft.storage/storageaccounts": [
        ("Transactions", "Total", 100.0, "lt", "transactions_below_100"),
    ],
    "microsoft.web/sites": [
        ("BytesReceived", "Total", 1048576.0, "lt", "bytes_received_below_1mb"),
        ("Requests", "Total", 10.0, "lt", "requests_below_10"),
    ],
    "microsoft.web/serverfarms": [
        ("CpuPercentage", "Average", 3.0, "lt", "cpu_avg_below_3pct"),
    ],
    "microsoft.containerservice/managedclusters": [
        ("node_cpu_usage_percentage", "Average", 5.0, "lt", "cpu_avg_below_5pct"),
    ],
    "microsoft.containerinstance/containergroups": [
        ("CpuUsage", "Average", 5.0, "lt", "cpu_avg_below_5pct"),
    ],
}

_MONTHLY_COST_ESTIMATES: dict[str, float] = {
    "microsoft.compute/virtualmachines": 70.0,
    "microsoft.compute/disks": 9.6,
    "microsoft.storage/storageaccounts": 5.0,
    "microsoft.sql/servers/databases": 15.0,
    "microsoft.web/sites": 13.0,
    "microsoft.web/serverfarms": 73.0,
    "microsoft.network/publicipaddresses": 3.65,
    "microsoft.network/networkinterfaces": 0.0,
    "microsoft.network/networksecuritygroups": 0.0,
    "microsoft.containerservice/managedclusters": 147.0,
    "microsoft.containerinstance/containergroups": 30.0,
}


def _config_check_disk(props: dict[str, Any]) -> tuple[bool, str]:
    state = str(props.get("diskState") or "").strip()
    if state == "Unattached":
        return True, "Managed disk is unattached and not associated with any virtual machine"
    return False, ""


def _config_check_pip(props: dict[str, Any]) -> tuple[bool, str]:
    if props.get("ipConfiguration") is None and props.get("natGateway") is None:
        return True, "Public IP address is not associated with any resource"
    return False, ""


def _config_check_nic(props: dict[str, Any]) -> tuple[bool, str]:
    if props.get("virtualMachine") is None:
        return True, "Network interface is not attached to any virtual machine"
    return False, ""


def _config_check_nsg(props: dict[str, Any]) -> tuple[bool, str]:
    subnets = props.get("subnets") or []
    nics = props.get("networkInterfaces") or []
    if not subnets and not nics:
        return True, "Network Security Group has no subnet or NIC associations"
    return False, ""


_CONFIG_IDLE_CHECKS: dict[str, Any] = {
    "microsoft.compute/disks": _config_check_disk,
    "microsoft.network/publicipaddresses": _config_check_pip,
    "microsoft.network/networkinterfaces": _config_check_nic,
    "microsoft.network/networksecuritygroups": _config_check_nsg,
}


class IdleResourceDetector:
    def __init__(self, token: str, days: int = 7) -> None:
        self.token = token
        self.days = max(1, min(days, 30))

    @staticmethod
    def _iso(dt: datetime) -> str:
        return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")

    def _fetch_resource_config(self, azure_resource_id: str, resource_type: str) -> dict[str, Any] | None:
        api_version = _RESOURCE_API_VERSION_MAP.get(resource_type, _DEFAULT_API_VERSION)
        try:
            response = httpx.get(
                f"https://management.azure.com{azure_resource_id}",
                params={"api-version": api_version},
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=30,
            )
            if response.status_code < 400:
                return response.json()
        except Exception:
            return None
        return None

    def _query_metric(self, azure_resource_id: str, metric_name: str, aggregation_label: str) -> float | None:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=self.days)
        try:
            response = httpx.get(
                f"https://management.azure.com{azure_resource_id}/providers/microsoft.insights/metrics",
                params={
                    "api-version": _METRICS_API_VERSION,
                    "metricnames": metric_name,
                    "timespan": f"{self._iso(start)}/{self._iso(end)}",
                    "interval": "P1D",
                    "aggregation": aggregation_label,
                },
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=30,
            )
        except Exception:
            return None

        if response.status_code >= 400:
            return None
        try:
            payload = response.json()
        except Exception:
            return None

        values: list[float] = []
        for metric in payload.get("value", []):
            for series in metric.get("timeseries", []):
                for point in series.get("data", []):
                    value = point.get(aggregation_label.lower())
                    if value is not None:
                        values.append(float(value))

        if not values:
            return None

        if aggregation_label.lower() == "total":
            return sum(values)
        return sum(values) / len(values)

    def _recommended_action(self, resource_type: str, signal: str | None = None) -> str:
        normalized_type = str(resource_type or "").lower()
        normalized_signal = str(signal or "").lower()

        if normalized_signal == "config_unattached":
            if normalized_type == "microsoft.compute/disks":
                return "Attach the disk to an active VM or deallocate/delete the disk if no longer required."
            if normalized_type == "microsoft.network/publicipaddresses":
                return "Associate the public IP to an active resource or release it to prevent idle cost."
            if normalized_type == "microsoft.network/networkinterfaces":
                return "Attach the NIC to an active VM or remove it if it is no longer used."
            if normalized_type == "microsoft.network/networksecuritygroups":
                return "Associate the NSG with active subnets/NICs or remove unused NSGs."

        if normalized_type in {
            "microsoft.compute/virtualmachines",
            "microsoft.web/sites",
            "microsoft.web/serverfarms",
            "microsoft.containerservice/managedclusters",
            "microsoft.containerinstance/containergroups",
        }:
            return "Review utilization trend and right-size, schedule stop, or decommission if consistently idle."

        if normalized_type == "microsoft.sql/servers/databases":
            return "Review DTU/CPU trend and scale down or pause non-production databases when idle."

        if normalized_type == "microsoft.storage/storageaccounts":
            return "Review transactions and data lifecycle; move cold data and remove unused storage accounts."

        return "Validate business ownership and decommission or optimize the resource if idle pattern persists."

    def detect(self, resource: dict[str, Any]) -> dict[str, Any]:
        azure_resource_id = resource.get("azure_resource_id") or ""
        resource_type = str(resource.get("resource_type") or "").lower()
        idle_signals: list[str] = []
        idle_reasons: list[str] = []

        config_check_fn = _CONFIG_IDLE_CHECKS.get(resource_type)
        if config_check_fn:
            config = self._fetch_resource_config(azure_resource_id, resource_type)
            if config:
                props = config.get("properties") or {}
                is_idle, reason = config_check_fn(props)
                if is_idle:
                    idle_signals.append("config_unattached")
                    idle_reasons.append(reason)
                    return {
                        "is_idle": True,
                        "confidence": "high",
                        "idle_reason": reason,
                        "idle_signals": idle_signals,
                        "recommended_action": self._recommended_action(resource_type, "config_unattached"),
                        "days_checked": self.days,
                        "monthly_cost_estimate": _MONTHLY_COST_ESTIMATES.get(resource_type, 0.0),
                    }

        metric_rules = _IDLE_METRIC_RULES.get(resource_type, [])
        metrics_passed = 0
        metrics_queried = 0

        for metric_name, aggregation_label, threshold, comparison, signal_label in metric_rules:
            value = self._query_metric(azure_resource_id, metric_name, aggregation_label)
            if value is None:
                continue
            metrics_queried += 1
            passes = (value < threshold) if comparison == "lt" else (abs(value - threshold) < 1e-6)
            if passes:
                metrics_passed += 1
                idle_signals.append(f"{signal_label}({aggregation_label.lower()}={value:.1f})")

        if metrics_queried > 0 and metrics_passed > 0:
            pass_ratio = metrics_passed / metrics_queried
            if pass_ratio >= 0.5:
                confidence = "high" if (pass_ratio == 1.0 and metrics_queried >= 2) else "medium"
                idle_reasons.append(
                    f"{metrics_passed}/{metrics_queried} activity metrics below idle threshold over last {self.days} days"
                )
                return {
                    "is_idle": True,
                    "confidence": confidence,
                    "idle_reason": "; ".join(idle_reasons),
                    "idle_signals": idle_signals,
                    "recommended_action": self._recommended_action(resource_type),
                    "days_checked": self.days,
                    "monthly_cost_estimate": _MONTHLY_COST_ESTIMATES.get(resource_type, 0.0),
                }

        return {
            "is_idle": False,
            "confidence": "low",
            "idle_reason": "",
            "idle_signals": [],
            "recommended_action": None,
            "days_checked": self.days,
            "monthly_cost_estimate": _MONTHLY_COST_ESTIMATES.get(resource_type, 0.0),
        }

    def detect_batch(self, resources: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        if not resources:
            return results

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(resources))) as executor:
            futures = {
                executor.submit(self.detect, resource): (resource.get("azure_resource_id") or "")
                for resource in resources
            }
            for future in concurrent.futures.as_completed(futures):
                resource_id = futures[future]
                try:
                    results[resource_id] = future.result()
                except Exception as exc:
                    results[resource_id] = {
                        "is_idle": False,
                        "confidence": "low",
                        "idle_reason": f"Detection error: {exc}",
                        "idle_signals": [],
                        "recommended_action": None,
                        "days_checked": self.days,
                        "monthly_cost_estimate": 0.0,
                    }

        return results
