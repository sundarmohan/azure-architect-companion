import asyncio
from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient

from tests.legacy_app import app
from app.domains.architecture.models import Architecture, ArchitectureResource, AzureResourceGroup, AzureSubscription
from app.domains.cost.azure_cost_management_adapter import AzureCostManagementAdapter
from app.domains.cost.azure_retail_adapter import AzureRetailPricingAdapter
from app.domains.cost.service import (
    CostEstimationService,
    _provider_from_resource,
    _resource_region,
    _resource_sku,
)


def _run(coro):
    return asyncio.run(coro)


def test_provider_resource_region_and_sku_normalization():
    assert _provider_from_resource({"resource_type": "vm"}, "azure") == "azure"
    assert _provider_from_resource({"resource_type": "aws-ec2"}, "azure") == "aws"

    assert _resource_region({"location": "East US"}, "westus") == "East US"
    assert _resource_region({}, "westus2") == "westus2"

    assert _resource_sku({"sku": "Standard_D2s_v5"}) == "Standard_D2s_v5"
    assert _resource_sku({"properties": {"vmSize": "Standard_B2s"}}) == "Standard_B2s"
    assert _resource_sku({}) is None


def test_adapter_region_mapping_and_service_mapping():
    adapter = AzureRetailPricingAdapter()

    assert adapter._normalize_region("East US 2") == "eastus2"
    assert adapter._normalize_region("west us") == "westus"

    assert adapter._map_resource_to_service("vm") == "Virtual Machines"
    assert adapter._map_resource_to_service("sql") == "SQL Database"
    assert adapter._map_resource_to_service("unknown") == ""


def test_adapter_price_normalization_hour_and_month_and_day_and_gb():
    adapter = AzureRetailPricingAdapter()

    hourly = adapter._normalize_price(price=1.5, unit="1 Hour", quantity=2)
    assert hourly is not None
    assert round(hourly["monthly"], 2) == 2190.00

    monthly = adapter._normalize_price(price=50, unit="1 Month", quantity=3)
    assert monthly is not None
    assert monthly["monthly"] == 150

    daily = adapter._normalize_price(price=2, unit="1 Day", quantity=1)
    assert daily is not None
    assert daily["monthly"] == 60

    gb = adapter._normalize_price(price=0.1, unit="1 GB/Month", quantity=200)
    assert gb is not None
    assert gb["monthly"] == 20

    assert adapter._normalize_price(price=1, unit="per transaction", quantity=1) is None


def test_retail_api_response_normalization_with_mock(monkeypatch):
    adapter = AzureRetailPricingAdapter()

    class MockResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "Items": [
                    {
                        "armSkuName": "Standard_D2s_v5",
                        "skuName": "D2s",
                        "meterName": "D2s v5",
                        "unitOfMeasure": "1 Hour",
                        "retailPrice": 0.1,
                        "currencyCode": "USD",
                    }
                ],
                "NextPageLink": None,
            }

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None):
            return MockResponse()

    monkeypatch.setattr("app.domains.cost.azure_retail_adapter.httpx.AsyncClient", MockClient)

    result = _run(
        adapter.get_pricing(
            resource_type="vm",
            region="eastus",
            sku="Standard_D2s_v5",
            quantity=2,
        )
    )

    assert result["pricing_source"] == "azure_retail_prices"
    assert result["currency"] == "USD"
    assert result["sku"] == "Standard_D2s_v5"
    assert result["unit_of_measure"] == "1 Hour"
    assert result["monthly"] == 146.0


def test_retail_api_unavailable_when_no_items(monkeypatch):
    adapter = AzureRetailPricingAdapter()

    class MockResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"Items": [], "NextPageLink": None}

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None):
            return MockResponse()

    monkeypatch.setattr("app.domains.cost.azure_retail_adapter.httpx.AsyncClient", MockClient)

    result = _run(
        adapter.get_pricing(
            resource_type="vm",
            region="eastus",
            sku="Standard_B2s",
            quantity=1,
        )
    )

    assert result["unavailable"] is True
    assert "No Microsoft Retail Prices rows" in result["error"]


