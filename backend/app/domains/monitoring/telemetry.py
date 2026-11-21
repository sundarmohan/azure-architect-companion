"""Read-only Azure Monitor collection from the selected inventory snapshot."""

import asyncio
import math
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx

from .azure_monitor_adapter import AzureMonitorAdapter

ARM = "https://management.azure.com"
RESOURCE_HEALTH_API_VERSION = "2025-05-01"
MAX_RESOURCES = 40
CONCURRENCY = 8
ARM_RESOURCE_ID = re.compile(
    r"/subscriptions/[0-9a-f-]{36}/resourcegroups/[^/?#%\\]+"
    r"/providers/[a-z0-9.]+(?:/[^/?#%\\]+/[^/?#%\\]+)+", re.IGNORECASE
)
PLATFORM_METRICS = {
    "microsoft.compute/virtualmachines": {
        "Average": ("Percentage CPU", "Available Memory Bytes"),
        "Total": ("Network In Total", "Network Out Total"),
    },
    "microsoft.web/sites": {"Total": ("Requests", "Http5xx")},
    "microsoft.web/serverfarms": {"Average": ("CpuPercentage", "MemoryPercentage")},
    "microsoft.storage/storageaccounts": {"Average": ("UsedCapacity",), "Total": ("Ingress", "Egress")},
    "microsoft.sql/servers/databases": {"Average": ("cpu_percent", "storage_percent")},
    "microsoft.network/natgateways": {"Total": ("ByteCount",)},
    "microsoft.network/publicipaddresses": {"Total": ("ByteCount",)},
    "microsoft.network/azurefirewalls": {"Average": ("Throughput", "SNATPortUtilization")},
    "microsoft.network/applicationgateways": {"Average": ("Throughput",), "Total": ("FailedRequests",)},
}


async def request_json(http, semaphore, url, params, headers):
    try:
        async with semaphore:
            response = await http.get(url, params=params, headers=headers, follow_redirects=False)
        if response.status_code != 200:
            return {
                401: "authentication_failure",
                403: "permission_failure",
                404: "unsupported",
            }.get(response.status_code, "provider_error"), {}
        payload = response.json()
        if isinstance(payload, dict):
            return "synced", payload
    except (httpx.HTTPError, ValueError):
        pass
    return "provider_error", {}


def summarize_states(states):
    failures = set(states) & {"authentication_failure", "permission_failure", "provider_error"}
    if not failures:
        return "synced"
    if "synced" in states or len(failures) > 1:
        return "partial_failure"
    return next(iter(failures))


def metrics_for_request(payload, names, aggregation):
    raw = payload.get("value")
    if not isinstance(raw, list):
        return [], "provider_error"
    by_name = {}
    allowed_names = {name.casefold(): name for name in names}
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("name"), dict):
            continue
        name = allowed_names.get(str(item["name"].get("value")).casefold())
        series = item.get("timeseries")
        if not name or not isinstance(series, list) or len(series) != 1 or not isinstance(series[0], dict):
            continue
        data = series[0].get("data")
        if not isinstance(data, list):
            continue
        points = {}
        for row in data:
            if not isinstance(row, dict):
                continue
            value, timestamp = row.get(aggregation.lower()), row.get("timeStamp")
            if type(value) not in {int, float} or abs(value) > 1e30 or not math.isfinite(value):
                continue
            try:
                moment = datetime.fromisoformat(timestamp)
                if moment.tzinfo is None:
                    continue
                points[moment.astimezone(timezone.utc).isoformat()] = value
            except (TypeError, ValueError, OverflowError):
                continue
        if points:
            unit = item.get("unit")
            by_name[name] = {
                "name": name,
                "unit": unit[:40] if isinstance(unit, str) else None,
                "aggregation": aggregation.lower(),
                "points": [{"timestamp": timestamp, "value": points[timestamp]} for timestamp in sorted(points)[-25:]],
            }
    return [by_name[name] for name in names if name in by_name], "synced" if by_name else "no_data"


async def collect_resource(resource, http, semaphore, headers, timespan):
    row = {key: resource.get(key, "") for key in ("id", "name", "type", "location")}
    resource_id = row["id"]
    if (not isinstance(resource_id, str) or len(resource_id) > 2048
            or not ARM_RESOURCE_ID.fullmatch(resource_id)
            or any(part in {".", ".."} for part in resource_id.split("/"))
            or any(ord(char) < 32 for char in resource_id)):
        return dict(row, health=None, health_status="unsupported", metrics_status="unsupported", metrics=[]), []
    url = f"{ARM}{quote(resource_id, safe='/')}"
    profiles = PLATFORM_METRICS.get(str(row["type"]).casefold(), {})

    health_call = request_json(
        http, semaphore, f"{url}/providers/Microsoft.ResourceHealth/availabilityStatuses/current",
        {"api-version": RESOURCE_HEALTH_API_VERSION}, headers,
    )
    metric_calls = [
        request_json(
            http, semaphore, f"{url}/providers/microsoft.insights/metrics",
            {"api-version": AzureMonitorAdapter.METRICS_API_VERSION, "metricnames": ",".join(names),
             "timespan": timespan, "interval": "PT1H", "aggregation": aggregation}, headers,
        )
        for aggregation, names in profiles.items()
    ]
    (health_status, health_document), *responses = await asyncio.gather(health_call, *metric_calls)
    health_values = {"available": "available", "degraded": "degraded", "unavailable": "unavailable", "unknown": "unknown"}
    properties = health_document.get("properties")
    health = health_values.get(str(properties.get("availabilityState")).casefold()) if isinstance(properties, dict) else None
    if health_status == "synced" and not health:
        health_status = "no_data"

    metrics, metric_states = [], []
    for (aggregation, names), (state, payload) in zip(profiles.items(), responses):
        if state == "synced":
            parsed, state = metrics_for_request(payload, names, aggregation)
            metrics.extend(parsed)
        metric_states.append(state)
    metrics_status = summarize_states(metric_states)
    if metrics_status == "synced" and not metrics:
        metrics_status = "no_data" if "no_data" in metric_states else "unsupported"
    return dict(row, health=health, health_status=health_status,
                metrics_status=metrics_status, metrics=metrics), [health_status, *metric_states]


async def collect_telemetry(resources, http, headers):
    """Collect recent resource health and counters without modifying Azure."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=24)
    timespan = AzureMonitorAdapter()._format_timespan(start_time=start, end_time=end)
    semaphore = asyncio.Semaphore(CONCURRENCY)
    observations = await asyncio.gather(*(
        collect_resource(resource, http, semaphore, headers, timespan) for resource in resources[:MAX_RESOURCES]
    ))
    limitations = [
        "Azure Resource Health and platform metric support varies by resource type and Azure permissions.",
        "Metrics cover the previous 24 hours at hourly intervals. Network counters report volume only.",
    ]
    if len(resources) > MAX_RESOURCES:
        limitations.append(f"Sampled the first {MAX_RESOURCES} resources of {len(resources)} inventory records.")
    status = summarize_states([state for _, states in observations for state in states])
    return status, {"resources": [row for row, _ in observations], "limitations": limitations}
