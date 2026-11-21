from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def _create_architecture(client: TestClient, name: str) -> dict:
    response = client.post(
        "/api/architectures",
        json={"name": name, "provider": "azure", "environment": "draft", "status": "draft"},
    )
    assert response.status_code == 201
    return response.json()


def _create_resource_group(client: TestClient, architecture_id: str, name: str) -> dict:
    response = client.post(
        f"/api/architectures/{architecture_id}/resource-groups",
        json={"name": name, "location": "East US"},
    )
    assert response.status_code == 201
    return response.json()


def _create_resource(client: TestClient, architecture_id: str, resource_group_id: str, resource_type: str, properties: dict) -> dict:
    response = client.post(
        f"/api/architectures/{architecture_id}/resources",
        json={
            "resource_type": resource_type,
            "name": f"{resource_type}-{uuid4().hex[:6]}",
            "location": "East US",
            "resource_group_id": resource_group_id,
            "properties": properties,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_governance_compliance_summary_uses_legacy_engine():
    with TestClient(app) as client:
        architecture = _create_architecture(client, f"gov-{uuid4()}")
        rg = _create_resource_group(client, architecture["id"], "rg-gov")

        _create_resource(
            client,
            architecture["id"],
            rg["id"],
            "storage",
            {
                "region": "eastus",
                "encryption_at_rest": False,
                "logging": "disabled",
            },
        )

        response = client.post(
            f"/api/architectures/{architecture['id']}/governance-summary",
            json={"frameworks": ["hipaa"]},
        )
        assert response.status_code == 200
        payload = response.json()

        assert payload["source"] == "legacy_compliance_engine"
        assert payload["state"] == "evaluated"
        assert payload["frameworks"] == ["HIPAA"]
        assert payload["compliant"] is False
        assert any("encryption at rest" in item.lower() for item in payload["violations"])
        assert payload["total_findings"] >= 1
        assert isinstance(payload["findings"], list)
        assert any((item.get("resource_name") or "").startswith("storage-") for item in payload["findings"])
        assert payload["azure_connection_state"] in {"not_configured", "configured", "unavailable", "authentication_failure", "permission_failure", "provider_error"}

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


def test_governance_compliance_summary_defaults_to_hipaa_without_frameworks():
    with TestClient(app) as client:
        architecture = _create_architecture(client, f"gov-empty-{uuid4()}")

        response = client.post(
            f"/api/architectures/{architecture['id']}/governance-summary",
            json={},
        )
        assert response.status_code == 200
        payload = response.json()

        assert payload["source"] == "legacy_compliance_engine"
        assert payload["state"] == "evaluated"
        assert payload["frameworks"] == ["HIPAA"]
        assert payload["compliant"] is False
        assert payload["total_findings"] >= 1
        assert isinstance(payload["findings"], list)

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


def test_governance_security_summary_uses_legacy_engine():
    with TestClient(app) as client:
        architecture = _create_architecture(client, f"sec-{uuid4()}")
        rg = _create_resource_group(client, architecture["id"], "rg-sec")

        _create_resource(
            client,
            architecture["id"],
            rg["id"],
            "sql",
            {
                "network_access": "public",
                "encryption_at_rest": False,
                "nsg_applied": False,
                "db_password": "super-secret-value-123",
            },
        )

        response = client.post(f"/api/architectures/{architecture['id']}/security-summary", json={})
        assert response.status_code == 200
        payload = response.json()

        assert payload["source"] == "legacy_security_engine"
        assert payload["state"] == "evaluated"
        assert payload["total_findings"] >= 1
        assert payload["high_count"] >= 1
        assert payload["secrets_count"] >= 1
        assert payload["risk_level"] in {"low", "medium", "high", "critical"}

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


def test_governance_security_summary_empty_architecture():
    with TestClient(app) as client:
        architecture = _create_architecture(client, f"sec-empty-{uuid4()}")

        response = client.post(f"/api/architectures/{architecture['id']}/security-summary", json={})
        assert response.status_code == 200
        payload = response.json()

        assert payload["source"] == "legacy_security_engine"
        assert payload["state"] == "evaluated"
        assert payload["evaluated_resources"] == 0
        assert payload["total_findings"] == 0
        assert payload["security_score"] == 100

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204
