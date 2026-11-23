"""Read bounded Azure Recovery Services evidence for inventoried vaults."""

import asyncio
import re
from datetime import datetime, timezone
from urllib.parse import quote
from uuid import UUID

import httpx
from azure.core.exceptions import AzureError
from azure.identity.aio import ClientSecretCredential
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.access.azure import confirm_active_connection
from app.domains.access.routes import client_access, get_db
from app.domains.monitoring.observations import observation_context
from app.domains.monitoring.telemetry import request_json

router = APIRouter()
ARM = "https://management.azure.com"
VAULT_PATH = re.compile(r"/subscriptions/([^/]+)/resourceGroups/([^/]+)/providers/Microsoft\.RecoveryServices/vaults/([a-zA-Z0-9-]+)", re.ASCII | re.I)
MAX_VAULTS = 6
MAX_ROWS = 25
PROPERTIES = {
    "jobs": ("entityFriendlyName", "operation", "status", "startTime", "endTime"),
    "protected_items": ("friendlyName", "protectionState", "protectionStatus", "lastBackupStatus",
                        "lastBackupTime", "lastRecoveryPoint", "policyId"),
}


def vaults_for_inventory(resources, subscription):
    vaults = {}
    for row in resources:
        resource_id = row.get("id")
        match = VAULT_PATH.fullmatch(resource_id) if isinstance(resource_id, str) else None
        if (not match or match[1].casefold() != str(subscription)
                or match[2] in {".", ".."} or any(ord(char) < 32 for char in resource_id)):
            continue
        vaults.setdefault(resource_id.casefold(), (resource_id, match[3]))
    return list(vaults.values())


async def read_rows(http, semaphore, headers, vault, collection, endpoint, version):
    status, payload = await request_json(http, semaphore, f"{ARM}{quote(vault, safe='/')}/{endpoint}",
                                         {"api-version": version}, headers)
    items = payload.get("value")
    if status == "synced" and not isinstance(items, list):
        status = "provider_error"
    rows = []
    if isinstance(items, list):
        for item in items[:MAX_ROWS]:
            props = item.get("properties") if isinstance(item, dict) else None
            if not isinstance(props, dict):
                continue
            rows.append({key: props[key][:512] for key in PROPERTIES[collection] if isinstance(props.get(key), str)})
    return {"status": status, "rows": rows,
            "truncated": bool(payload.get("nextLink")) or (isinstance(items, list) and len(items) > MAX_ROWS)}


async def collect_vaults(vaults, values):
    async with ClientSecretCredential(tenant_id=values["tenant_id"], client_id=values["client_id"],
                                      client_secret=values["client_secret"]) as credential:
        token = await credential.get_token(f"{ARM}/.default")
    headers = {"Authorization": f"Bearer {token.token}"}
    semaphore = asyncio.Semaphore(4)
    async with httpx.AsyncClient(timeout=8, follow_redirects=False) as http:
        async def collect(vault, name):
            jobs, items = await asyncio.gather(
                read_rows(http, semaphore, headers, vault, "jobs", "backupJobs", "2025-08-01"),
                read_rows(http, semaphore, headers, vault, "protected_items", "backupProtectedItems", "2025-02-01"),
            )
            return {"id": vault, "name": name, "jobs": jobs, "protected_items": items}

        return await asyncio.gather(*(collect(*vault) for vault in vaults))


@router.get("/backup/evidence")
async def backup_evidence(request: Request, subscription_id: UUID | None = None,
                          client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db)):
    context = await observation_context(db, client_id, subscription_id)
    if not context or not context.inventory_exists:
        return {"status": "inventory_required" if context else "not_configured", "vaults": [], "limitations": []}
    all_vaults = vaults_for_inventory(context.resources, context.subscription_id)
    limitations = ["Each vault shows up to 25 jobs and protected items from the first Azure response page.",
                   "Restore jobs provide operational evidence. Retention policies, recovery objectives, and restore testing require additional evidence."]
    if context.inventory_is_stale:
        limitations.append("The latest inventory refresh failed. The vault list may be stale.")
    if len(all_vaults) > MAX_VAULTS:
        limitations.append(f"Reviewed the first {MAX_VAULTS} of {len(all_vaults)} inventoried vaults.")
    if not all_vaults:
        return {"status": "no_vaults_in_inventory", "vaults": [], "limitations": limitations}

    await db.rollback()
    try:
        async with asyncio.timeout(25):
            vaults = await collect_vaults(all_vaults[:MAX_VAULTS], context.credentials)
    except AzureError:
        vaults, status = [], "authentication_failure"
    except (TimeoutError, httpx.HTTPError):
        vaults, status = [], "provider_error"
    else:
        statuses = {vault[key]["status"] for vault in vaults for key in ("jobs", "protected_items")}
        status = next(iter(statuses)) if len(statuses) == 1 else "partial_failure"
    await confirm_active_connection(db, request, client_id, context.ciphertext)
    return {"status": status, "retrieved_at": datetime.now(timezone.utc), "vaults": vaults, "limitations": limitations}
