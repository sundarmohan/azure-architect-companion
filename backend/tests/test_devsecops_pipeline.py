import asyncio
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.domains.devsecops import routes
from app.main import app
from tests.test_local_access import PASSWORD, WRITE


def test_github_pipeline_is_scoped_and_returns_only_selected_metadata(monkeypatch):
    monkeypatch.setenv("MONITORAI_OBSERVATION_WORKER", "0")
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_USERNAME", "phase-one-admin")
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_PASSWORD", PASSWORD)
    calls = []

    async def saved_runs(owner, repository):
        calls.append((owner, repository))
        return {"total_count": 1, "workflow_runs": [{
            "id": 111, "name": "Build", "head_branch": "main", "head_sha": "a" * 40,
            "event": "push", "status": "completed", "conclusion": "success",
            "created_at": "2026-11-01T00:00:00Z", "logs_url": "https://example.invalid/logs",
        }]}

    monkeypatch.setattr(routes, "read_public_runs", saved_runs)
    path = "/api/devsecops/github/runs"
    params = {"owner": "octocat", "repository": "hello-world"}
    with TestClient(app, base_url="https://testserver") as client:
        assert client.get(path, params=params).status_code == 401
        assert client.post("/api/auth/login", headers=WRITE, json={
            "username": "phase-one-admin", "password": PASSWORD,
        }).status_code == 200
        assert client.get(path, params=params).status_code == 403
        client_id = client.post("/api/auth/clients", headers=WRITE,
                                json={"name": str(uuid4())}).json()["client_id"]
        headers = {**WRITE, "X-Client-ID": client_id}
        for invalid in ({"owner": "github.com@localhost"}, {"repository": ".."}, {"repository": "x/y"}):
            assert client.get(path, params={**params, **invalid}, headers=headers).status_code == 422
        result = client.get(path, params=params, headers=headers)
        assert result.status_code == 200, result.text
        evidence = result.json()
        assert evidence["repository"] == "octocat/hello-world"
        assert evidence["runs"][0]["conclusion"] == "success"
        assert "logs_url" not in evidence["runs"][0]
        assert calls == [("octocat", "hello-world")]


@pytest.mark.parametrize(("upstream", "headers", "expected"), [
    (403, {"x-ratelimit-remaining": "0"}, 429),
    (403, {}, 403),
    (404, {}, 404),
    (302, {"location": "https://example.invalid"}, 502),
])
def test_public_workflow_request_uses_fixed_endpoint_without_redirects(monkeypatch, upstream, headers, expected):
    real_client = httpx.AsyncClient

    def respond(request):
        assert request.method == "GET"
        assert request.url == httpx.URL("https://api.github.com/repos/octocat/hello-world/actions/runs?per_page=20")
        assert "authorization" not in request.headers
        return httpx.Response(upstream, headers=headers)

    def client(**kwargs):
        return real_client(**kwargs, transport=httpx.MockTransport(respond))

    monkeypatch.setattr(routes.httpx, "AsyncClient", client)
    with pytest.raises(HTTPException) as failure:
        asyncio.run(routes.read_public_runs("octocat", "hello-world"))
    assert failure.value.status_code == expected
