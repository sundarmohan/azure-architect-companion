from uuid import uuid4

from fastapi.testclient import TestClient

from tests.legacy_app import app
from app.domains.cost.schemas import ArchitectureActualCostRead, ArchitectureCostEstimateRead, CostBreakdown
from app.domains.monitoring.schemas import ArchitectureMonitoringSummaryRead


class _MockMonitoringService:
    async def monitor_architecture(self, architecture, resources, **kwargs):
        return ArchitectureMonitoringSummaryRead(
            architecture_id=str(architecture.id),
            state="live",
            total_resources=len(resources),
            monitored_resources=len(resources),
            live_resources=max(0, len(resources) - 1),
            healthy_count=max(0, len(resources) - 1),
            warning_count=0,
            critical_count=0,
            no_data_count=0,
            unsupported_count=0,
            error_count=0,
            resources=[],
        )


class _MockCostService:
    async def estimate_architecture_cost(self, architecture, resources, **kwargs):
        top = resources[0] if resources else None
        top_id = str(top.id) if top else "none"
        top_name = top.name if top else "none"
        top_type = top.resource_type if top else "vm"
        return ArchitectureCostEstimateRead(
            architecture_id=str(architecture.id),
            pricing_source="schema_fallback",
            total_monthly_cost=100.0,
            total_annual_cost=1200.0,
            currency="USD",
            items=[
                {
                    "resource_id": top_id,
                    "name": top_name,
                    "resource_type": top_type,
                    "region": "eastus",
                    "monthly_cost": 85.0,
                    "annual_cost": 1020.0,
                    "quantity": 1.0,
                    "pricing_source": "schema_fallback",
                },
                {
                    "resource_id": "small-2",
                    "name": "small-2",
                    "resource_type": "storage",
                    "region": "eastus",
                    "monthly_cost": 15.0,
                    "annual_cost": 180.0,
                    "quantity": 1.0,
                    "pricing_source": "schema_fallback",
                },
            ],
            breakdown=CostBreakdown(),
            warnings=[],
            errors=[],
        )

    async def get_architecture_actual_cost(self, architecture, **kwargs):
        return ArchitectureActualCostRead(
            architecture_id=str(architecture.id),
            available=False,
            error="not configured",
        )


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


def _create_resource(
    client: TestClient,
    architecture_id: str,
    resource_type: str,
    name: str,
    resource_group_id: str | None = None,
    parent_resource_id: str | None = None,
    properties: dict | None = None,
) -> dict:
    payload = {
        "resource_type": resource_type,
        "name": name,
        "location": "East US",
        "properties": properties or {},
    }
    if resource_group_id:
        payload["resource_group_id"] = resource_group_id
    if parent_resource_id:
        payload["parent_resource_id"] = parent_resource_id

    response = client.post(f"/api/architectures/{architecture_id}/resources", json=payload)
    assert response.status_code == 201
    return response.json()


def _create_relationship(client: TestClient, architecture_id: str, source_id: str, target_id: str, relationship_type: str = "connects_to") -> dict:
    response = client.post(
        f"/api/architectures/{architecture_id}/relationships",
        json={
            "source_resource_id": source_id,
            "target_resource_id": target_id,
            "relationship_type": relationship_type,
        },
    )
    assert response.status_code == 201
    return response.json()


def _patch_services(monkeypatch):
    monkeypatch.setattr("app.domains.intelligence.service.MonitoringService", lambda: _MockMonitoringService())
    monkeypatch.setattr("app.domains.intelligence.service.CostEstimationService", lambda: _MockCostService())


def test_intelligence_normal_architecture(monkeypatch):
    _patch_services(monkeypatch)
    with TestClient(app) as client:
        architecture = _create_architecture(client, f"intel-normal-{uuid4()}")
        rg = _create_resource_group(client, architecture["id"], "rg-intel")

        vnet = _create_resource(client, architecture["id"], "vnet", "vnet-main", rg["id"], properties={"private_endpoints": True})
        subnet = _create_resource(client, architecture["id"], "subnet", "subnet-main", rg["id"], parent_resource_id=vnet["id"])
        _create_relationship(client, architecture["id"], vnet["id"], subnet["id"], "contains")

        response = client.post(f"/api/architectures/{architecture['id']}/intelligence-analysis", json={})
        assert response.status_code == 200
        payload = response.json()

        assert payload["state"] in {"success", "insufficient_data"}
        assert payload["source"] == "monitorai_deterministic_intelligence"
        assert "severity_summary" in payload

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


