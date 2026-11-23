import asyncio
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
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

    monkeypatch.setenv("MONITORAI_AZURE_ENCRYPTION_KEY", Fernet.generate_key().decode())

    async def saved_runs(owner, repository, token=None):
        calls.append((owner, repository, token))
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
        assert calls == [("octocat", "hello-world", None)]
        connection = "/api/devsecops/github/connection"
        token = "fixture_repository_token_0000"
        configured = client.put(connection, headers=headers, json={**params, "token": token})
        assert configured.status_code == 200, configured.text
        assert configured.json() == params
        assert client.get(connection, headers=headers).json() == params
        assert client.get(path, headers=headers, params=params).status_code == 200
        assert calls[-1] == ("octocat", "hello-world", token)
        other = client.post("/api/auth/clients", headers=WRITE, json={"name": str(uuid4())}).json()["client_id"]
        assert client.get(path, headers={**WRITE, "X-Client-ID": other}, params=params).status_code == 200
        assert calls[-1] == ("octocat", "hello-world", None)
        assert client.get(path, headers=headers, params={**params, "repository": "different"}).status_code == 200
        assert calls[-1] == ("octocat", "different", None)
        assert client.delete(connection, headers=headers).status_code == 204
        assert client.get(connection, headers=headers).json() is None


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

def test_repository_findings_import_deduplication_and_scope(monkeypatch):
    monkeypatch.setenv("MONITORAI_OBSERVATION_WORKER", "0")
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_USERNAME", "phase-one-admin")
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_PASSWORD", PASSWORD)
    path = "/api/devsecops/findings"
    finding = {
        "owner": "Octocat", "repository": "Hello-World", "source": "ApprovedScanner",
        "category": "container", "severity": "high", "fingerprint": "a" * 64,
        "commit_sha": "b" * 40, "image": "ghcr.io/octocat/hello-world:v1",
    }
    with TestClient(app, base_url="https://testserver") as client:
        assert client.get(path).status_code == 401
        assert client.post("/api/auth/login", headers=WRITE, json={
            "username": "phase-one-admin", "password": PASSWORD,
        }).status_code == 200
        first, other = [client.post("/api/auth/clients", headers=WRITE, json={"name": str(uuid4())})
                        .json()["client_id"] for _ in range(2)]
        own, foreign = [{**WRITE, "X-Client-ID": value} for value in (first, other)]
        result = client.post(path + "/import", headers=own, json={
            "findings": [finding, {**finding, "owner": "octocat"}],
        })
        assert result.status_code == 200, result.text
        assert result.json() == {"inserted": 1, "duplicates": 1}
        for invalid in ({"raw_secret": "fixture"}, {"source": "ghp_fixture"}, {"image": "https://registry/image"}):
            rejected = client.post(path + "/import", headers=own, json={"findings": [{**finding, **invalid}]})
            assert rejected.status_code == 422
        results = client.get(path, headers=own).json()
        assert results["has_next"] is False
        saved, = results["findings"]
        assert saved["owner"] == "octocat"
        assert saved["recommendation"]
        assert client.get(path, headers=foreign).json()["findings"] == []
        events = client.get("/api/audit", headers=own).json()
        assert any(event["action"] == "import_devsecops_findings" for event in events)

        username = f"repo-view-{uuid4().hex}"
        assert client.post("/api/auth/users", headers=WRITE,
                           json={"username": username, "password": PASSWORD}).status_code == 201
        assert client.post(f"/api/auth/clients/{first}/members", headers=WRITE,
                           json={"username": username, "role": "viewer"}).status_code == 204
        client.cookies.clear()
        assert client.post("/api/auth/login", headers=WRITE,
                           json={"username": username, "password": PASSWORD}).status_code == 200
        assert client.get(path, headers=own).status_code == 200
        assert client.get(path, headers=foreign).status_code == 403
        assert client.post(path + "/import", headers=own, json={"findings": [finding]}).status_code == 403
