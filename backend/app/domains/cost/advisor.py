"""Read subscription-scoped, cached cost recommendations from Azure Advisor."""

import asyncio
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

import httpx
from azure.core.exceptions import AzureError
from azure.identity.aio import ClientSecretCredential
from pydantic import BaseModel, Field

from app.domains.monitoring.security_collector import normalized_enum, object_fields, subscription_resource_id
from app.domains.monitoring.telemetry import request_json

ARM = "https://management.azure.com"
MAX_RECOMMENDATIONS = 25


class AdvisorRecommendation(BaseModel):
    id: str
    recommendation: str
    problem: str = ""
    resource_id: str | None = None
    impact: str = ""
    last_updated: str = ""


class AdvisorCostRead(BaseModel):
    subscription_id: UUID
    status: Literal["synced", "partial_failure", "authentication_failure", "permission_failure", "unsupported", "provider_error"]
    recommendations: list[AdvisorRecommendation] = Field(default_factory=list)
    retrieved_at: datetime | None = None
    truncated: bool = False


def safe_text(value, limit):
    return value.strip()[:limit] if isinstance(value, str) else ""


def advisor_cost_snapshot(subscription_id, payload):
    rows = payload.get("value")
    if not isinstance(rows, list):
        return AdvisorCostRead(subscription_id=subscription_id, status="provider_error")

    scope = f"/subscriptions/{subscription_id}"
    recommendations = {}
    incomplete = False
    for row in rows[:MAX_RECOMMENDATIONS]:
        entry = object_fields(row)
        props = object_fields(entry.get("properties"))
        category = normalized_enum(props.get("category"))
        if category and category != "cost":
            continue
        recommendation_id = subscription_resource_id(entry.get("id"), scope)
        provider_path, separator, name = (recommendation_id or "").casefold().rpartition("/providers/microsoft.advisor/recommendations/")
        resource = object_fields(props.get("resourceMetadata")).get("resourceId")
        resource_id = subscription_resource_id(resource, scope)
        description = object_fields(props.get("shortDescription"))
        problem = safe_text(description.get("problem"), 400)
        solution = safe_text(description.get("solution"), 400) or safe_text(props.get("description"), 400) or problem
        if not (category and provider_path and separator and name and "/" not in name and solution) or (resource and not resource_id):
            incomplete = True
            continue
        recommendations.setdefault(recommendation_id.casefold(), AdvisorRecommendation(
            id=recommendation_id, recommendation=solution, problem=problem if problem != solution else "",
            resource_id=resource_id, impact=safe_text(props.get("impact"), 40),
            last_updated=safe_text(props.get("lastUpdated"), 40),
        ))

    return AdvisorCostRead(
        subscription_id=subscription_id, status="partial_failure" if incomplete else "synced",
        recommendations=list(recommendations.values()), retrieved_at=datetime.now(timezone.utc),
        truncated=len(rows) > MAX_RECOMMENDATIONS or bool(payload.get("nextLink")),
    )


async def read_advisor_cost(subscription_id, credentials):
    try:
        async with asyncio.timeout(20):
            async with ClientSecretCredential(
                tenant_id=credentials["tenant_id"], client_id=credentials["client_id"],
                client_secret=credentials["client_secret"],
            ) as credential:
                token = await credential.get_token(f"{ARM}/.default")
            async with httpx.AsyncClient(timeout=8, follow_redirects=False) as http:
                status, payload = await request_json(
                    http, asyncio.Semaphore(1),
                    f"{ARM}/subscriptions/{subscription_id}/providers/Microsoft.Advisor/recommendations",
                    {"api-version": "2025-01-01", "$filter": "Category eq 'Cost'", "$top": MAX_RECOMMENDATIONS},
                    {"Authorization": f"Bearer {token.token}"},
                )
    except AzureError:
        status = "authentication_failure"
    except (httpx.HTTPError, TimeoutError):
        status = "provider_error"
    if status != "synced":
        return AdvisorCostRead(subscription_id=subscription_id, status=status)
    return advisor_cost_snapshot(subscription_id, payload)
