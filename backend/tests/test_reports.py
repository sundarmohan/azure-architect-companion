from fastapi.testclient import TestClient

from app.main import app


def _create_architecture(client: TestClient) -> dict:
    response = client.post(
        "/api/architectures",
        json={"name": "report-arch", "description": "report test", "provider": "azure", "default_region": "eastus"},
    )
    assert response.status_code == 201
    return response.json()


def _create_subscription(client: TestClient, architecture_id: str) -> dict:
    response = client.post(
        f"/api/architectures/{architecture_id}/subscriptions",
        json={"name": "sub-a", "subscription_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert response.status_code == 201
    return response.json()


def _create_resource_group(client: TestClient, architecture_id: str, subscription_id: str | None = None) -> dict:
    payload = {"name": "rg-a", "location": "East US"}
    if subscription_id:
        payload["subscription_id"] = subscription_id
    response = client.post(f"/api/architectures/{architecture_id}/resource-groups", json=payload)
    assert response.status_code == 201
    return response.json()


def _create_resource(client: TestClient, architecture_id: str, resource_group_id: str) -> dict:
    response = client.post(
        f"/api/architectures/{architecture_id}/resources",
        json={
            "resource_type": "vm",
            "name": "vm-report",
            "location": "East US",
            "resource_group_id": resource_group_id,
            "properties": {"azure_resource_id": "/subscriptions/demo/resourceGroups/rg-a/providers/Microsoft.Compute/virtualMachines/vm-report"},
        },
    )
    assert response.status_code == 201
    return response.json()


def test_executive_report_aggregates_domain_signals():
    with TestClient(app) as client:
        architecture = _create_architecture(client)
        subscription = _create_subscription(client, architecture["id"])
        group = _create_resource_group(client, architecture["id"], subscription["id"])
        _create_resource(client, architecture["id"], group["id"])

        response = client.post(
            f"/api/reports/architectures/{architecture['id']}/executive-summary",
            json={"provider": "deterministic_fallback", "include_actual_cost": True},
        )

        assert response.status_code == 200
        payload = response.json()

        assert payload["report_type"] == "architecture_executive_summary"
        assert payload["architecture"]["id"] == architecture["id"]
        assert payload["monitoring"]["state"] in {
            "live",
            "not_configured",
            "authentication_failure",
            "permission_failure",
            "azure_api_failure",
            "no_data",
            "unsupported",
        }
        assert payload["incidents"]["incident_count"] >= 0
        assert payload["cost_estimate"]["total_monthly_cost"] >= 0
        assert "governance_security" in payload
        assert "governance_compliance" in payload
        assert payload["intelligence"]["provider"] in {"openai", "gemini", "deterministic_fallback"}
        assert payload["settings_snapshot"]["provider_contract"] == ["openai", "gemini", "deterministic_fallback"]


def test_executive_report_404_for_unknown_architecture():
    with TestClient(app) as client:
        response = client.post(
            "/api/reports/architectures/00000000-0000-0000-0000-000000000000/executive-summary",
            json={},
        )
        assert response.status_code == 404
