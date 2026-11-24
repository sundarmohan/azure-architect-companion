import asyncio

import httpx

from datetime import datetime, timezone

from app.domains.monitoring.telemetry import collect_telemetry, metric_analysis


VM = {
    "id": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/test/providers/Microsoft.Compute/virtualMachines/vm",
    "name": "Test VM",
    "type": "Microsoft.Compute/virtualMachines",
    "location": "eastus",
}


def test_collects_health_and_separates_average_from_total_counters():
    calls = []

    def respond(request):
        assert request.method == "GET"
        assert request.url.host == "management.azure.com"
        assert request.headers["Authorization"] == "Bearer test-token"
        calls.append(request.url)
        if request.url.path.endswith("/current"):
            return httpx.Response(200, json={"properties": {"availabilityState": "Available"}})
        if request.url.path.endswith("/metricDefinitions"):
            return httpx.Response(200, json={"value": [
                {"name": {"value": "Percentage CPU"}, "supportedAggregationTypes": ["Average"]},
                {"name": {"value": "Network In Total"}, "supportedAggregationTypes": ["Total"]},
            ]})
        aggregate = request.url.params["aggregation"]
        assert request.url.params["interval"] == "PT1H"
        name = "Percentage CPU" if aggregate == "Average" else "Network In Total"
        return httpx.Response(200, json={
            "value": [{
                "name": {"value": name},
                "unit": "Percent" if aggregate == "Average" else "Bytes",
                "timeseries": [{"data": [
                    {"timeStamp": "2026-11-21T12:00:00Z", aggregate.lower(): 42},
                    {"timeStamp": "invalid", aggregate.lower(): 100},
                    {"timeStamp": "2026-11-21T13:00:00Z", aggregate.lower(): None},
                ]}],
            }],
        })

    async def read():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            return await collect_telemetry([VM], http, {"Authorization": "Bearer test-token"})

    status, payload = asyncio.run(read())
    assert status == "synced"
    resource = payload["resources"][0]
    assert resource["health"] == "available"
    assert resource["metrics_status"] == "synced"
    assert len(calls) == 4
    metric_urls = [url for url in calls if url.path.endswith("/metrics")]
    assert all("Available Memory Bytes" not in url.params["metricnames"] for url in metric_urls)
    assert all("Network Out Total" not in url.params["metricnames"] for url in metric_urls)
    assert [(metric["name"], metric["aggregation"], metric["points"][0]["value"])
            for metric in resource["metrics"]] == [
        ("Percentage CPU", "average", 42), ("Network In Total", "total", 42),
    ]
    assert all(len(metric["points"]) == 1 for metric in resource["metrics"])


def test_returns_partial_health_and_never_follows_invalid_inventory_paths():
    calls = []

    def respond(request):
        calls.append(request.url)
        if request.url.path.endswith("/current"):
            return httpx.Response(200, json={"properties": {"availabilityState": "Degraded"}})
        if request.url.path.endswith("/metricDefinitions"):
            return httpx.Response(200, json={"value": [
                {"name": {"value": "Percentage CPU"}, "supportedAggregationTypes": ["Average"]},
            ]})
        return httpx.Response(403, json={"message": "untrusted upstream detail"})

    async def read():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            return await collect_telemetry([VM, {**VM, "id": "https://example.invalid"}], http, {})

    status, payload = asyncio.run(read())
    assert status == "partial_failure"
    healthy, invalid = payload["resources"]
    assert healthy["health"] == "degraded"
    assert healthy["metrics_status"] == "permission_failure"
    assert healthy["metrics"] == []
    assert invalid["health_status"] == "unsupported"
    assert len(calls) == 3
    assert "untrusted upstream detail" not in str(payload)


def test_metric_analysis_is_deterministic_and_evidence_bound():
    collected_at = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)
    points = [
        {"timestamp": f"2026-11-24T{hour:02d}:00:00+00:00", "value": value}
        for hour, value in zip(range(6, 12), [10, 10, 10, 10, 10, 30])
    ]

    analysis = metric_analysis(points, collected_at)

    assert analysis["sample_count"] == 6
    assert analysis["direction"] == "increasing"
    assert analysis["freshness"] == "recent"
    assert analysis["anomaly"] is True
