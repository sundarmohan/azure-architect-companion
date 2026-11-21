from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.domains.cost.schemas import ArchitectureActualCostRead, ArchitectureCostEstimateRead, CostBreakdown
from app.domains.intelligence.providers import IntelligenceContext
from app.domains.intelligence.service import IntelligenceService
from app.domains.monitoring.schemas import ArchitectureMonitoringSummaryRead, ResourceMonitoringRead
from app.domains.settings.service import SettingsService


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


class _MockMonitoringServiceWithIncident:
    async def monitor_architecture(self, architecture, resources, **kwargs):
        incident_resource_id = str(resources[0].id) if resources else "r1"
        incident_resource_name = resources[0].name if resources else "vm-1"
        incident_resource_type = resources[0].resource_type if resources else "vm"
        return ArchitectureMonitoringSummaryRead(
            architecture_id=str(architecture.id),
            state="azure_api_failure",
            total_resources=max(1, len(resources)),
            monitored_resources=max(1, len(resources)),
            live_resources=0,
            healthy_count=0,
            warning_count=0,
            critical_count=1,
            no_data_count=0,
            unsupported_count=0,
            error_count=1,
            resources=[
                ResourceMonitoringRead(
                    architecture_id=str(architecture.id),
                    resource_id=incident_resource_id,
                    resource_name=incident_resource_name,
                    resource_type=incident_resource_type,
                    state="azure_api_failure",
                    live=False,
                    health_status="unavailable",
                    metrics=[],
                    message="Telemetry query failed",
                )
            ],
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
                }
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


def _patch_internal_services(monkeypatch):
    monkeypatch.setattr("app.domains.intelligence.service.MonitoringService", lambda: _MockMonitoringService())
    monkeypatch.setattr("app.domains.intelligence.service.CostEstimationService", lambda: _MockCostService())


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


def _create_resource(client: TestClient, architecture_id: str, resource_group_id: str, name: str = "vm-1") -> dict:
    response = client.post(
        f"/api/architectures/{architecture_id}/resources",
        json={"resource_type": "vm", "name": name, "location": "East US", "resource_group_id": resource_group_id},
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch):
    SettingsService.reset_runtime_state()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    with TestClient(app) as cleanup_client:
        cleanup_client.delete("/api/settings/providers/openai")
        cleanup_client.delete("/api/settings/providers/gemini")


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _mock_openai(monkeypatch, status_code: int = 200, payload: dict | None = None):
    class _Response:
        def __init__(self):
            self.status_code = status_code
            self.content = b"ok"

        def json(self):
            return payload or {
                "choices": [
                    {
                        "message": {
                            "content": '{"overall_assessment":"AI assessment","findings":[{"title":"Public exposure","priority":"high","category":"security","description":"Public endpoint detected","recommendation":"Restrict exposure","explanation":"Public endpoint can increase attack surface","affected_resources":["vm-1"]}],"recommendations":[{"title":"Enable private access","priority":"high","category":"security","recommendation":"Use private endpoints","explanation":"Reduces external exposure","affected_resources":["vm-1"]}],"risks":[{"title":"Internet exposure","priority":"high","explanation":"Public access path present","impact":"Higher threat likelihood"}]}'
                        }
                    }
                ]
            }

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            return _Response()

    monkeypatch.setattr("app.domains.intelligence.providers.httpx.AsyncClient", _Client)