def test_service_aggregation_and_totals_live_source():
    class FakeAdapter:
        async def get_pricing(self, *, resource_type, region, sku, quantity):
            return {
                "unavailable": False,
                "pricing_source": "azure_retail_prices",
                "currency": "USD",
                "sku": sku or "default",
                "meter_name": "meter",
                "unit_of_measure": "1 Month",
                "monthly": 100.0 if resource_type == "vm" else 25.0,
                "annual": 1200.0 if resource_type == "vm" else 300.0,
            }

    architecture = Architecture(name="a", provider="azure", environment="draft", status="draft")
    r1 = ArchitectureResource(
        architecture_id=architecture.id,
        resource_type="vm",
        name="vm-1",
        location="eastus",
        properties={},
    )
    r2 = ArchitectureResource(
        architecture_id=architecture.id,
        resource_type="storage",
        name="st-1",
        location="eastus",
        properties={},
    )

    service = CostEstimationService(adapter=FakeAdapter())
    result = _run(
        service.estimate_architecture_cost(
            architecture=architecture,
            resources=[r1, r2],
            resource_groups=[],
            region_override=None,
        )
    )

    assert result.pricing_source == "azure_retail_prices"
    assert result.total_monthly_cost == 125.0
    assert result.total_annual_cost == 1500.0
    assert len(result.items) == 2


def test_service_aggregation_by_resource_group_and_subscription():
    class FakeAdapter:
        async def get_pricing(self, *, resource_type, region, sku, quantity):
            return {
                "unavailable": False,
                "pricing_source": "azure_retail_prices",
                "currency": "USD",
                "sku": sku or "default",
                "meter_name": "meter",
                "unit_of_measure": "1 Month",
                "monthly": 80.0 if resource_type == "vm" else 20.0,
                "annual": 960.0 if resource_type == "vm" else 240.0,
            }

    architecture = Architecture(name="a", provider="azure", environment="draft", status="draft")
    sub = AzureSubscription(
        id=uuid4(),
        architecture_id=architecture.id,
        name="sub-a",
        subscription_id="sub-agg",
        environment="design",
        properties={},
    )
    rg = AzureResourceGroup(
        id=uuid4(),
        architecture_id=architecture.id,
        name="rg-a",
        location="eastus",
        subscription_id=sub.id,
        tags={},
        properties={},
    )
    r1 = ArchitectureResource(
        architecture_id=architecture.id,
        resource_type="vm",
        name="vm-1",
        location="eastus",
        resource_group_id=rg.id,
        properties={},
    )
    r2 = ArchitectureResource(
        architecture_id=architecture.id,
        resource_type="storage",
        name="st-1",
        location="eastus",
        resource_group_id=rg.id,
        properties={},
    )

    service = CostEstimationService(adapter=FakeAdapter())
    result = _run(
        service.estimate_architecture_cost(
            architecture=architecture,
            resources=[r1, r2],
            resource_groups=[rg],
            subscriptions=[sub],
            region_override=None,
        )
    )

    assert result.total_monthly_cost == 100.0
    assert result.breakdown.by_resource_group["rg-a"] == 100.0
    assert result.breakdown.by_subscription["sub-agg"] == 100.0
    assert result.items[0].resource_group_name == "rg-a"
    assert result.items[0].subscription_id == "sub-agg"


def test_service_fallback_source_when_live_unavailable():
    class FailingAdapter:
        async def get_pricing(self, *, resource_type, region, sku, quantity):
            return {"unavailable": True, "error": "live unavailable"}

    architecture = Architecture(name="a", provider="azure", environment="draft", status="draft")
    r1 = ArchitectureResource(
        architecture_id=architecture.id,
        resource_type="vm",
        name="vm-1",
        location="eastus",
        properties={"vmSize": "Standard_B2s"},
    )

    service = CostEstimationService(adapter=FailingAdapter())
    result = _run(
        service.estimate_architecture_cost(
            architecture=architecture,
            resources=[r1],
            resource_groups=[],
            region_override=None,
        )
    )

    assert result.pricing_source == "schema_fallback"
    assert len(result.warnings) == 1
    assert result.items[0].pricing_source == "schema_fallback"


def test_service_invalid_resource_returns_controlled_unavailable():
    class FailingAdapter:
        async def get_pricing(self, *, resource_type, region, sku, quantity):
            return {"unavailable": True, "error": "unsupported resource type"}

    architecture = Architecture(name="a", provider="azure", environment="draft", status="draft")
    bad = ArchitectureResource(
        architecture_id=architecture.id,
        resource_type="not-real",
        name="x",
        location=None,
        properties={},
    )

    service = CostEstimationService(adapter=FailingAdapter())
    result = _run(
        service.estimate_architecture_cost(
            architecture=architecture,
            resources=[bad],
            resource_groups=[],
            region_override="eastus",
        )
    )

    assert result.pricing_source == "schema_fallback"
    assert result.items[0].monthly_cost == 0.0
    assert result.items[0].warning is not None
    assert result.errors


