from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.test_local_access import ARCH, AUTH, PASSWORD, WRITE


def test_design_lifecycle_is_client_scoped_and_preserves_graph(monkeypatch):
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_USERNAME", "phase-one-admin")
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_PASSWORD", PASSWORD)
    with TestClient(app, base_url="https://testserver") as client:
        admin = client.post(AUTH + "/login", headers=WRITE, json={
            "username": "phase-one-admin", "password": PASSWORD,
        })
        assert admin.status_code == 200
        admin_session = client.cookies.get("monitorai_session")
        workspace_ids = []
        for _ in range(2):
            response = client.post(AUTH + "/clients", headers=WRITE, json={"name": str(uuid4())})
            assert response.status_code == 201
            workspace_ids.append(response.json()["client_id"])
        first, second = [{**WRITE, "X-Client-ID": workspace_id} for workspace_id in workspace_ids]

        response = client.post(ARCH, headers=first, json={
            "name": "Application design", "project": "Web", "environment": "production",
        })
        assert response.status_code == 201, response.text
        design = response.json()
        path = ARCH + "/" + design["id"]
        assert design["project"] == "Web" and design["environment"] == "production"
        assert client.get(ARCH, headers=first, params={"project": "Web", "environment": "production"}).json() == [design]
        assert client.get(ARCH, headers=first, params={"project": "Other"}).json() == []
        assert client.put(path, headers=first, json={"status": "approved"}).status_code == 422

        group = client.post(path + "/resource-groups", headers=first, json={
            "name": "design-rg", "location": "eastus",
        })
        assert group.status_code == 201
        group_id = group.json()["id"]
        parent = client.post(path + "/resources", headers=first, json={
            "name": "network", "resource_type": "vnet", "resource_group_id": group_id,
        })
        assert parent.status_code == 201
        parent_id = parent.json()["id"]
        child = client.post(path + "/resources", headers=first, json={
            "name": "subnet", "resource_type": "subnet", "resource_group_id": group_id,
            "parent_resource_id": parent_id,
        })
        assert child.status_code == 201
        child_id = child.json()["id"]
        assert client.put(path, headers=first, json={"graph_data": {"selected": child_id}}).status_code == 200

        saved = client.post(path + "/revisions", headers=first, json={"description": "Initial topology"})
        assert saved.status_code == 201, saved.text
        initial = saved.json()
        assert initial["number"] == 1
        assert client.get(path + "/revisions", headers=second).status_code == 404
        assert client.post(path + "/duplicate", headers=second, json={"name": "Unauthorized"}).status_code == 404

        duplicate = client.post(path + "/duplicate", headers=first, json={"name": "Fork"})
        assert duplicate.status_code == 201, duplicate.text
        copied = duplicate.json()
        duplicate_path = ARCH + "/" + copied["id"]
        copied_nodes = {row["name"]: row for row in client.get(duplicate_path + "/resources", headers=first).json()}
        assert copied_nodes["network"]["id"] != parent_id
        assert copied_nodes["subnet"]["id"] != child_id
        assert copied_nodes["subnet"]["parent_resource_id"] == copied_nodes["network"]["id"]
        assert copied_nodes["subnet"]["resource_group_id"] != group_id
        assert copied["graph_data"]["selected"] == copied_nodes["subnet"]["id"]
        assert client.get(duplicate_path + "/revisions/" + initial["id"], headers=first).status_code == 404

        assert client.delete(path + "/resources/" + child_id, headers=first).status_code == 204
        saved = client.post(path + "/revisions", headers=first, json={"description": "Remove subnet"})
        assert saved.status_code == 201
        compared = client.get(path + "/revisions/" + initial["id"] + "/compare", headers=first,
                              params={"to": saved.json()["id"]})
        assert compared.status_code == 200, compared.text
        assert [(change["section"], change["id"], change["kind"]) for change in compared.json()["changes"]] == [
            ("resources", child_id, "removed"),
        ]
        restored = client.post(path + "/revisions/" + initial["id"] + "/restore", headers=first,
                               json={"description": "Recover subnet"})
        assert restored.status_code == 200, restored.text
        restored_nodes = {row["name"]: row for row in client.get(path + "/resources", headers=first).json()}
        assert restored_nodes["subnet"]["id"] == child_id
        assert restored_nodes["subnet"]["parent_resource_id"] == parent_id
        assert [r["number"] for r in client.get(path + "/revisions", headers=first).json()] == [4, 3, 2, 1]

        username = "design-editor-" + uuid4().hex
        assert client.post(AUTH + "/users", headers=WRITE, json={
            "username": username, "password": PASSWORD,
        }).status_code == 201
        assert client.post(f"{AUTH}/clients/{workspace_ids[0]}/members", headers=WRITE, json={
            "username": username, "role": "editor",
        }).status_code == 204
        client.cookies.clear()
        assert client.post(AUTH + "/login", headers=WRITE, json={
            "username": username, "password": PASSWORD,
        }).status_code == 200
        editor_session = client.cookies.get("monitorai_session")
        assert client.post(path + "/status", headers=first, json={"status": "in_review"}).status_code == 200
        assert client.post(path + "/status", headers=first, json={"status": "approved"}).status_code == 403
        assert client.put(path + "/resources/" + child_id, headers=first, json={"name": "Unreviewed"}).status_code == 409

        client.cookies.clear()
        client.cookies.set("monitorai_session", admin_session)
        approved = client.post(path + "/status", headers=first, json={"status": "approved", "note": "Reviewed"})
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"
        assert client.post(path + "/revisions", headers=first, json={"description": "Forbidden"}).status_code == 409
        assert client.post(path + "/revisions/" + initial["id"] + "/restore", headers=first,
                           json={"description": "Forbidden"}).status_code == 409
        history = client.get(path + "/history", headers=first).json()
        assert [event["to_status"] for event in history] == ["approved", "in_review"]
        assert history[0]["note"] == "Reviewed"
        assert client.get(path + "/revisions", headers=first).json()[0]["description"] == "Reviewed"
        assert client.post(path + "/status", headers=first, json={"status": "archived"}).status_code == 200

        client.cookies.clear()
        client.cookies.set("monitorai_session", editor_session)
        assert client.delete(path, headers=first).status_code == 403
        assert client.post(path + "/status", headers=first, json={"status": "draft"}).status_code == 403
        client.cookies.clear()
        client.cookies.set("monitorai_session", admin_session)
        assert client.delete(path, headers=first).status_code == 204
        assert client.get(path + "/history", headers=first).status_code == 404
