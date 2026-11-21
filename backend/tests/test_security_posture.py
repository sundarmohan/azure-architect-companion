import asyncio
from uuid import uuid4

import httpx

from app.domains.monitoring import security_posture


def test_security_posture_scores_authorized_configuration_without_exposing_payload(monkeypatch):
    subscription = str(uuid4())
    scope = f"/subscriptions/{subscription}"
    storage_id = f"{scope}/resourceGroups/test/providers/Microsoft.Storage/storageAccounts/example"
    foreign_id = f"/subscriptions/{uuid4()}/resourceGroups/test/providers/Microsoft.Storage/storageAccounts/foreign"
    requests = []

    async def defender(*_args):
        return "permission_failure", [], ["Defender evidence unavailable."]

    async def roles(_http, _headers, path, params):
        assert path == f"{scope}/providers/Microsoft.Authorization/roleAssignments"
        assert params["$filter"] == "atScope()"
        owner = "8e3af657-a8ff-443c-a75c-2fe8c4bcb635"
        return "synced", [{"properties": {"roleDefinitionId": owner, "scope": scope, "principalId": "sensitive-id"}}]

    def response(request):
        requests.append(request)
        return httpx.Response(200, json={"properties": {
            "allowBlobPublicAccess": True, "supportsHttpsTrafficOnly": False,
            "minimumTlsVersion": "TLS1_0", "ignored_key": "sensitive-property",
        }})

    async def collect():
        async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as http:
            return await security_posture.collect_security_snapshot(
                subscription, [{"id": storage_id, "type": "Microsoft.Storage/storageAccounts"},
                               {"id": foreign_id, "type": "Microsoft.Storage/storageAccounts"}],
                None, http, {},
            )

    monkeypatch.setattr(security_posture, "collect_security", defender)
    monkeypatch.setattr(security_posture, "read_feed", roles)
    status, payload, limits = asyncio.run(collect())
    assert status == "partial_failure"
    assert len(requests) == 1 and requests[0].method == "GET" and requests[0].url.path == storage_id
    assert payload["score"] == 39
    assert {row["code"] for row in payload["findings"]} == {
        "storage_public_blob_allowed", "storage_http_allowed", "storage_legacy_tls",
        "subscription_privileged_roles_owner",
    }
    assert "sensitive" not in str(payload)
    assert "Defender evidence unavailable." in limits


def test_repeated_failed_control_changes_are_review_signals():
    source = {"source": "azure_activity_log", "resource_id": "/subscriptions/example"}
    findings = security_posture.activity_signals([
        {**source, "evidence": {"status": "succeeded", "count": 5}},
        {**source, "evidence": {"status": "failed", "count": 2}},
        {**source, "evidence": {"status": "failed", "count": 3, "operation": "role_assignment_written"}},
    ])
    assert len(findings) == 1
    assert findings[0]["code"] == "repeated_security_control_failures"
    assert findings[0]["evidence"]["count"] == 3