def test_cost_endpoint_and_source_identification(monkeypatch):
    async def fake_get_pricing(self, *, resource_type, region, sku, quantity):
        return {
            "unavailable": False,
            "pricing_source": "azure_retail_prices",
            "currency": "USD",
            "sku": sku or "default",
            "meter_name": "meter",
            "unit_of_measure": "1 Month",
            "monthly": 42.0,
            "annual": 504.0,
        }

    monkeypatch.setattr(
        "app.domains.cost.azure_retail_adapter.AzureRetailPricingAdapter.get_pricing",
        fake_get_pricing,
    )

    with TestClient(app) as client:
        create = client.post("/api/architectures", json={"name": f"cost-{uuid4()}"})
        assert create.status_code == 201
        arch_id = create.json()["id"]

        rg = client.post(
            f"/api/architectures/{arch_id}/resource-groups",
            json={"name": "rg-cost", "location": "East US"},
        )
        assert rg.status_code == 201
        rg_id = rg.json()["id"]

        vm = client.post(
            f"/api/architectures/{arch_id}/resources",
            json={"resource_type": "vm", "name": "vm-cost", "resource_group_id": rg_id, "location": "East US"},
        )
        assert vm.status_code == 201

        estimate = client.post(f"/api/architectures/{arch_id}/cost-estimate", json={"region": "eastus"})
        assert estimate.status_code == 200
        payload = estimate.json()

        assert payload["pricing_source"] == "azure_retail_prices"
        assert payload["total_monthly_cost"] == 42.0
        assert payload["items"][0]["pricing_source"] == "azure_retail_prices"

        cleanup = client.delete(f"/api/architectures/{arch_id}")
        assert cleanup.status_code == 204


def test_service_actual_cost_available_path():
    class FakeActualAdapter:
        def default_start_date(self):
            return date(2026, 1, 1)

        def default_end_date(self):
            return date(2026, 1, 31)

        async def get_actual_cost(self, *, subscription_id, start_date, end_date):
            assert subscription_id == "sub-123"
            return {
                "available": True,
                "source": "azure_cost_management",
                "subscription_id": subscription_id,
                "currency": "USD",
                "total_cost": 99.5,
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
                "daily": [{"usage_date": "2026-01-15", "cost": 3.5}],
            }

    architecture = Architecture(name="a", provider="azure", environment="draft", status="draft")
    sub = AzureSubscription(architecture_id=architecture.id, name="s1", subscription_id="sub-123", environment="design", properties={})

    service = CostEstimationService(actual_adapter=FakeActualAdapter())
    result = _run(
        service.get_architecture_actual_cost(
            architecture=architecture,
            subscriptions=[sub],
            requested_subscription_id=None,
            start_date=None,
            end_date=None,
        )
    )

    assert result.available is True
    assert result.pricing_source == "azure_cost_management"
    assert result.total_cost == 99.5
    assert result.subscription_id == "sub-123"
    assert len(result.daily) == 1


def test_service_actual_cost_unavailable_path():
    class FakeActualAdapter:
        def default_start_date(self):
            return date(2026, 2, 1)

        def default_end_date(self):
            return date(2026, 2, 28)

        async def get_actual_cost(self, *, subscription_id, start_date, end_date):
            return {"available": False, "error": "missing credentials"}

    architecture = Architecture(name="a", provider="azure", environment="draft", status="draft")
    sub = AzureSubscription(
        architecture_id=architecture.id,
        name="sub-x",
        subscription_id="sub-x",
        environment="design",
        properties={},
    )
    service = CostEstimationService(actual_adapter=FakeActualAdapter())
    result = _run(
        service.get_architecture_actual_cost(
            architecture=architecture,
            subscriptions=[sub],
            requested_subscription_id="sub-x",
            start_date=None,
            end_date=None,
        )
    )

    assert result.available is False
    assert result.error is not None
    assert "missing credentials" in result.error


