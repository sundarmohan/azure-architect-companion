"""Read existing Azure security signals without initiating scans or cloud changes."""

import asyncio
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from uuid import UUID

import httpx

ARM = "https://management.azure.com"
MAX_PAGES = 10
MAX_ROWS = 2500
ACTIVITY_HOURS = 24
SEVERITIES = {"critical", "high", "medium", "low", "informational"}
ACTIVITY_OPERATIONS = {
    "microsoft.authorization/roleassignments/write": "role_assignment_written",
    "microsoft.authorization/roleassignments/delete": "role_assignment_removed",
    "microsoft.authorization/roledefinitions/write": "role_definition_written",
    "microsoft.authorization/roledefinitions/delete": "role_definition_removed",
    "microsoft.security/pricings/write": "defender_plan_written",
    "microsoft.insights/diagnosticsettings/write": "diagnostic_setting_written",
    "microsoft.insights/diagnosticsettings/delete": "diagnostic_setting_removed",
}
SAFE_ID_PATH = re.compile(r"(?:/[A-Za-z0-9_.()~-]{1,260})+")


def object_fields(value):
    return value if isinstance(value, dict) else {}


def normalized_enum(value):
    return value.casefold() if isinstance(value, str) else ""


def guid(value):
    try:
        return str(UUID(value)) if isinstance(value, str) else None
    except ValueError:
        return None


def subscription_resource_id(value, scope):
    if not isinstance(value, str) or len(value) > 1024 or not SAFE_ID_PATH.fullmatch(value):
        return None
    if value.casefold() != scope and not value.casefold().startswith(f"{scope}/"):
        return None
    if {".", ".."}.intersection(value.split("/")):
        return None
    return value


def finding(code, title, severity, resource_id, evidence, source):
    return {
        "code": code,
        "title": title,
        "severity": severity,
        "resource_id": resource_id,
        "evidence": evidence,
        "source": source,
    }


def assessment_findings(rows, scope, inventory):
    findings = {}
    for row in rows:
        properties = object_fields(row.get("properties"))
        details = object_fields(properties.get("resourceDetails"))
        status = object_fields(properties.get("status"))
        if normalized_enum(details.get("source")) != "azure" or normalized_enum(status.get("code")) != "unhealthy":
            continue
        resource_id = subscription_resource_id(details.get("id"), scope)
        assessment_id = guid(row.get("name"))
        row_id = subscription_resource_id(row.get("id"), scope)
        if not resource_id or not assessment_id or not row_id:
            continue
        if row_id.casefold() != f"{resource_id}/providers/Microsoft.Security/assessments/{assessment_id}".casefold():
            continue
        resource_id = inventory.get(resource_id.casefold())
        if not resource_id:
            continue
        severity = normalized_enum(object_fields(properties.get("metadata")).get("severity"))
        known_severity = severity in SEVERITIES
        findings[resource_id.casefold(), assessment_id] = finding(
            "defender_unhealthy_assessment", "Unhealthy Defender for Cloud assessment",
            severity if known_severity else "informational", resource_id,
            {"assessment_id": assessment_id, "status": "unhealthy", "severity_reported": known_severity},
            "azure_defender_assessments",
        )
    return list(findings.values())


def alert_findings(rows, scope, inventory):
    counts = Counter()
    seen = set()
    for row in rows:
        if not subscription_resource_id(row.get("id"), scope):
            continue
        properties = object_fields(row.get("properties"))
        if normalized_enum(properties.get("status")) != "active":
            continue
        severity = normalized_enum(properties.get("severity"))
        severity = severity if severity in SEVERITIES else "informational"
        identifiers = properties.get("resourceIdentifiers")
        if not isinstance(identifiers, list):
            identifiers = []
        known = set()
        for identifier in identifiers:
            identifier = object_fields(identifier)
            if identifier.get("type") != "AzureResource":
                continue
            resource_id = subscription_resource_id(identifier.get("azureResourceId"), scope)
            if resource_id and resource_id.casefold() in inventory:
                known.add(inventory[resource_id.casefold()])
        alert_id = row["id"].casefold()
        for resource_id in known or {scope}:
            key = (alert_id, resource_id)
            if key not in seen:
                seen.add(key)
                counts[resource_id, severity] += 1
    return [
        finding("defender_active_alerts", "Active Defender for Cloud alerts", severity, resource_id,
                {"status": "active", "count": count}, "azure_defender_alerts")
        for (resource_id, severity), count in sorted(counts.items())
    ]


