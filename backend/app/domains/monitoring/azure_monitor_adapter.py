from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any

import httpx

try:
    from azure.identity import ClientSecretCredential
except Exception:  # pragma: no cover
    ClientSecretCredential = None  # type: ignore[assignment]


class AzureMonitorAdapter:
    RESOURCE_HEALTH_API_VERSION = "2022-10-01"
    METRICS_API_VERSION = "2018-01-01"

    RESOURCE_METRICS = {
        "vm": ["Percentage CPU", "Network In Total", "Network Out Total"],
        "appservice": ["CpuPercentage", "Requests", "Http5xx"],
        "appserviceplan": ["CpuPercentage", "MemoryPercentage"],
        "storage": ["UsedCapacity", "Ingress", "Egress"],
        "sql": ["cpu_percent", "storage_percent"],
        "sqlserver": ["cpu_percent"],
        "container": ["CpuUsage", "Requests"],
        "containerenv": ["CpuUsage", "Requests"],
        "aks": ["node_cpu_usage_percentage", "node_memory_working_set_percentage"],
        "keyvault": ["ServiceApiLatency", "ServiceApiResult"],
        "publicip": ["ByteCount"],
        "natgateway": ["BytesProcessed"],
        "gateway": ["TotalRequests", "FailedRequests"],
        "firewall": ["Throughput", "SNATPortUtilization"],
        "vnet": ["VmAvailabilityMetric"],
        "subnet": ["VmAvailabilityMetric"],
        "nsg": ["BytesProcessed"],
        "vpn": ["TunnelEgressBytes", "TunnelIngressBytes"],
        "bastion": ["TotalSessions"],
        "privateendpoint": ["BytesIn", "BytesOut"],
        "loganalytics": ["IngestionVolume", "QueryCount"],
    }

    async def get_resource_monitoring(
        self,
        *,
        resource_type: str,
        azure_resource_id: str,
        start_time: datetime,
        end_time: datetime,
        interval: str,
    ) -> dict[str, Any]:
        if not azure_resource_id:
            return {
                "state": "unsupported",
                "message": "Resource is missing Azure external id",
                "health_status": None,
                "metrics": [],
            }

        supported_metrics = self.RESOURCE_METRICS.get(str(resource_type or "").lower())
        if not supported_metrics:
            return {
                "state": "unsupported",
                "message": "Resource type is not supported for Azure Monitor metrics",
                "health_status": None,
                "metrics": [],
            }

        if ClientSecretCredential is None:
            return {
                "state": "not_configured",
                "message": "azure-identity is not installed; Azure monitoring is unavailable",
                "health_status": None,
                "metrics": [],
            }

        auth = self.get_access_token()
        if auth.get("state") != "configured":
            return {
                "state": str(auth.get("state") or "authentication_failure"),
                "message": str(auth.get("message") or "Azure authentication failed for monitoring"),
                "health_status": None,
                "metrics": [],
            }

        headers = {
            "Authorization": f"Bearer {auth.get('token')}",
            "Content-Type": "application/json",
        }

        health_status: str | None = None
        metrics_payload: list[dict[str, Any]] = []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                health_url = (
                    f"https://management.azure.com{azure_resource_id}"
                    "/providers/Microsoft.ResourceHealth/availabilityStatuses/current"
                )
                metrics_url = f"https://management.azure.com{azure_resource_id}/providers/microsoft.insights/metrics"
                timespan = self._format_timespan(start_time=start_time, end_time=end_time)
                health_task = client.get(
                    health_url,
                    params={"api-version": self.RESOURCE_HEALTH_API_VERSION},
                    headers=headers,
                )
                metrics_task = client.get(
                    metrics_url,
                    params={
                        "api-version": self.METRICS_API_VERSION,
                        "metricnames": ",".join(supported_metrics),
                        "timespan": timespan,
                        "interval": interval,
                        "aggregation": "Average,Total,Minimum,Maximum",
                    },
                    headers=headers,
                )

                health_response, metrics_response = await asyncio.gather(
                    health_task,
                    metrics_task,
                    return_exceptions=True,
                )

                if isinstance(health_response, httpx.TimeoutException) or isinstance(metrics_response, httpx.TimeoutException):
                    return {
                        "state": "azure_api_failure",
                        "message": "Azure Monitor query timed out",
                        "health_status": health_status,
                        "metrics": [],
                    }
                if isinstance(health_response, Exception) or isinstance(metrics_response, Exception):
                    return {
                        "state": "azure_api_failure",
                        "message": "Azure Monitor query failed",
                        "health_status": health_status,
                        "metrics": [],
                    }

                if health_response.status_code == 401:
                    return {
                        "state": "authentication_failure",
                        "message": "Azure authentication failed while reading resource health",
                        "health_status": None,
                        "metrics": [],
                    }
                if health_response.status_code == 403:
                    return {
                        "state": "permission_failure",
                        "message": "Azure permissions are insufficient for resource health/metrics",
                        "health_status": None,
                        "metrics": [],
                    }
                if health_response.status_code < 400:
                    health_payload = health_response.json() or {}
                    props = health_payload.get("properties") if isinstance(health_payload, dict) else {}
                    if isinstance(props, dict):
                        health_status = str(props.get("availabilityState") or "").strip() or None

                if metrics_response.status_code == 401:
                    return {
                        "state": "authentication_failure",
                        "message": "Azure authentication failed while reading metrics",
                        "health_status": health_status,
                        "metrics": [],
                    }
                if metrics_response.status_code == 403:
                    return {
                        "state": "permission_failure",
                        "message": "Azure permissions are insufficient for Azure Monitor metrics",
                        "health_status": health_status,
                        "metrics": [],
                    }
                if metrics_response.status_code >= 400:
                    message = self._api_error_message(metrics_response)
                    if self._is_unsupported_metrics_namespace(message):
                        return {
                            "state": "unsupported",
                            "message": message,
                            "health_status": health_status,
                            "metrics": [],
                        }
                    return {
                        "state": "azure_api_failure",
                        "message": message,
                        "health_status": health_status,
                        "metrics": [],
                    }

                metrics_payload = self._normalize_metrics(metrics_response.json() or {})

        except httpx.TimeoutException:
            return {
                "state": "azure_api_failure",
                "message": "Azure Monitor query timed out",
                "health_status": health_status,
                "metrics": [],
            }
        except Exception as exc:
            return {
                "state": "azure_api_failure",
                "message": f"Azure Monitor query failed: {exc}",
                "health_status": health_status,
                "metrics": [],
            }

        if metrics_payload:
            return {
                "state": "live",
                "message": None,
                "health_status": health_status,
                "metrics": metrics_payload,
            }

        if health_status:
            return {
                "state": "live",
                "message": "No metric datapoints in selected time range",
                "health_status": health_status,
                "metrics": [],
            }

        return {
            "state": "no_data",
            "message": "No Azure Monitor data available in selected time range",
            "health_status": None,
            "metrics": [],
        }

    def get_access_token(self) -> dict[str, Any]:
        if ClientSecretCredential is None:
            return {
                "state": "not_configured",
                "message": "azure-identity is not installed; Azure monitoring is unavailable",
                "token": None,
                "subscription_id": None,
            }

        tenant_id = (os.getenv("AZURE_TENANT_ID") or "").strip()
        client_id = (os.getenv("AZURE_CLIENT_ID") or "").strip()
        client_secret = (os.getenv("AZURE_CLIENT_SECRET") or "").strip()
        subscription_id = (os.getenv("AZURE_SUBSCRIPTION_ID") or "").strip() or None

        if not tenant_id or not client_id or not client_secret:
            return {
                "state": "not_configured",
                "message": "Azure credentials are not configured for monitoring",
                "token": None,
                "subscription_id": subscription_id,
            }

        try:
            credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret,
            )
            token = credential.get_token("https://management.azure.com/.default")
            return {
                "state": "configured",
                "message": "Azure monitoring credential resolved",
                "token": token.token,
                "subscription_id": subscription_id,
            }
        except Exception as exc:
            return {
                "state": "authentication_failure",
                "message": f"Azure authentication failed for monitoring: {exc}",
                "token": None,
                "subscription_id": subscription_id,
            }

    def _normalize_metrics(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        values = payload.get("value") or []
        if not isinstance(values, list):
            return []

        normalized: list[dict[str, Any]] = []
        for metric in values:
            if not isinstance(metric, dict):
                continue
            name_obj = metric.get("name") if isinstance(metric.get("name"), dict) else {}
            name = str(name_obj.get("value") or name_obj.get("localizedValue") or "").strip()
            unit = str(metric.get("unit") or "").strip() or None
            series_rows = metric.get("timeseries") or []
            if not isinstance(series_rows, list):
                continue

            points: list[dict[str, Any]] = []
            aggregation = None
            for series in series_rows:
                data_rows = series.get("data") if isinstance(series, dict) else None
                if not isinstance(data_rows, list):
                    continue
                for row in data_rows:
                    if not isinstance(row, dict):
                        continue
                    ts = row.get("timeStamp")
                    if ts is None:
                        continue
                    for key in ("average", "total", "minimum", "maximum"):
                        if row.get(key) is not None:
                            aggregation = aggregation or key
                            try:
                                points.append({
                                    "timestamp": str(ts),
                                    "value": round(float(row.get(key)), 4),
                                })
                            except Exception:
                                pass
                            break

            if not points:
                continue

            normalized.append(
                {
                    "name": name or "metric",
                    "unit": unit,
                    "aggregation": aggregation,
                    "points": points,
                }
            )

        return normalized

    def _api_error_message(self, response: httpx.Response) -> str:
        try:
            payload = response.json() or {}
            if isinstance(payload, dict):
                inner = payload.get("error")
                if isinstance(inner, dict) and inner.get("message"):
                    return str(inner.get("message"))
                if payload.get("message"):
                    return str(payload.get("message"))
        except Exception:
            pass
        return f"Azure API request failed with status {response.status_code}"

    def _format_timespan(self, *, start_time: datetime, end_time: datetime) -> str:
        start = start_time.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        end = end_time.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return f"{start}/{end}"

    def _is_unsupported_metrics_namespace(self, message: str) -> bool:
        normalized = str(message or "").lower()
        return "is not a supported platform metric namespace" in normalized