def test_actual_cost_endpoint_unavailable_and_available(monkeypatch):
    async def fake_unavailable(self, *, subscription_id, start_date, end_date):
        return {"available": False, "error": "forbidden"}

    monkeypatch.setattr(
        "app.domains.cost.azure_cost_management_adapter.AzureCostManagementAdapter.get_actual_cost",
        fake_unavailable,
    )

    with TestClient(app) as client:
        create = client.post("/api/architectures", json={"name": f"actual-{uuid4()}"})
        assert create.status_code == 201
        arch_id = create.json()["id"]

        sub = client.post(
            f"/api/architectures/{arch_id}/subscriptions",
            json={"name": "sub-a", "subscription_id": "sub-aaa"},
        )
        assert sub.status_code == 201

        unavailable = client.post(f"/api/architectures/{arch_id}/actual-cost", json={})
        assert unavailable.status_code == 200
        un_payload = unavailable.json()
        assert un_payload["available"] is False
        assert un_payload["pricing_source"] == "azure_cost_management"
        assert "forbidden" in (un_payload["error"] or "")

        async def fake_available(self, *, subscription_id, start_date, end_date):
            return {
                "available": True,
                "source": "azure_cost_management",
                "subscription_id": subscription_id,
                "currency": "USD",
                "total_cost": 12.34,
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
                "daily": [{"usage_date": start_date.isoformat(), "cost": 12.34}],
            }

        monkeypatch.setattr(
            "app.domains.cost.azure_cost_management_adapter.AzureCostManagementAdapter.get_actual_cost",
            fake_available,
        )

        available = client.post(
            f"/api/architectures/{arch_id}/actual-cost",
            json={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )
        assert available.status_code == 200
        av_payload = available.json()
        assert av_payload["available"] is True
        assert av_payload["pricing_source"] == "azure_cost_management"
        assert av_payload["total_cost"] == 12.34

        cleanup = client.delete(f"/api/architectures/{arch_id}")
        assert cleanup.status_code == 204


def test_service_actual_cost_rejects_subscription_outside_architecture():
    class FakeActualAdapter:
        def default_start_date(self):
            return date(2026, 3, 1)

        def default_end_date(self):
            return date(2026, 3, 31)

        async def get_actual_cost(self, *, subscription_id, start_date, end_date):
            raise AssertionError("adapter should not be called for foreign subscription")

    architecture = Architecture(name="a", provider="azure", environment="draft", status="draft")
    allowed = AzureSubscription(
        architecture_id=architecture.id,
        name="sub-owned",
        subscription_id="sub-owned",
        environment="design",
        properties={},
    )

    service = CostEstimationService(actual_adapter=FakeActualAdapter())
    result = _run(
        service.get_architecture_actual_cost(
            architecture=architecture,
            subscriptions=[allowed],
            requested_subscription_id="sub-foreign",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )
    )

    assert result.available is False
    assert result.error == "Requested subscription does not belong to this architecture"


def test_service_actual_cost_uses_requested_owned_subscription():
    class FakeActualAdapter:
        def __init__(self):
            self.called_subscription_id = None

        def default_start_date(self):
            return date(2026, 4, 1)

        def default_end_date(self):
            return date(2026, 4, 30)

        async def get_actual_cost(self, *, subscription_id, start_date, end_date):
            self.called_subscription_id = subscription_id
            return {
                "available": True,
                "subscription_id": subscription_id,
                "currency": "USD",
                "total_cost": 10,
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
                "daily": [],
            }

    architecture = Architecture(name="a", provider="azure", environment="draft", status="draft")
    sub1 = AzureSubscription(architecture_id=architecture.id, name="s1", subscription_id="sub-1", environment="design", properties={})
    sub2 = AzureSubscription(architecture_id=architecture.id, name="s2", subscription_id="sub-2", environment="design", properties={})

    adapter = FakeActualAdapter()
    service = CostEstimationService(actual_adapter=adapter)
    result = _run(
        service.get_architecture_actual_cost(
            architecture=architecture,
            subscriptions=[sub1, sub2],
            requested_subscription_id="sub-2",
            start_date=date(2026, 4, 10),
            end_date=date(2026, 4, 10),
        )
    )

    assert result.available is True
    assert result.subscription_id == "sub-2"
    assert adapter.called_subscription_id == "sub-2"
    assert result.start_date == "2026-04-10"
    assert result.end_date == "2026-04-10"


def test_actual_cost_endpoint_invalid_date_format_and_reversed_dates(monkeypatch):
    async def fake_cost(self, *, subscription_id, start_date, end_date):
        if end_date < start_date:
            return {"available": False, "error": "Invalid date range: end_date is before start_date"}
        return {
            "available": True,
            "subscription_id": subscription_id,
            "currency": "USD",
            "total_cost": 0,
            "from": start_date.isoformat(),
            "to": end_date.isoformat(),
            "daily": [],
        }

    monkeypatch.setattr(
        "app.domains.cost.azure_cost_management_adapter.AzureCostManagementAdapter.get_actual_cost",
        fake_cost,
    )

    with TestClient(app) as client:
        create = client.post("/api/architectures", json={"name": f"date-{uuid4()}"})
        assert create.status_code == 201
        arch_id = create.json()["id"]

        sub = client.post(
            f"/api/architectures/{arch_id}/subscriptions",
            json={"name": "sub-date", "subscription_id": "sub-date"},
        )
        assert sub.status_code == 201

        invalid_format = client.post(
            f"/api/architectures/{arch_id}/actual-cost",
            json={"start_date": "2026/01/01", "end_date": "2026-01-31"},
        )
        assert invalid_format.status_code == 422

        reversed_range = client.post(
            f"/api/architectures/{arch_id}/actual-cost",
            json={"start_date": "2026-02-10", "end_date": "2026-02-01"},
        )
        assert reversed_range.status_code == 200
        payload = reversed_range.json()
        assert payload["available"] is False
        assert "Invalid date range" in (payload["error"] or "")

        cleanup = client.delete(f"/api/architectures/{arch_id}")
        assert cleanup.status_code == 204


def test_actual_cost_adapter_controlled_auth_and_empty_response(monkeypatch):
    adapter = AzureCostManagementAdapter()

    monkeypatch.setenv("AZURE_TENANT_ID", "tenant")
    monkeypatch.setenv("AZURE_CLIENT_ID", "client")
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "secret")

    class BadCredential:
        def __init__(self, tenant_id, client_id, client_secret):
            pass

        def get_token(self, scope):
            raise RuntimeError("bad credentials")

    monkeypatch.setattr("app.domains.cost.azure_cost_management_adapter.ClientSecretCredential", BadCredential)

    auth_failure = _run(
        adapter.get_actual_cost(
            subscription_id="sub-1",
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 31),
        )
    )
    assert auth_failure["available"] is False
    assert "authentication failed" in auth_failure["error"].lower()

    class GoodCredential:
        def __init__(self, tenant_id, client_id, client_secret):
            pass

        def get_token(self, scope):
            class Token:
                token = "fake-token"

            return Token()

    class ForbiddenResponse:
        status_code = 403

        def raise_for_status(self):
            return None

        def json(self):
            return {}

    class EmptyOkResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"properties": {"columns": [{"name": "Cost"}, {"name": "Currency"}, {"name": "UsageDate"}], "rows": []}}

    class MockClientForbidden:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, params=None, headers=None, json=None):
            return ForbiddenResponse()

    class MockClientEmptyOk:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, params=None, headers=None, json=None):
            return EmptyOkResponse()

    monkeypatch.setattr("app.domains.cost.azure_cost_management_adapter.ClientSecretCredential", GoodCredential)
    monkeypatch.setattr("app.domains.cost.azure_cost_management_adapter.httpx.AsyncClient", MockClientForbidden)

    forbidden = _run(
        adapter.get_actual_cost(
            subscription_id="sub-1",
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 31),
        )
    )
    assert forbidden["available"] is False
    assert "insufficient" in forbidden["error"].lower()

    monkeypatch.setattr("app.domains.cost.azure_cost_management_adapter.httpx.AsyncClient", MockClientEmptyOk)
    empty_ok = _run(
        adapter.get_actual_cost(
            subscription_id="sub-1",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
        )
    )
    assert empty_ok["available"] is True
    assert empty_ok["total_cost"] == 0.0
    assert empty_ok["currency"] == "USD"


