from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

try:
    from azure.identity import ClientSecretCredential
except Exception:  # pragma: no cover - import guard for optional dependency
    ClientSecretCredential = None  # type: ignore[assignment]


class AzureCostManagementAdapter:
    API_VERSION = "2023-03-01"
    MAX_RETRIES = 3

    async def get_actual_cost(
        self,
        *,
        subscription_id: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        if end_date < start_date:
            return {
                "available": False,
                "error": "Invalid date range: end_date is before start_date",
            }

        if not subscription_id:
            return {
                "available": False,
                "error": "Missing Azure subscription id for actual cost query",
            }

        if ClientSecretCredential is None:
            return {
                "available": False,
                "error": "azure-identity is not installed; actual cost query is unavailable",
            }

        tenant_id = (os.getenv("AZURE_TENANT_ID") or "").strip()
        client_id = (os.getenv("AZURE_CLIENT_ID") or "").strip()
        client_secret = (os.getenv("AZURE_CLIENT_SECRET") or "").strip()
        if not tenant_id or not client_id or not client_secret:
            return {
                "available": False,
                "error": "Azure credentials are not configured for actual cost query",
            }

        query_url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            "/providers/Microsoft.CostManagement/query"
        )
        body = {
            "type": "ActualCost",
            "timeframe": "Custom",
            "timePeriod": {
                "from": datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc).isoformat(),
                "to": datetime.combine(end_date, datetime.min.time(), tzinfo=timezone.utc).isoformat(),
            },
            "dataset": {
                "granularity": "Daily",
                "aggregation": {
                    "totalCost": {
                        "name": "Cost",
                        "function": "Sum",
                    }
                },
            },
        }

        try:
            credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret,
            )
            token = credential.get_token("https://management.azure.com/.default")
        except Exception as exc:
            return {
                "available": False,
                "error": f"Azure authentication failed for actual cost query: {exc}",
            }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await self._post_cost_query(
                    client=client,
                    query_url=query_url,
                    token=token.token,
                    body=body,
                )

            if response.status_code in {401, 403}:
                return {
                    "available": False,
                    "error": "Azure permissions are insufficient for Cost Management query",
                    "status_code": response.status_code,
                }
            response.raise_for_status()

            payload = response.json() or {}
            props = payload.get("properties") or {}
            columns = props.get("columns") or []
            rows = props.get("rows") or []

            idx_cost = self._column_index(columns, "Cost")
            idx_currency = self._column_index(columns, "Currency")
            idx_date = self._column_index(columns, "UsageDate")

            total = 0.0
            currency = "USD"
            daily: list[dict[str, Any]] = []
            for row in rows:
                if not isinstance(row, list):
                    continue
                cost_val = self._safe_float(row[idx_cost]) if idx_cost is not None and idx_cost < len(row) else 0.0
                total += cost_val
                if idx_currency is not None and idx_currency < len(row) and row[idx_currency]:
                    currency = str(row[idx_currency])
                usage_date = str(row[idx_date]) if idx_date is not None and idx_date < len(row) else ""
                daily.append({"usage_date": usage_date, "cost": round(cost_val, 2)})

            return {
                "available": True,
                "source": "azure_cost_management",
                "subscription_id": subscription_id,
                "currency": currency,
                "total_cost": round(total, 2),
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
                "daily": daily,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            }
        except httpx.TimeoutException:
            return {
                "available": False,
                "error": "Azure Cost Management query timed out",
            }
        except Exception as exc:
            return {
                "available": False,
                "error": f"Azure Cost Management query failed: {exc}",
            }

    async def _post_cost_query(
        self,
        *,
        client: httpx.AsyncClient,
        query_url: str,
        token: str,
        body: dict[str, Any],
    ) -> httpx.Response:
        response: httpx.Response | None = None
        for attempt in range(self.MAX_RETRIES):
            response = await client.post(
                query_url,
                params={"api-version": self.API_VERSION},
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=body,
            )

            if response.status_code == 429 and attempt < self.MAX_RETRIES - 1:
                retry_after = self._retry_after_seconds(response)
                await asyncio.sleep(retry_after)
                continue

            if response.status_code >= 500 and attempt < self.MAX_RETRIES - 1:
                await asyncio.sleep(1 + attempt)
                continue

            return response

        return response if response is not None else httpx.Response(500)

    def _retry_after_seconds(self, response: httpx.Response) -> float:
        header = str(response.headers.get("Retry-After") or "").strip()
        try:
            value = float(header)
            if value > 0:
                return min(value, 10.0)
        except Exception:
            pass
        return 2.0

    def default_start_date(self) -> date:
        return (datetime.now(timezone.utc) - timedelta(days=30)).date()

    def default_end_date(self) -> date:
        return datetime.now(timezone.utc).date()

    def _column_index(self, columns: list[dict[str, Any]], name: str) -> int | None:
        for idx, col in enumerate(columns):
            if str(col.get("name") or "").lower() == name.lower():
                return idx
        return None

    def _safe_float(self, value: Any) -> float:
        try:
            return float(value)
        except Exception:
            return 0.0
