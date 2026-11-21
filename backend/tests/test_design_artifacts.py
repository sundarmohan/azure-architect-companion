import json
from uuid import uuid4
from xml.etree import ElementTree as ET

from fastapi.testclient import TestClient

from app.main import app


def test_client_scoped_artifacts_are_downloads_and_filter_secret_properties(monkeypatch):
    username = "phase-one-admin"
    password = "A phase-one password"
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_USERNAME", username)
    monkeypatch.setenv("MONITORAI_BOOTSTRAP_PASSWORD", password)

    write_header = {"X-MonitorAI-Request": "1"}
    with TestClient(app, base_url="https://testserver") as client:
        assert client.post("/api/auth/login", headers=write_header,
                           json={"username": username, "password": password}).status_code == 200
        first = client.post("/api/auth/clients", headers=write_header, json={"name": str(uuid4())}).json()
        second = client.post("/api/auth/clients", headers=write_header, json={"name": str(uuid4())}).json()
        headers = {**write_header, "X-Client-ID": first["client_id"]}

        design = client.post("/api/architectures", headers=headers,
                             json={"name": "Azure demo", "project": "Export review"})
        assert design.status_code == 201, design.text
        path = f"/api/architectures/{design.json()['id']}"
        group = client.post(path + "/resource-groups", headers=headers,
                            json={"name": "rg-review", "location": "East US"})
        assert group.status_code == 201, group.text
        group_id = group.json()["id"]
        vnet = client.post(path + "/resources", headers=headers, json={
            "name": "vnet-demo", "resource_type": "vnet", "resource_group_id": group_id,
            "properties": {"address_space": ["10.4.0.0/16"], "client_secret": "should-not-be-exported"},
        })
        assert vnet.status_code == 201, vnet.text
        subnet = client.post(path + "/resources", headers=headers, json={
            "name": "subnet-demo", "resource_type": "subnet", "resource_group_id": group_id,
            "parent_resource_id": vnet.json()["id"], "properties": {"address_prefix": "10.4.1.0/24"},
        })
        assert subnet.status_code == 201, subnet.text
        unsupported = client.post(path + "/resources", headers=headers, json={
            "name": "<script>example</script>", "resource_type": "user",
        })
        assert unsupported.status_code == 201, unsupported.text

        findings = client.get(path + "/validation", headers=headers)
        assert findings.status_code == 200, findings.text
        assert not any(item["severity"] == "error" for item in findings.json()["findings"])
        data = client.get(path + "/exports/definition", headers=headers)
        assert data.status_code == 200, data.text
        assert "attachment" in data.headers["content-disposition"]
        assert "should-not-be-exported" not in data.text
        assert data.json()["architecture"]["project"] == "Export review"
        assert any(item["properties"] == {"address_space": ["10.4.0.0/16"]} for item in data.json()["resources"])

        svg = client.get(path + "/exports/diagram", headers=headers)
        assert svg.status_code == 200, svg.text
        assert "<script>" not in svg.text and "&lt;script&gt;" in svg.text
        assert svg.headers["content-type"].startswith("image/svg+xml")
        root = ET.fromstring(svg.content)
        assert root.find("{http://www.w3.org/2000/svg}line") is not None

        tf = client.get(path + "/exports/terraform", headers=headers)
        assert tf.status_code == 200, tf.text
        assert "should-not-be-exported" not in tf.text
        generated = tf.json()
        assert set(generated["resource"]) == {"azurerm_resource_group", "azurerm_virtual_network", "azurerm_subnet"}
        subnet_arguments = next(iter(generated["resource"]["azurerm_subnet"].values()))
        assert subnet_arguments["address_prefixes"] == ["10.4.1.0/24"]
        assert subnet_arguments["virtual_network_name"].startswith("${azurerm_virtual_network.")
        assert generated["output"]["monitorai_export_scope"]["value"]["omitted_resources"][0]["id"] == unsupported.json()["id"]

        playbook_request = {"packages": ["nginx"], "services": [{"name": "nginx", "enabled": True, "state": "started"}]}
        ansible = client.post(path + "/exports/ansible", headers=headers, json=playbook_request)
        assert ansible.status_code == 200, ansible.text
        play = json.loads(ansible.text.split("\n", 1)[1])[0]
        assert play["hosts"] == "azure_managed_hosts"
        assert play["tasks"][0]["ansible.builtin.package"] == {"name": "nginx", "state": "present"}
        assert play["tasks"][1]["ansible.builtin.service"]["enabled"] is True
        invalid = client.post(path + "/exports/ansible", headers=headers, json={"packages": ["{{ unsafe }}"]})
        assert invalid.status_code == 422

        wrong_context = {**headers, "X-Client-ID": second["client_id"]}
        for endpoint in ("validation", "exports/definition", "exports/diagram", "exports/terraform"):
            assert client.get(f"{path}/{endpoint}", headers=wrong_context).status_code == 404
        assert client.post(path + "/exports/ansible", headers=wrong_context, json=playbook_request).status_code == 404

        updated = client.put(f"{path}/resources/{subnet.json()['id']}", headers=headers,
                             json={"properties": {"address_prefix": "10.6.1.0/24"}})
        assert updated.status_code == 200, updated.text
        findings = client.get(path + "/validation", headers=headers).json()["findings"]
        assert any(item["severity"] == "error" and item["code"] == "subnet_outside_vnet" for item in findings)
        partial = client.get(path + "/exports/terraform", headers=headers).json()
        assert "azurerm_subnet" not in partial["resource"]


def test_terraform_literal_escapes_interpolation_and_directives():
    from app.domains.architecture.artifacts import tf_literal

    assert tf_literal("${var.hidden} %{ if true }") == "$${var.hidden} %%{ if true }"