def test_v214_deterministic_fallback(client: TestClient, monkeypatch):
    _patch_internal_services(monkeypatch)
    architecture = _create_architecture(client, f"v214-det-{uuid4()}")
    rg = _create_resource_group(client, architecture["id"], "rg-det")
    _create_resource(client, architecture["id"], rg["id"], "vm-det")

    response = client.post(f"/api/architectures/{architecture['id']}/intelligence-analysis", json={"provider": "deterministic_fallback"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "deterministic_fallback"
    assert payload["source"] == "monitorai_deterministic_intelligence"


def test_v214_openai_not_configured(client: TestClient, monkeypatch):
    _patch_internal_services(monkeypatch)
    architecture = _create_architecture(client, f"v214-openai-missing-{uuid4()}")
    rg = _create_resource_group(client, architecture["id"], "rg-openai")
    _create_resource(client, architecture["id"], rg["id"], "vm-openai")

    response = client.post(f"/api/architectures/{architecture['id']}/intelligence-analysis", json={"provider": "openai"})
    payload = response.json()
    assert payload["source"] == "monitorai_deterministic_intelligence"
    assert payload["error_state"] == "not_configured"


def test_v214_gemini_not_configured(client: TestClient, monkeypatch):
    _patch_internal_services(monkeypatch)
    architecture = _create_architecture(client, f"v214-gemini-missing-{uuid4()}")
    rg = _create_resource_group(client, architecture["id"], "rg-gemini")
    _create_resource(client, architecture["id"], rg["id"], "vm-gemini")

    response = client.post(f"/api/architectures/{architecture['id']}/intelligence-analysis", json={"provider": "gemini"})
    payload = response.json()
    assert payload["source"] == "monitorai_deterministic_intelligence"
    assert payload["error_state"] == "not_configured"


def test_v214_provider_selection_prefers_configured_openai(client: TestClient, monkeypatch):
    _patch_internal_services(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    _mock_openai(monkeypatch, 200)

    client.put("/api/settings/providers/openai", json={"api_key": "sk-openai-test"})

    architecture = _create_architecture(client, f"v214-openai-selected-{uuid4()}")
    rg = _create_resource_group(client, architecture["id"], "rg-openai")
    _create_resource(client, architecture["id"], rg["id"], "vm-openai")

    response = client.post(f"/api/architectures/{architecture['id']}/intelligence-analysis", json={})
    payload = response.json()
    assert payload["provider"] == "openai"
    assert payload["source"] == "openai"


def test_v214_controlled_authentication_failure(client: TestClient, monkeypatch):
    _patch_internal_services(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    _mock_openai(monkeypatch, 401)
    client.put("/api/settings/providers/openai", json={"api_key": "sk-openai-test"})

    architecture = _create_architecture(client, f"v214-openai-auth-{uuid4()}")
    rg = _create_resource_group(client, architecture["id"], "rg-auth")
    _create_resource(client, architecture["id"], rg["id"], "vm-auth")

    response = client.post(f"/api/architectures/{architecture['id']}/intelligence-analysis", json={"provider": "openai"})
    payload = response.json()
    assert payload["source"] == "monitorai_deterministic_intelligence"
    assert payload["error_state"] == "authentication_failure"


def test_v214_controlled_provider_failure(client: TestClient, monkeypatch):
    _patch_internal_services(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    _mock_openai(monkeypatch, 500)
    client.put("/api/settings/providers/openai", json={"api_key": "sk-openai-test"})

    architecture = _create_architecture(client, f"v214-openai-fail-{uuid4()}")
    rg = _create_resource_group(client, architecture["id"], "rg-fail")
    _create_resource(client, architecture["id"], rg["id"], "vm-fail")

    response = client.post(f"/api/architectures/{architecture['id']}/intelligence-analysis", json={"provider": "openai"})
    payload = response.json()
    assert payload["source"] == "monitorai_deterministic_intelligence"
    assert payload["error_state"] == "provider_error"


def test_v214_response_schema_and_secret_redaction(client: TestClient, monkeypatch):
    _patch_internal_services(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    _mock_openai(monkeypatch, 200)
    secret = "sk-secret-v214-redaction"
    client.put("/api/settings/providers/openai", json={"api_key": secret})

    architecture = _create_architecture(client, f"v214-schema-{uuid4()}")
    rg = _create_resource_group(client, architecture["id"], "rg-schema")
    _create_resource(client, architecture["id"], rg["id"], "vm-schema")

    response = client.post(f"/api/architectures/{architecture['id']}/intelligence-analysis", json={})
    payload = response.json()
    required = {
        "status",
        "source",
        "provider",
        "findings",
        "recommendations",
        "risks",
        "generated_at",
    }
    assert required.issubset(payload.keys())
    assert secret not in response.text
    assert "api_key" not in payload


def test_v214_compact_context_generation():
    service = IntelligenceService()
    context = IntelligenceContext(
        architecture_id="a1",
        architecture_name="Arch",
        architecture_provider="azure",
        resources=[{"id": "r1", "name": "vm-1", "resource_type": "vm", "location": "eastus", "resource_group_id": "g1"}],
        relationships=[{"source_resource_id": "r1", "target_resource_id": "r2", "relationship_type": "connects_to"}],
        resource_groups=[{"id": "g1", "name": "rg-1"}],
        subscriptions=[{"id": "s1", "name": "sub-1"}],
        monitoring_summary={"state": "live", "total_resources": 1, "live_resources": 1},
        cost_estimate={"pricing_source": "azure_retail_prices", "total_monthly_cost": 12.4},
        actual_cost={"pricing_source": "azure_cost_management", "available": False},
        compliance_summary={"frameworks": ["HIPAA"], "compliant": True, "violations": []},
        security_summary={"risk_level": "low", "critical_count": 0, "high_count": 0, "secrets_count": 0},
        incident_summary={"incident_count": 0, "incidents": []},
    )
    compact = service.build_compact_context(context)
    assert compact["architecture"]["resources"] == 1
    assert compact["monitoring"]["state"] == "live"
    assert compact["cost"]["estimate_source"] == "azure_retail_prices"


def test_v216_rca_and_incident_correlation(client: TestClient, monkeypatch):
    monkeypatch.setattr("app.domains.intelligence.service.MonitoringService", lambda: _MockMonitoringServiceWithIncident())
    monkeypatch.setattr("app.domains.intelligence.service.CostEstimationService", lambda: _MockCostService())

    architecture = _create_architecture(client, f"v216-rca-{uuid4()}")
    rg = _create_resource_group(client, architecture["id"], "rg-rca")
    _create_resource(client, architecture["id"], rg["id"], "vm-rca")

    response = client.post(
        f"/api/architectures/{architecture['id']}/intelligence-analysis",
        json={"provider": "deterministic_fallback"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["observed_facts"]) >= 1
    assert len(payload["incident_correlations"]) >= 1
    assert len(payload["rca"]) >= 1
    assert payload["rca"][0]["probable_cause"]


def test_v214_ai_cannot_mutate_architecture_state(client: TestClient, monkeypatch):
    _patch_internal_services(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    _mock_openai(monkeypatch, 200)
    client.put("/api/settings/providers/openai", json={"api_key": "sk-openai-test"})

    architecture = _create_architecture(client, f"v214-immutability-{uuid4()}")
    rg = _create_resource_group(client, architecture["id"], "rg-immut")
    vm = _create_resource(client, architecture["id"], rg["id"], "vm-immut")
    db = _create_resource(client, architecture["id"], rg["id"], "db-immut")

    rel = client.post(
        f"/api/architectures/{architecture['id']}/relationships",
        json={"source_resource_id": vm["id"], "target_resource_id": db["id"], "relationship_type": "connects_to"},
    )
    assert rel.status_code == 201

    before_resources = client.get(f"/api/architectures/{architecture['id']}/resources").json()
    before_relationships = client.get(f"/api/architectures/{architecture['id']}/relationships").json()

    response = client.post(f"/api/architectures/{architecture['id']}/intelligence-analysis", json={})
    assert response.status_code == 200

    after_resources = client.get(f"/api/architectures/{architecture['id']}/resources").json()
    after_relationships = client.get(f"/api/architectures/{architecture['id']}/relationships").json()

    assert len(before_resources) == len(after_resources)
    assert len(before_relationships) == len(after_relationships)