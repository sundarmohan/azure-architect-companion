"""Resource-scoped, read-only Azure Monitor Logs summaries."""

import asyncio
import json
import re
from datetime import datetime
from typing import Literal
from uuid import UUID

import httpx
from azure.core.exceptions import AzureError
from azure.identity.aio import ClientSecretCredential
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.access.azure import confirm_active_connection, connection_values, select_subscription
from app.domains.access.models import AzureConnection, AzureInventorySnapshot
from app.domains.access.routes import audit, client_access, get_db

router = APIRouter()
Source = Literal["activity", "platform", "app_service", "application", "guest"]
Hours = Literal[1, 6, 24, 72]

RESOURCE_ID = re.compile(
    r"/subscriptions/[0-9a-f-]{36}/resourcegroups/[A-Za-z0-9_.()-]+"
    r"/providers/[A-Za-z0-9.]+(?:/[A-Za-z0-9_.()-]+/[A-Za-z0-9_.()-]+)+",
    re.IGNORECASE,
)
QUERIES = {
    "activity": ("AzureActivity",
                 'case(ActivityStatusValue in~ ("Failed", "Failure"), "Failed", '
                 'ActivityStatusValue in~ ("Succeeded", "Success"), "Succeeded", "Other activity")',
                 {"Failed", "Succeeded", "Other activity"}),
    "platform": ("AzureDiagnostics", '"Platform diagnostics"', {"Platform diagnostics"}),
    "app_service": ("AppServiceHTTPLogs",
                    'case(ScStatus >= 500, "HTTP 5xx", ScStatus >= 400, "HTTP 4xx", "Other HTTP")',
                    {"HTTP 5xx", "HTTP 4xx", "Other HTTP"}),
    "application": ("AppExceptions", '"Application exceptions"', {"Application exceptions"}),
    "guest": ("union isfuzzy=true withsource=SourceTable Syslog, Event",
              'case(SourceTable endswith "Syslog", "Linux syslog", "Windows events")',
              {"Linux syslog", "Windows events"}),
}


class DiagnosticQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str = Field(min_length=1, max_length=1024)
    source: Source
    hours: Hours


class DiagnosticRow(BaseModel):
    timestamp: datetime
    category: str
    count: int


class DiagnosticResult(BaseModel):
    status: str
    source: Source
    hours: Hours
    rows: list[DiagnosticRow] = Field(default_factory=list)


def build_query(resource_id: str, source: Source, hours: Hours):
    table, category, _ = QUERIES[source]
    return (
        f"{table}\n"
        f"| where TimeGenerated >= ago({hours}h) and _ResourceId =~ {json.dumps(resource_id)}\n"
        f"| extend category = {category}\n"
        "| summarize count=count() by timestamp=bin(TimeGenerated, 1h), category\n"
        "| project timestamp, category, count\n"
        "| order by timestamp desc\n"
        "| take 240"
    )


def parse_results(body, source: Source, hours: Hours):
    result = DiagnosticResult(status="provider_error", source=source, hours=hours)
    if not isinstance(body, dict) or not isinstance(body.get("tables"), list):
        return result
    tables = body["tables"]
    permitted_categories = QUERIES[source][2]
    permissions = body.get("permissions")
    entries = (
        [item for section in ("resources", "dataSources") if isinstance(permissions.get(section), list)
         for item in permissions[section]] if isinstance(permissions, dict) else []
    )
    degraded = bool(body.get("error")) or any(
        isinstance(item, dict) and bool(item.get("denyTables")) for item in entries
    )
    found = False
    for table in tables:
        if not isinstance(table, dict) or table.get("name") != "PrimaryResult":
            continue
        found = True
        expected = ["timestamp", "category", "count"]
        columns, rows = table.get("columns"), table.get("rows")
        if (not isinstance(columns, list) or not isinstance(rows, list)
                or [col.get("name") for col in columns if isinstance(col, dict)] != expected):
            degraded = True
            continue
        for row in rows[:240]:
            if (not isinstance(row, list) or len(row) != 3 or not isinstance(row[0], str)
                    or not isinstance(row[1], str) or row[1] not in permitted_categories
                    or type(row[2]) is not int or not 0 < row[2] <= 2**53 - 1):
                degraded = True
                continue
            try:
                timestamp = datetime.fromisoformat(row[0])
            except ValueError:
                degraded = True
                continue
            if timestamp.tzinfo is None:
                degraded = True
                continue
            result.rows.append(DiagnosticRow(timestamp=timestamp, category=row[1], count=row[2]))
        break
    if found or degraded:
        result.status = "partial_failure" if degraded else ("ok" if result.rows else "no_data")
    return result


async def query_logs(credentials, resource_id: str, source: Source, hours: Hours):
    try:
        async with asyncio.timeout(35):
            async with ClientSecretCredential(
                tenant_id=credentials["tenant_id"], client_id=credentials["client_id"],
                client_secret=credentials["client_secret"],
            ) as credential:
                token = await credential.get_token("https://api.loganalytics.io/.default")
            async with httpx.AsyncClient(timeout=20, follow_redirects=False) as http:
                response = await http.post(
                    f"https://api.loganalytics.azure.com/v1{resource_id}/query",
                    headers={"Authorization": f"Bearer {token.token}", "Prefer": "include-permissions=true"},
                    json={"query": build_query(resource_id, source, hours), "timespan": f"PT{hours}H"},
                )
            if response.status_code == 200:
                return parse_results(response.json(), source, hours)
            status = {
                401: "authentication_failure", 403: "permission_failure",
                400: "source_unavailable", 404: "source_unavailable",
            }.get(response.status_code, "provider_error")
    except AzureError:
        status = "authentication_failure"
    except (httpx.HTTPError, TimeoutError, ValueError):
        status = "provider_error"
    return DiagnosticResult(status=status, source=source, hours=hours)


@router.post("/query", response_model=DiagnosticResult)
async def query_diagnostics(payload: DiagnosticQuery, request: Request, subscription_id: UUID | None = None,
                            client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db)):
    connection = await db.get(AzureConnection, client_id)
    values = await connection_values(db, client_id, connection) if connection else None
    selected = select_subscription(values, subscription_id)
    if selected is None:
        raise HTTPException(404, "Azure subscription is not configured")
    resource_id = payload.resource_id
    prefix = f"/subscriptions/{selected}/"
    if (not resource_id.casefold().startswith(prefix) or not RESOURCE_ID.fullmatch(resource_id)
            or any(segment in {".", ".."} for segment in resource_id.split("/"))):
        raise HTTPException(404, "Resource not found in this subscription inventory")
    snapshot = await db.get(AzureInventorySnapshot, (client_id, UUID(selected)))
    if (not snapshot or not snapshot.last_success_at or not any(
        str(resource.get("id", "")).casefold() == resource_id.casefold() for resource in snapshot.resources
    )):
        raise HTTPException(404, "Resource not found in this subscription inventory")
    ciphertext = connection.ciphertext
    await db.rollback()
    result = await query_logs(values, resource_id, payload.source, payload.hours)
    account = await confirm_active_connection(db, request, client_id, ciphertext)
    audit(db, "query_azure_diagnostics", account, client_id, f"{selected}:{payload.source}",
          "success" if result.status in {"ok", "no_data"} else "failed")
    await db.commit()
    return result