def activity_findings(rows, subscription_id, scope, inventory):
    counts = Counter()
    seen = set()
    for row in rows:
        if guid(row.get("subscriptionId")) != subscription_id:
            continue
        operation = ACTIVITY_OPERATIONS.get(normalized_enum(object_fields(row.get("operationName")).get("value")))
        status = normalized_enum(object_fields(row.get("status")).get("value"))
        event_id = guid(row.get("eventDataId"))
        if not operation or status not in {"succeeded", "failed"} or not event_id or event_id in seen:
            continue
        raw_id = row.get("resourceId")
        resource_id = subscription_resource_id(raw_id, scope)
        if raw_id and not resource_id:
            continue
        seen.add(event_id)
        resource_id = inventory.get(resource_id.casefold(), scope) if resource_id else scope
        counts[resource_id, operation, status] += 1
    return [
        finding("azure_security_control_activity", "Azure security control activity", "informational", resource_id,
                {"operation": operation, "status": status, "count": count, "window_hours": ACTIVITY_HOURS},
                "azure_activity_log")
        for (resource_id, operation, status), count in sorted(counts.items())
    ]


async def read_feed(http, headers, path, params):
    """Bound paging to the same ARM subscription collection and discard invalid feeds."""
    rows = []
    url = f"{ARM}{path}"
    seen = set()
    try:
        async with asyncio.timeout(30):
            for _ in range(MAX_PAGES):
                if url in seen:
                    break
                seen.add(url)
                response = await http.get(url, params=params, headers=headers, follow_redirects=False)
                if response.status_code != 200:
                    state = {401: "authentication_failure", 403: "permission_failure"}.get(
                        response.status_code, "provider_error"
                    )
                    return state, []
                body = response.json()
                values = object_fields(body).get("value")
                if (not isinstance(values, list) or len(rows) + len(values) > MAX_ROWS
                        or any(not isinstance(row, dict) for row in values)):
                    break
                rows.extend(values)
                next_url = body.get("nextLink")
                if next_url is None or next_url == "":
                    return "synced", rows
                if (not isinstance(next_url, str) or len(next_url) > 8192
                        or any(ord(char) <= 32 or ord(char) == 127 for char in next_url)):
                    break
                target = urlsplit(next_url)
                if (target.scheme != "https" or target.netloc.casefold() != "management.azure.com"
                        or target.path.casefold() != path.casefold() or target.fragment):
                    break
                url = f"{ARM}{path}?{target.query}"
                params = None
    except (httpx.HTTPError, TimeoutError, ValueError):
        pass
    return "provider_error", []


async def collect_security(subscription_id: str, resources: list[dict], http, headers):
    subscription_id = guid(subscription_id)
    if not subscription_id:
        return "provider_error", [], ["An Azure subscription ID is required to collect security signals."]
    scope = f"/subscriptions/{subscription_id}"
    inventory = {scope: scope}
    for resource in resources:
        resource_id = subscription_resource_id(object_fields(resource).get("id"), scope)
        if resource_id:
            inventory[resource_id.casefold()] = resource_id

    end = datetime.now(timezone.utc).replace(microsecond=0)
    start = end - timedelta(hours=ACTIVITY_HOURS)
    activity_filter = (
        f"eventTimestamp ge '{start:%Y-%m-%dT%H:%M:%SZ}' and eventTimestamp le '{end:%Y-%m-%dT%H:%M:%SZ}'"
    )
    assessments, alerts, activity = await asyncio.gather(
        read_feed(http, headers, f"{scope}/providers/Microsoft.Security/assessments", {"api-version": "2020-01-01"}),
        read_feed(http, headers, f"{scope}/providers/Microsoft.Security/alerts", {"api-version": "2022-01-01"}),
        read_feed(http, headers, f"{scope}/providers/Microsoft.Insights/eventtypes/management/values", {
            "api-version": "2015-04-01", "$filter": activity_filter,
            "$select": "eventDataId,operationName,resourceId,status,subscriptionId",
        }),
    )
    findings = [
        *assessment_findings(assessments[1], scope, inventory),
        *alert_findings(alerts[1], scope, inventory),
        *activity_findings(activity[1], subscription_id, scope, inventory),
    ]
    limitations = [
        "Defender signals reflect the enabled plans and permissions on the selected Azure subscription.",
        "Assessments are limited to unhealthy Azure resources in inventory and subscription-level controls.",
        "Activity covers selected authorization, Defender plan, and diagnostic operations in the last 24 hours.",
    ]
    states = []
    for label, (state, _) in zip(("Defender assessments", "Defender alerts", "Azure Activity"), (assessments, alerts, activity)):
        states.append(state)
        if state != "synced":
            limitations.append(f"{label} unavailable ({state.replace('_', ' ')}).")
    if all(state == "synced" for state in states):
        return "synced", findings, limitations
    if "synced" in states:
        return "partial_failure", findings, limitations
    state = next((state for state in ("authentication_failure", "permission_failure") if state in states),
                 "provider_error")
    return state, [], limitations