def test_intelligence_empty_architecture_returns_no_data(monkeypatch):
    _patch_services(monkeypatch)
    with TestClient(app) as client:
        architecture = _create_architecture(client, f"intel-empty-{uuid4()}")

        response = client.post(f"/api/architectures/{architecture['id']}/intelligence-analysis", json={})
        assert response.status_code == 200
        payload = response.json()

        assert payload["state"] == "no_data"
        assert payload["finding_count"] == 0

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


def test_intelligence_isolated_resource_finding(monkeypatch):
    _patch_services(monkeypatch)
    with TestClient(app) as client:
        architecture = _create_architecture(client, f"intel-iso-{uuid4()}")
        rg = _create_resource_group(client, architecture["id"], "rg-iso")
        _create_resource(client, architecture["id"], "vm", "vm-alone", rg["id"])

        response = client.post(f"/api/architectures/{architecture['id']}/intelligence-analysis", json={})
        payload = response.json()
        ids = {item["id"] for item in payload["findings"]}
        assert "isolated-resources" in ids

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


def test_intelligence_missing_hierarchy_condition(monkeypatch):
    _patch_services(monkeypatch)
    with TestClient(app) as client:
        architecture = _create_architecture(client, f"intel-hier-{uuid4()}")
        rg = _create_resource_group(client, architecture["id"], "rg-hier")
        _create_resource(client, architecture["id"], "subnet", "subnet-orphan", rg["id"])

        response = client.post(f"/api/architectures/{architecture['id']}/intelligence-analysis", json={})
        payload = response.json()
        ids = {item["id"] for item in payload["findings"]}
        assert "subnet-missing-vnet-link" in ids

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


def test_intelligence_monitoring_coverage_finding(monkeypatch):
    _patch_services(monkeypatch)
    with TestClient(app) as client:
        architecture = _create_architecture(client, f"intel-mon-{uuid4()}")
        rg = _create_resource_group(client, architecture["id"], "rg-mon")
        _create_resource(client, architecture["id"], "vm", "vm-mon-1", rg["id"])
        _create_resource(client, architecture["id"], "vm", "vm-mon-2", rg["id"])

        response = client.post(f"/api/architectures/{architecture['id']}/intelligence-analysis", json={})
        payload = response.json()
        ids = {item["id"] for item in payload["findings"]}
        assert "monitoring-coverage-gap" in ids

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


def test_intelligence_severity_and_recommendations(monkeypatch):
    _patch_services(monkeypatch)
    with TestClient(app) as client:
        architecture = _create_architecture(client, f"intel-sev-{uuid4()}")
        rg = _create_resource_group(client, architecture["id"], "rg-sev")
        _create_resource(
            client,
            architecture["id"],
            "sql",
            "sql-risk",
            rg["id"],
            properties={"network_access": "public", "encryption_at_rest": False, "db_password": "hardcoded-secret-123"},
        )

        response = client.post(f"/api/architectures/{architecture['id']}/intelligence-analysis", json={})
        payload = response.json()
        assert payload["severity_summary"]["high"] >= 1 or payload["severity_summary"]["critical"] >= 1
        assert len(payload["recommendations"]) >= 1

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


def test_intelligence_invalid_architecture_returns_404(monkeypatch):
    _patch_services(monkeypatch)
    with TestClient(app) as client:
        response = client.post(f"/api/architectures/{uuid4()}/intelligence-analysis", json={})
        assert response.status_code == 404


def test_intelligence_output_is_deterministic(monkeypatch):
    _patch_services(monkeypatch)
    with TestClient(app) as client:
        architecture = _create_architecture(client, f"intel-deterministic-{uuid4()}")
        rg = _create_resource_group(client, architecture["id"], "rg-det")
        _create_resource(client, architecture["id"], "vm", "vm-det", rg["id"], properties={"network_access": "public"})

        first = client.post(f"/api/architectures/{architecture['id']}/intelligence-analysis", json={})
        second = client.post(f"/api/architectures/{architecture['id']}/intelligence-analysis", json={})
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["findings"] == second.json()["findings"]
        assert first.json()["recommendations"] == second.json()["recommendations"]

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


def test_intelligence_response_schema_shape(monkeypatch):
    _patch_services(monkeypatch)
    with TestClient(app) as client:
        architecture = _create_architecture(client, f"intel-schema-{uuid4()}")
        rg = _create_resource_group(client, architecture["id"], "rg-schema")
        _create_resource(client, architecture["id"], "vm", "vm-schema", rg["id"])

        response = client.post(f"/api/architectures/{architecture['id']}/intelligence-analysis", json={})
        payload = response.json()
        required = {
            "architecture_id",
            "source",
            "state",
            "overall_assessment",
            "finding_count",
            "severity_summary",
            "observed_facts",
            "rca",
            "incident_correlations",
            "analysis_confidence",
            "limitations",
            "findings",
            "recommendations",
        }
        assert required.issubset(payload.keys())

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204
