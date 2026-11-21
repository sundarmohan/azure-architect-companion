from datetime import datetime, timezone
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.legacy_app import app
from app.domains.architecture.models import Architecture, ArchitectureResource
from app.domains.monitoring.schemas import ArchitectureMonitoringSummaryRead, ResourceMonitoringRead
from app.domains.monitoring.service import MonitoringService


class _StateAdapter:
    def __init__(self, state: str, message: str | None = None, metrics: list[dict] | None = None, health_status: str | None = None):
        self.state = state
        self.message = message
        self.metrics = metrics or []
        self.health_status = health_status

    async def get_resource_monitoring(self, **kwargs):
        return {
            "state": self.state,
            "message": self.message,
            "health_status": self.health_status,
            "metrics": self.metrics,
        }


def _create_architecture(client: TestClient, name: str) -> dict:
    response = client.post(
        "/api/architectures",
        json={"name": name, "provider": "azure", "environment": "draft", "status": "draft"},
    )
    assert response.status_code == 201
    return response.json()


def _create_resource(client: TestClient, architecture_id: str, resource_type: str = "vm") -> dict:
    group = client.post(
        f"/api/architectures/{architecture_id}/resource-groups",
        json={"name": "rg-monitor", "location": "East US"},
    )
    assert group.status_code == 201
    resource = client.post(
        f"/api/architectures/{architecture_id}/resources",
        json={
            "resource_type": resource_type,
            "name": f"{resource_type}-monitor",
            "location": "East US",
            "resource_group_id": group.json()["id"],
            "properties": {
                "azure_resource_id": "/subscriptions/sub-1/resourceGroups/rg-monitor/providers/Microsoft.Compute/virtualMachines/vm-monitor"
            },
        },
    )
    assert resource.status_code == 201
    return resource.json()


def test_monitoring_service_states_and_no_fabrication():
    architecture = Architecture(name="a", provider="azure", environment="draft", status="draft")
    resource = ArchitectureResource(
        architecture_id=architecture.id,
        resource_type="vm",
        name="vm-1",
        location="eastus",
        properties={"azure_resource_id": "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1"},
    )

    start = datetime.now(timezone.utc)
    end = datetime.now(timezone.utc)

    for state in [
        "not_configured",
        "authentication_failure",
        "permission_failure",
        "azure_api_failure",
        "no_data",
    ]:
        service = MonitoringService(adapter=_StateAdapter(state=state, message="state-message"))
        result = __import__("asyncio").run(
            service.monitor_resource(
                architecture=architecture,
                resource=resource,
                resource_groups=[],
                subscriptions=[],
                start_time=start,
                end_time=end,
                interval="PT1H",
            )
        )
        assert result.state == state
        assert result.live is False
        assert result.metrics == []


def test_monitoring_service_unsupported_resource_and_missing_azure_id():
    architecture = Architecture(name="a", provider="azure", environment="draft", status="draft")
    resource = ArchitectureResource(
        architecture_id=architecture.id,
        resource_type="vm",
        name="vm-1",
        location="eastus",
        properties={},
    )

    service = MonitoringService(adapter=_StateAdapter(state="live"))
    result = __import__("asyncio").run(
        service.monitor_resource(
            architecture=architecture,
            resource=resource,
            resource_groups=[],
            subscriptions=[],
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            interval="PT1H",
        )
    )
    assert result.state == "unsupported"


def test_monitoring_service_successful_normalized_response():
    architecture = Architecture(name="a", provider="azure", environment="draft", status="draft")
    resource = ArchitectureResource(
        architecture_id=architecture.id,
        resource_type="vm",
        name="vm-1",
        location="eastus",
        properties={"azure_resource_id": "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1"},
    )

    adapter = _StateAdapter(
        state="live",
        health_status="Available",
        metrics=[
            {
                "name": "Percentage CPU",
                "unit": "Percent",
                "aggregation": "average",
                "points": [{"timestamp": "2026-01-01T00:00:00Z", "value": 22.5}],
            }
        ],
    )
    service = MonitoringService(adapter=adapter)
    result = __import__("asyncio").run(
        service.monitor_resource(
            architecture=architecture,
            resource=resource,
            resource_groups=[],
            subscriptions=[],
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            interval="PT1H",
        )
    )
    assert result.state == "live"
    assert result.live is True
    assert result.health_status == "Available"
    assert len(result.metrics) == 1