def test_actual_cost_adapter_reversed_date_precedence_without_credentials():
    adapter = AzureCostManagementAdapter()
    result = _run(
        adapter.get_actual_cost(
            subscription_id="sub-1",
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 1),
        )
    )
    assert result["available"] is False
    assert "Invalid date range" in result["error"]


def test_actual_cost_adapter_aggregates_multiple_rows(monkeypatch):
    adapter = AzureCostManagementAdapter()

    monkeypatch.setenv("AZURE_TENANT_ID", "tenant")
    monkeypatch.setenv("AZURE_CLIENT_ID", "client")
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "secret")

    class GoodCredential:
        def __init__(self, tenant_id, client_id, client_secret):
            pass

        def get_token(self, scope):
            class Token:
                token = "fake-token"

            return Token()

    class OkResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "properties": {
                    "columns": [
                        {"name": "Cost"},
                        {"name": "Currency"},
                        {"name": "UsageDate"},
                    ],
                    "rows": [
                        [1.25, "USD", "20260701"],
                        [2.75, "USD", "20260702"],
                    ],
                }
            }

    class MockClientOk:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, params=None, headers=None, json=None):
            return OkResponse()

    monkeypatch.setattr("app.domains.cost.azure_cost_management_adapter.ClientSecretCredential", GoodCredential)
    monkeypatch.setattr("app.domains.cost.azure_cost_management_adapter.httpx.AsyncClient", MockClientOk)

    result = _run(
        adapter.get_actual_cost(
            subscription_id="sub-1",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )
    )

    assert result["available"] is True
    assert result["total_cost"] == 4.0
    assert result["currency"] == "USD"
    assert len(result["daily"]) == 2
