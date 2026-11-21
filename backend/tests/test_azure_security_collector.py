import json

import httpx
import pytest

from app.domains.monitoring.security_collector import collect_security


SUBSCRIPTION = "089bd33f-d4ec-47fe-8ba5-0753aa5c5b33"
SCOPE = f"/subscriptions/{SUBSCRIPTION}"
RESOURCE = f"{SCOPE}/resourceGroups/example/providers/Microsoft.Compute/virtualMachines/vm"
ASSESSMENT = "21300918-b2e3-0346-785f-c77ff57d243b"
OTHER_RESOURCE = RESOURCE.replace(SUBSCRIPTION, "20ff7fc3-e762-44dd-bd96-b71116dcdc23")
SENSITIVE = "arbitrary text from Azure that must be dropped"


@pytest.mark.asyncio
async def test_collector_keeps_scoped_allowlisted_signals():
    def handle(request):
        assert request.method == "GET"
        assert request.url.host == "management.azure.com"
        assert request.url.path.startswith(f"{SCOPE}/")
        assert request.headers["authorization"] == "Bearer fixture-token"
        if request.url.path.endswith("/assessments"):
            return httpx.Response(200, json={"value": [
                {
                    "id": f"{resource}/providers/Microsoft.Security/assessments/{ASSESSMENT}",
                    "name": ASSESSMENT,
                    "properties": {
                        "displayName": SENSITIVE, "metadata": {"severity": "High"},
                        "resourceDetails": {"source": "Azure", "id": resource}, "status": {"code": "Unhealthy"},
                    },
                }
                for resource in (RESOURCE, OTHER_RESOURCE)
            ]})
        if request.url.path.endswith("/alerts"):
            alert = {
                "id": f"{SCOPE}/providers/Microsoft.Security/locations/westeurope/alerts/fixture",
                "properties": {
                    "status": "Active", "severity": "Medium", "supportingEvidence": SENSITIVE,
                    "resourceIdentifiers": [{"type": "AzureResource", "azureResourceId": RESOURCE}],
                },
            }
            return httpx.Response(200, json={"value": [alert, alert]})
        assert "eventTimestamp ge" in request.url.params["$filter"]
        assert "caller" not in request.url.params["$select"]
        return httpx.Response(200, json={"value": [{
            "subscriptionId": SUBSCRIPTION, "resourceId": RESOURCE, "eventDataId": ASSESSMENT,
            "status": {"value": "Succeeded"}, "caller": SENSITIVE,
            "operationName": {"value": "Microsoft.Authorization/roleAssignments/write"},
        }]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        status, findings, _ = await collect_security(SUBSCRIPTION, [{"id": RESOURCE}], http, {
            "Authorization": "Bearer fixture-token",
        })
    assert status == "synced"
    assert [row["severity"] for row in findings] == ["high", "medium", "informational"]
    assert {row["resource_id"] for row in findings} == {RESOURCE}
    assert findings[1]["evidence"]["count"] == 1
    assert findings[2]["evidence"]["operation"] == "role_assignment_written"
    assert SENSITIVE not in json.dumps(findings)


@pytest.mark.asyncio
async def test_collector_follows_only_same_scope_and_reports_partial_feeds():
    paths = []

    def handle(request):
        paths.append(str(request.url))
        if request.url.path.endswith("/assessments"):
            if "$skiptoken" in request.url.params:
                return httpx.Response(200, json={"value": []})
            return httpx.Response(200, json={
                "value": [], "nextLink": f"https://management.azure.com{request.url.path}?$skiptoken=second",
            })
        if request.url.path.endswith("/alerts"):
            return httpx.Response(200, json={
                "value": [], "nextLink": f"https://forbidden.example{request.url.path}?$skiptoken=second",
            })
        return httpx.Response(403)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        status, findings, limitations = await collect_security(SUBSCRIPTION, [], http, {})
    assert status == "partial_failure"
    assert not findings
    assert len(paths) == 4
    assert not any("forbidden.example" in path for path in paths)
    assert "Defender alerts unavailable (provider error)." in limitations
    assert "Azure Activity unavailable (permission failure)." in limitations