def test_monitoring_api_resource_ownership_validation():
    with TestClient(app) as client:
        arch_a = _create_architecture(client, f"mon-a-{uuid4()}")
        arch_b = _create_architecture(client, f"mon-b-{uuid4()}")

        resource_b = _create_resource(client, arch_b["id"], "vm")

        response = client.post(
            f"/api/architectures/{arch_a['id']}/resources/{resource_b['id']}/monitoring",
            json={},
        )
        assert response.status_code == 404

        cleanup_a = client.delete(f"/api/architectures/{arch_a['id']}")
        cleanup_b = client.delete(f"/api/architectures/{arch_b['id']}")
        assert cleanup_a.status_code == 204
        assert cleanup_b.status_code == 204


def test_monitoring_api_success_with_mock_adapter(monkeypatch):
    class _MockAdapter:
        async def get_resource_monitoring(self, **kwargs):
            return {
                "state": "live",
                "message": None,
                "health_status": "Available",
                "metrics": [
                    {
                        "name": "Percentage CPU",
                        "unit": "Percent",
                        "aggregation": "average",
                        "points": [{"timestamp": "2026-01-01T00:00:00Z", "value": 30.0}],
                    }
                ],
            }

    monkeypatch.setattr(
        "app.domains.architecture.routes.MonitoringService",
        lambda: MonitoringService(adapter=_MockAdapter()),
    )

    with TestClient(app) as client:
        architecture = _create_architecture(client, f"mon-live-{uuid4()}")
        resource = _create_resource(client, architecture["id"], "vm")

        response = client.post(
            f"/api/architectures/{architecture['id']}/resources/{resource['id']}/monitoring",
            json={},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["state"] == "live"
        assert payload["live"] is True
        assert payload["health_status"] == "Available"
        assert len(payload["metrics"]) == 1

        summary = client.post(f"/api/architectures/{architecture['id']}/monitoring-summary", json={})
        assert summary.status_code == 200
        summary_payload = summary.json()
        assert summary_payload["state"] == "live"
        assert summary_payload["live_resources"] >= 1

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


def test_monitoring_architecture_collection_is_bounded(monkeypatch):
    class _SlowAdapter:
        async def get_resource_monitoring(self, **kwargs):
            _ = kwargs
            await __import__("asyncio").sleep(0.12)
            return {
                "state": "live",
                "message": None,
                "health_status": "Available",
                "metrics": [],
            }

    monkeypatch.setenv("MONITORING_MAX_CONCURRENCY", "4")
    monkeypatch.setenv("MONITORING_RESOURCE_TIMEOUT_SECONDS", "0.05")

    architecture = Architecture(name="bounded", provider="azure", environment="draft", status="draft")
    resources = []
    for idx in range(8):
        resources.append(
            ArchitectureResource(
                architecture_id=architecture.id,
                resource_type="vm",
                name=f"vm-{idx}",
                location="eastus",
                properties={
                    "azure_resource_id": f"/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-{idx}"
                },
            )
        )

    service = MonitoringService(adapter=_SlowAdapter())
    started = time.perf_counter()
    result = __import__("asyncio").run(
        service.monitor_architecture(
            architecture=architecture,
            resources=resources,
            resource_groups=[],
            subscriptions=[],
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            interval="PT1H",
        )
    )
    elapsed = time.perf_counter() - started

    assert result.total_resources == 8
    assert len(result.resources) == 8
    assert all(item.state in {"live", "azure_api_failure"} for item in result.resources)
    # With bounded per-resource timeout + parallel fan-out, this should complete quickly.
    assert elapsed < 0.35


def test_monitoring_api_not_configured_with_mock_adapter(monkeypatch):
    class _MockAdapter:
        async def get_resource_monitoring(self, **kwargs):
            return {
                "state": "not_configured",
                "message": "credentials missing",
                "health_status": None,
                "metrics": [],
            }

    monkeypatch.setattr(
        "app.domains.architecture.routes.MonitoringService",
        lambda: MonitoringService(adapter=_MockAdapter()),
    )

    with TestClient(app) as client:
        architecture = _create_architecture(client, f"mon-nc-{uuid4()}")
        resource = _create_resource(client, architecture["id"], "vm")

        response = client.post(
            f"/api/architectures/{architecture['id']}/resources/{resource['id']}/monitoring",
            json={},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["state"] == "not_configured"
        assert payload["live"] is False

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


def test_monitoring_incident_summary_uses_legacy_incident_engine(monkeypatch):
    class _MockService:
        async def monitor_architecture(self, architecture, resources, **kwargs):
            return ArchitectureMonitoringSummaryRead(
                architecture_id=str(architecture.id),
                state="azure_api_failure",
                total_resources=len(resources),
                monitored_resources=len(resources),
                live_resources=1,
                healthy_count=0,
                warning_count=0,
                critical_count=1,
                no_data_count=0,
                unsupported_count=0,
                error_count=1,
                resources=[
                    ResourceMonitoringRead(
                        architecture_id=str(architecture.id),
                        resource_id=str(resources[0].id),
                        resource_name=resources[0].name,
                        resource_type=resources[0].resource_type,
                        state="not_configured",
                        live=False,
                        message="credentials missing",
                    ),
                    ResourceMonitoringRead(
                        architecture_id=str(architecture.id),
                        resource_id=str(resources[0].id),
                        resource_name=resources[0].name,
                        resource_type=resources[0].resource_type,
                        state="live",
                        live=True,
                        health_status="Unavailable",
                    ),
                ],
            )

    monkeypatch.setattr("app.domains.architecture.routes.MonitoringService", lambda: _MockService())

    with TestClient(app) as client:
        architecture = _create_architecture(client, f"mon-inc-{uuid4()}")
        _create_resource(client, architecture["id"], "vm")

        first = client.post(f"/api/architectures/{architecture['id']}/incident-summary", json={})
        assert first.status_code == 200
        payload = first.json()
        assert payload["source"] == "legacy_incident_engine"
        assert payload["incident_count"] == 2
        assert payload["critical_count"] == 1
        assert payload["medium_count"] == 1
        assert all(item["status"] == "open" for item in payload["incidents"])

        second = client.post(f"/api/architectures/{architecture['id']}/incident-summary", json={})
        assert second.status_code == 200
        second_payload = second.json()
        assert second_payload["incident_count"] == 2

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


def test_monitoring_incident_summary_no_signals(monkeypatch):
    class _MockService:
        async def monitor_architecture(self, architecture, resources, **kwargs):
            return ArchitectureMonitoringSummaryRead(
                architecture_id=str(architecture.id),
                state="unsupported",
                total_resources=len(resources),
                monitored_resources=len(resources),
                live_resources=0,
                healthy_count=0,
                warning_count=0,
                critical_count=0,
                no_data_count=0,
                unsupported_count=len(resources),
                error_count=0,
                resources=[
                    ResourceMonitoringRead(
                        architecture_id=str(architecture.id),
                        resource_id=str(resources[0].id),
                        resource_name=resources[0].name,
                        resource_type=resources[0].resource_type,
                        state="unsupported",
                        live=False,
                    )
                ],
            )

    monkeypatch.setattr("app.domains.architecture.routes.MonitoringService", lambda: _MockService())

    with TestClient(app) as client:
        architecture = _create_architecture(client, f"mon-inc-empty-{uuid4()}")
        _create_resource(client, architecture["id"], "vm")

        response = client.post(f"/api/architectures/{architecture['id']}/incident-summary", json={})
        assert response.status_code == 200
        payload = response.json()
        assert payload["incident_count"] == 0
        assert payload["incidents"] == []

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


def test_monitoring_incident_lifecycle_and_alert_status(monkeypatch):
    class _MockService:
        async def monitor_architecture(self, architecture, resources, **kwargs):
            return ArchitectureMonitoringSummaryRead(
                architecture_id=str(architecture.id),
                state="azure_api_failure",
                total_resources=len(resources),
                monitored_resources=len(resources),
                live_resources=1,
                healthy_count=0,
                warning_count=0,
                critical_count=1,
                no_data_count=0,
                unsupported_count=0,
                error_count=1,
                resources=[
                    ResourceMonitoringRead(
                        architecture_id=str(architecture.id),
                        resource_id=str(resources[0].id),
                        resource_name=resources[0].name,
                        resource_type=resources[0].resource_type,
                        state="not_configured",
                        live=False,
                        message="credentials missing",
                    )
                ],
            )

    monkeypatch.setattr("app.domains.architecture.routes.MonitoringService", lambda: _MockService())

    with TestClient(app) as client:
        architecture = _create_architecture(client, f"mon-inc-life-{uuid4()}")
        _create_resource(client, architecture["id"], "vm")

        response = client.post(f"/api/architectures/{architecture['id']}/incident-summary", json={})
        assert response.status_code == 200
        payload = response.json()
        assert payload["incident_count"] == 1
        incident_id = payload["incidents"][0]["incident_id"]

        listed = client.get(f"/api/architectures/{architecture['id']}/incidents")
        assert listed.status_code == 200
        listed_payload = listed.json()
        assert len(listed_payload) == 1
        assert listed_payload[0]["incident_id"] == incident_id
        assert len(listed_payload[0]["timeline"]) >= 1

        updated = client.put(
            f"/api/architectures/{architecture['id']}/incidents/{incident_id}/status",
            json={"status": "acknowledged", "actor": "test_operator", "comment": "triaged"},
        )
        assert updated.status_code == 200
        updated_payload = updated.json()
        assert updated_payload["status"] == "acknowledged"
        assert any(item["event_type"] == "status_changed" for item in updated_payload["timeline"])

        alerts = client.post(f"/api/architectures/{architecture['id']}/alerts-summary", json={})
        assert alerts.status_code == 200
        alerts_payload = alerts.json()
        assert alerts_payload["alert_count"] >= 1
        assert any(item["status"] == "acknowledged" for item in alerts_payload["alerts"])

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


def test_unused_resource_summary_not_configured(monkeypatch):
    class _MockService:
        async def detect_unused_resources(self, architecture, resources, lookback_days, azure_connection_state, azure_connection_message):
            _ = architecture, resources, lookback_days, azure_connection_state, azure_connection_message
            return {
                "architecture_id": str(architecture.id),
                "source": "legacy_idle_detector",
                "state": "not_configured",
                "lookback_days": 7,
                "analysis_start_time": "2026-01-01T00:00:00+00:00",
                "analysis_end_time": "2026-01-08T00:00:00+00:00",
                "total_checked": 1,
                "total_unused": 0,
                "estimated_monthly_waste": 0.0,
                "azure_connection_state": "not_configured",
                "azure_connection_message": "Azure credentials are not configured.",
                "message": "Azure credentials are not configured for monitoring",
                "unused_resources": [],
            }

    monkeypatch.setattr("app.domains.architecture.routes.MonitoringService", lambda: _MockService())

    with TestClient(app) as client:
        architecture = _create_architecture(client, f"mon-unused-nc-{uuid4()}")
        _create_resource(client, architecture["id"], "vm")

        response = client.post(f"/api/architectures/{architecture['id']}/unused-resources", json={})
        assert response.status_code == 200
        payload = response.json()
        assert payload["state"] == "not_configured"
        assert payload["total_unused"] == 0
        assert payload["azure_connection_state"] == "not_configured"

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


@pytest.mark.parametrize("lookback_days", [7, 14, 30])
def test_unused_resource_summary_with_lookback(monkeypatch, lookback_days):
    class _MockService:
        async def detect_unused_resources(self, architecture, resources, lookback_days, azure_connection_state, azure_connection_message):
            _ = resources, azure_connection_state, azure_connection_message
            return {
                "architecture_id": str(architecture.id),
                "source": "legacy_idle_detector",
                "state": "evaluated",
                "lookback_days": lookback_days,
                "analysis_start_time": "2026-01-01T00:00:00+00:00",
                "analysis_end_time": "2026-01-15T00:00:00+00:00",
                "total_checked": 1,
                "total_unused": 1,
                "estimated_monthly_waste": 9.6,
                "azure_connection_state": "configured",
                "azure_connection_message": "Azure connection test succeeded.",
                "message": "Unused resource analysis completed.",
                "unused_resources": [
                    {
                        "resource_id": "rid-1",
                        "resource_name": "disk-1",
                        "resource_type": "microsoft.compute/disks",
                        "location": "eastus",
                        "resource_group": "rg-monitor",
                        "subscription_id": "sub-1",
                        "idle_reason": "Managed disk is unattached and not associated with any virtual machine",
                        "idle_signals": ["config_unattached"],
                        "confidence": "high",
                        "days_checked": lookback_days,
                        "monthly_cost_estimate": 9.6,
                        "portal_link": "https://portal.azure.com/#resource/subscriptions/sub-1/resourceGroups/rg-monitor/providers/Microsoft.Compute/disks/disk-1",
                    }
                ],
            }

    monkeypatch.setattr("app.domains.architecture.routes.MonitoringService", lambda: _MockService())

    with TestClient(app) as client:
        architecture = _create_architecture(client, f"mon-unused-live-{uuid4()}")
        _create_resource(client, architecture["id"], "vm")

        response = client.post(
            f"/api/architectures/{architecture['id']}/unused-resources",
            json={"lookback_days": lookback_days},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["state"] == "evaluated"
        assert payload["lookback_days"] == lookback_days
        assert payload["total_unused"] == 1
        assert payload["unused_resources"][0]["days_checked"] == lookback_days

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


def test_monitoring_subscription_scope_isolation_and_duplicate_prevention(monkeypatch):
    class _ScopedMockService:
        async def monitor_resource(self, architecture, resource, **kwargs):
            _ = kwargs
            return ResourceMonitoringRead(
                architecture_id=str(architecture.id),
                resource_id=str(resource.id),
                resource_name=resource.name,
                resource_type=resource.resource_type,
                state="not_configured",
                live=False,
                message="credentials missing",
            )

        async def monitor_architecture(self, architecture, resources, **kwargs):
            scoped_resources = []
            for item in resources:
                scoped_resources.append(
                    ResourceMonitoringRead(
                        architecture_id=str(architecture.id),
                        resource_id=str(item.id),
                        resource_name=item.name,
                        resource_type=item.resource_type,
                        state="not_configured",
                        live=False,
                        message="credentials missing",
                    )
                )
            return ArchitectureMonitoringSummaryRead(
                architecture_id=str(architecture.id),
                state="azure_api_failure" if scoped_resources else "unsupported",
                total_resources=len(scoped_resources),
                monitored_resources=len(scoped_resources),
                live_resources=0,
                healthy_count=0,
                warning_count=0,
                critical_count=0,
                no_data_count=0,
                unsupported_count=0 if scoped_resources else 1,
                error_count=1 if scoped_resources else 0,
                resources=scoped_resources,
            )

    monkeypatch.setattr("app.domains.architecture.routes.MonitoringService", lambda: _ScopedMockService())

    with TestClient(app) as client:
        architecture = _create_architecture(client, f"mon-scope-{uuid4()}")

        sub_a = client.post(
            f"/api/architectures/{architecture['id']}/subscriptions",
            json={"name": "sub-a", "subscription_id": "sub-a", "tenant_id": "tenant-a"},
        ).json()
        sub_b = client.post(
            f"/api/architectures/{architecture['id']}/subscriptions",
            json={"name": "sub-b", "subscription_id": "sub-b", "tenant_id": "tenant-b"},
        ).json()

        rg_a = client.post(
            f"/api/architectures/{architecture['id']}/resource-groups",
            json={"name": "rg-a", "location": "East US", "subscription_id": sub_a["id"]},
        ).json()
        rg_b = client.post(
            f"/api/architectures/{architecture['id']}/resource-groups",
            json={"name": "rg-b", "location": "East US", "subscription_id": sub_b["id"]},
        ).json()

        resource_a = client.post(
            f"/api/architectures/{architecture['id']}/resources",
            json={
                "resource_type": "vm",
                "name": "vm-a",
                "location": "East US",
                "resource_group_id": rg_a["id"],
                "properties": {
                    "azure_resource_id": "/subscriptions/sub-a/resourceGroups/rg-a/providers/Microsoft.Compute/virtualMachines/vm-a",
                    "azure_subscription_id": "sub-a",
                },
            },
        ).json()
        resource_b = client.post(
            f"/api/architectures/{architecture['id']}/resources",
            json={
                "resource_type": "vm",
                "name": "vm-b",
                "location": "East US",
                "resource_group_id": rg_b["id"],
                "properties": {
                    "azure_resource_id": "/subscriptions/sub-b/resourceGroups/rg-b/providers/Microsoft.Compute/virtualMachines/vm-b",
                    "azure_subscription_id": "sub-b",
                },
            },
        ).json()

        sub_a_incidents = client.post(
            f"/api/architectures/{architecture['id']}/incident-summary",
            json={"subscription_id": sub_a["id"]},
        )
        assert sub_a_incidents.status_code == 200
        sub_a_incident_payload = sub_a_incidents.json()
        assert sub_a_incident_payload["incident_count"] == 1
        assert "vm-a" in sub_a_incident_payload["incidents"][0]["title"]

        # Repeated cycles for the same subscription should not create duplicate active incidents.
        sub_a_repeat = client.post(
            f"/api/architectures/{architecture['id']}/incident-summary",
            json={"subscription_id": sub_a["subscription_id"]},
        )
        assert sub_a_repeat.status_code == 200
        assert sub_a_repeat.json()["incident_count"] == 1

        sub_b_incidents = client.post(
            f"/api/architectures/{architecture['id']}/incident-summary",
            json={"subscription_id": sub_b["id"]},
        )
        assert sub_b_incidents.status_code == 200
        sub_b_incident_payload = sub_b_incidents.json()
        assert sub_b_incident_payload["incident_count"] == 1
        assert "vm-b" in sub_b_incident_payload["incidents"][0]["title"]

        sub_a_alerts = client.post(
            f"/api/architectures/{architecture['id']}/alerts-summary",
            json={"subscription_id": sub_a["id"]},
        )
        assert sub_a_alerts.status_code == 200
        sub_a_alerts_payload = sub_a_alerts.json()
        assert sub_a_alerts_payload["alert_count"] == 1
        assert all(item["subscription_id"] == sub_a["id"] for item in sub_a_alerts_payload["alerts"])

        sub_b_alerts = client.post(
            f"/api/architectures/{architecture['id']}/alerts-summary",
            json={"subscription_id": sub_b["subscription_id"]},
        )
        assert sub_b_alerts.status_code == 200
        sub_b_alerts_payload = sub_b_alerts.json()
        assert sub_b_alerts_payload["alert_count"] == 1
        assert all(item["subscription_id"] == sub_b["id"] for item in sub_b_alerts_payload["alerts"])

        wrong_scope_resource = client.post(
            f"/api/architectures/{architecture['id']}/resources/{resource_a['id']}/monitoring",
            json={"subscription_id": sub_b["id"]},
        )
        assert wrong_scope_resource.status_code == 404

        correct_scope_resource = client.post(
            f"/api/architectures/{architecture['id']}/resources/{resource_b['id']}/monitoring",
            json={"subscription_id": sub_b["subscription_id"]},
        )
        assert correct_scope_resource.status_code == 200

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204


def test_monitoring_invalid_subscription_scope_rejected(monkeypatch):
    class _ScopedMockService:
        async def monitor_architecture(self, architecture, resources, **kwargs):
            scoped_resources = [
                ResourceMonitoringRead(
                    architecture_id=str(architecture.id),
                    resource_id=str(item.id),
                    resource_name=item.name,
                    resource_type=item.resource_type,
                    state="not_configured",
                    live=False,
                    message="credentials missing",
                )
                for item in resources
            ]
            return ArchitectureMonitoringSummaryRead(
                architecture_id=str(architecture.id),
                state="azure_api_failure" if scoped_resources else "unsupported",
                total_resources=len(scoped_resources),
                monitored_resources=len(scoped_resources),
                live_resources=0,
                healthy_count=0,
                warning_count=0,
                critical_count=0,
                no_data_count=0,
                unsupported_count=0 if scoped_resources else 1,
                error_count=1 if scoped_resources else 0,
                resources=scoped_resources,
            )

    monkeypatch.setattr("app.domains.architecture.routes.MonitoringService", lambda: _ScopedMockService())

    with TestClient(app) as client:
        architecture = _create_architecture(client, f"mon-invalid-scope-{uuid4()}")

        sub_a = client.post(
            f"/api/architectures/{architecture['id']}/subscriptions",
            json={"name": "sub-a", "subscription_id": "sub-a", "tenant_id": "tenant-a"},
        ).json()

        rg_a = client.post(
            f"/api/architectures/{architecture['id']}/resource-groups",
            json={"name": "rg-a", "location": "East US", "subscription_id": sub_a["id"]},
        ).json()

        _ = client.post(
            f"/api/architectures/{architecture['id']}/resources",
            json={
                "resource_type": "vm",
                "name": "vm-a",
                "location": "East US",
                "resource_group_id": rg_a["id"],
                "properties": {
                    "azure_resource_id": "/subscriptions/sub-a/resourceGroups/rg-a/providers/Microsoft.Compute/virtualMachines/vm-a",
                    "azure_subscription_id": "sub-a",
                },
            },
        ).json()

        invalid_incidents = client.post(
            f"/api/architectures/{architecture['id']}/incident-summary",
            json={"subscription_id": "not-in-architecture"},
        )
        assert invalid_incidents.status_code == 404

        invalid_alerts = client.post(
            f"/api/architectures/{architecture['id']}/alerts-summary",
            json={"subscription_id": "not-in-architecture"},
        )
        assert invalid_alerts.status_code == 404

        cleanup = client.delete(f"/api/architectures/{architecture['id']}")
        assert cleanup.status_code == 204
