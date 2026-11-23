import asyncio
from uuid import UUID

import httpx

from app.domains.backup.routes import read_rows, retention_summary, vaults_for_inventory


def test_backup_vaults_and_reads_stay_in_scope():
    subscription = UUID("11111111-1111-1111-1111-111111111111")
    root = f"/subscriptions/{subscription}/resourceGroups/example/providers/Microsoft.RecoveryServices/vaults"
    vault = f"{root}/recovery"
    assert vaults_for_inventory([
        {"id": vault}, {"id": vault.upper()}, {"id": vault + "/backupJobs/job"},
        {"id": vault.replace(str(subscription), "22222222-2222-2222-2222-222222222222")},
        {"id": vault.replace("example", "..")},
    ], subscription) == [(vault, "recovery")]

    def transport(request):
        assert request.method == "GET"
        assert request.url.host == "management.azure.com"
        assert request.url.path == vault + "/backupJobs"
        return httpx.Response(200, json={
            "value": [{"properties": {"operation": "Restore", "status": "Completed", "private": "omit"}}],
            "nextLink": "https://untrusted.example/another-page",
        })

    async def read():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
            return await read_rows(http, asyncio.Semaphore(1), {}, vault, "jobs", "backupJobs", "2025-08-01")

    assert asyncio.run(read()) == {
        "status": "synced", "truncated": True, "rows": [{"operation": "Restore", "status": "Completed"}],
    }


def test_retention_summary_only_uses_supported_policy_fields():
    assert retention_summary({
        "dailySchedule": {"retentionDuration": {"count": 30, "durationType": "Days"}},
        "yearlySchedule": {"retentionDuration": {"count": 7, "durationType": "Years"}},
        "monthlySchedule": {"retentionDuration": {"count": True, "durationType": "Months"}},
    }) == "Daily 30 days; Yearly 7 years"
    assert retention_summary(None) == ""