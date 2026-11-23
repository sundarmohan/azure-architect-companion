from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from math import isfinite
from typing import Any

import httpx

try:
    from azure.identity.aio import ClientSecretCredential
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
        credentials: dict[str, str] | None = None,
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

        if credentials is None:
            credentials = {
                "tenant_id": os.getenv("AZURE_TENANT_ID") or "",
                "client_id": os.getenv("AZURE_CLIENT_ID") or "",
                "client_secret": os.getenv("AZURE_CLIENT_SECRET") or "",
            }
        tenant_id = credentials.get("tenant_id", "").strip()
        client_id = credentials.get("client_id", "").strip()
        client_secret = credentials.get("client_secret", "")
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
                "to": datetime.combine(end_date, datetime.max.time().replace(microsecond=0), tzinfo=timezone.utc).isoformat(),
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
            async with ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret,
            ) as credential:
                token = await credential.get_token("https://management.azure.com/.default")
        except Exception:
            return {
                "available": False,
                "error": "Azure authentication failed for actual cost query",
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

            props = {} if response.status_code == 204 else response.json()["properties"]
            if props.get("nextLink"):
                return {"available": False, "error": "Azure returned a partial cost result. Select a shorter date range."}
            currency, total, daily = self._daily_charges(props, start_date, end_date)
            if not daily:
                return {"available": False, "error": "Azure returned no billed charges for the selected dates"}

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
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError, AttributeError, OverflowError):
            return {
                "available": False,
                "error": "Azure Cost Management did not return a usable cost result",
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

    def _daily_charges(self, props: dict, start_date: date, end_date: date):
        rows = props.get("rows", [])
        if not isinstance(rows, list):
            raise ValueError("Invalid daily charges")
        if not rows:
            return None, None, []
        columns = props["columns"]
        cost_index = self._column_index(columns, "Cost")
        if cost_index is None:
            cost_index = self._column_index(columns, "PreTaxCost")
        date_index = self._column_index(columns, "UsageDate")
        currency_index = self._column_index(columns, "Currency")
        if None in (cost_index, date_index, currency_index):
            raise ValueError("Missing billing columns")
        currency = None
        charges: dict[str, float] = {}
        for row in rows:
            cost = float(row[cost_index])
            usage_date = datetime.strptime(str(row[date_index]), "%Y%m%d").date()
            row_currency = row[currency_index]
            if (not isfinite(cost) or not start_date <= usage_date <= end_date or
                    not isinstance(row_currency, str) or len(row_currency) != 3 or
                    not row_currency.isascii() or not row_currency.isalpha()):
                raise ValueError("Invalid billing row")
            row_currency = row_currency.upper()
            if currency is not None and currency != row_currency:
                raise ValueError("Mixed billing currencies")
            currency = row_currency
            key = usage_date.isoformat()
            charges[key] = charges.get(key, 0) + cost
        total = sum(charges.values())
        if not isfinite(total) or not all(map(isfinite, charges.values())):
            raise ValueError("Cost result exceeds supported range")
        return currency, total, [{"usage_date": key, "cost": round(value, 2)} for key, value in sorted(charges.items())]
