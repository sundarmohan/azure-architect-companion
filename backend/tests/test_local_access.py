from uuid import uuid4

import httpx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.domains.access import azure
from app.main import app

AUTH = "/api/auth"
ARCH = "/api/architectures"
AZURE = "/api/settings/azure"
WRITE = {"X-MonitorAI-Request": "1"}
PASSWORD = "A phase-one password"
NEW_PASSWORD = "A changed phase-one password"


def test_phase_one_access(monkeypatch):
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_USERNAME", "phase-one-admin")
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_PASSWORD", PASSWORD)
    monkeypatch.setenv("MONITORAI_AZURE_ENCRYPTION_KEY", Fernet.generate_key().decode())

    async def fake_azure_check(values):
        assert values["client_secret"] == "test-azure-secret"
        return httpx.Response(200)

    monkeypatch.setattr(azure, "check_subscription", fake_azure_check)
    with TestClient(app, base_url="https://testserver") as client:
        assert client.get(ARCH).status_code == 401
        assert client.post(AUTH + "/login", json={"username": "phase-one-admin", "password": PASSWORD}).status_code == 403
        signed_in = client.post(AUTH + "/login", headers=WRITE,
                                json={"username": "phase-one-admin", "password": PASSWORD})
        assert signed_in.status_code == 200, signed_in.text
        assert "HttpOnly" in signed_in.headers["set-cookie"]
        assert "Secure" in signed_in.headers["set-cookie"]

        clients = []
        for _ in range(2):
            response = client.post(AUTH + "/clients", headers=WRITE, json={"name": str(uuid4())})
            assert response.status_code == 201, response.text
            clients.append(response.json()["client_id"])

        editor = "editor-" + uuid4().hex
        response = client.post(AUTH + "/users", headers=WRITE, json={"username": editor, "password": PASSWORD})
        assert response.status_code == 201, response.text
        for client_id, role in zip(clients, ("editor", "viewer")):
            response = client.post(f"{AUTH}/clients/{client_id}/members", headers=WRITE,
                                   json={"username": editor, "role": role})
            assert response.status_code == 204
        first, second = [{**WRITE, "X-Client-ID": key} for key in clients]
        architecture = client.post(ARCH, headers=first, json={"name": "Private design"})
        assert architecture.status_code == 201, architecture.text
        architecture_path = f"{ARCH}/{architecture.json()['id']}"
        resource = client.post(architecture_path + "/resources", headers=first,
                               json={"name": "Private VM", "resource_type": "vm"})
        assert resource.status_code == 201, resource.text
        resource_path = architecture_path + "/resources/" + resource.json()["id"]

        payload = {key: str(uuid4()) for key in ("tenant_id", "client_id", "subscription_id")}
        payload["client_secret"] = "test-azure-secret"
        saved = client.put(AZURE + "/credentials", headers=first, json=payload)
        assert saved.status_code == 200, saved.text
        assert payload["client_secret"] not in saved.text
        invalid = client.put(AZURE + "/credentials", headers=first,
                             json={**payload, "tenant_id": payload["client_secret"]})
        assert invalid.status_code == 422 and payload["client_secret"] not in invalid.text
        check = client.post(AZURE + "/test", headers=first)
        assert check.json()["connection_state"] == "configured"
        assert client.get(AZURE + "/status", headers=second).json()["enabled"] is False
        assert client.get(ARCH, headers=second).json() == []
        assert client.delete(resource_path, headers=second).status_code == 404

        admin_token = client.cookies.get("monitorai_session")
        client.cookies.clear()
        assert client.post(AUTH + "/login", headers=WRITE,
                           json={"username": editor, "password": PASSWORD}).status_code == 200
        assert client.get(architecture_path, headers=first).status_code == 200
        assert client.get(architecture_path, headers=second).status_code == 404
        assert client.delete(resource_path, headers={**WRITE, "X-Client-ID": str(uuid4())}).status_code == 403
        assert client.put(resource_path, headers=second, json={"name": "cross-client"}).status_code == 403
        assert client.post(ARCH, headers=second, json={"name": "Forbidden"}).status_code == 403
        assert client.put(AZURE + "/credentials", headers=first, json=payload).status_code == 403
        assert client.post(AUTH + "/password", headers=WRITE,
                           json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}).status_code == 204
        assert client.get(AUTH + "/me").status_code == 401
        assert client.post(AUTH + "/login", headers=WRITE,
                           json={"username": editor, "password": NEW_PASSWORD}).status_code == 200
        member_token = client.cookies.get("monitorai_session")
        client.cookies.clear()
        client.cookies.set("monitorai_session", admin_token)
        assert client.post(f"{AUTH}/users/{editor}/password", headers=WRITE,
                           json={"new_password": PASSWORD}).status_code == 204
        revoked = client.get(AUTH + "/me", headers={"Cookie": f"monitorai_session={member_token}"})
        assert revoked.status_code == 401

        token = admin_token
        assert client.post(AUTH + "/logout", headers=WRITE).status_code == 204
        client.cookies.set("monitorai_session", token)
        assert client.get(AUTH + "/me").status_code == 401
