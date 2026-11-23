"""Read bounded Azure Recovery Services evidence for inventoried vaults."""

import asyncio
import re
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import quote
from uuid import UUID

import httpx
from azure.core.exceptions import AzureError
from azure.identity.aio import ClientSecretCredential
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.access.azure import confirm_active_connection, connection_values, select_subscription
from app.domains.access.models import AzureConnection
from app.domains.access.routes import audit, client_access, get_db
from app.domains.monitoring.observations import observation_context
from app.domains.monitoring.telemetry import request_json
from .models import AzureRecoveryObjectives, AzureRestoreTest

router = APIRouter()
ARM = "https://management.azure.com"
VAULT_PATH = re.compile(r"/subscriptions/([^/]+)/resourceGroups/([^/]+)/providers/Microsoft\.RecoveryServices/vaults/([a-zA-Z0-9-]+)", re.ASCII | re.I)
ASR_ITEM_PATH = re.compile(
    r"/replicationFabrics/([\w.()~-]{1,260})/replicationProtectionContainers/([\w.()~-]{1,260})"
    r"/replicationProtectedItems/([\w.()~-]{1,260})", re.ASCII | re.I,
)
MAX_VAULTS = 6
MAX_ROWS = 25
PROPERTIES = {
    "jobs": ("entityFriendlyName", "operation", "status", "startTime", "endTime"),
    "policies": ("backupManagementType",),
    "protected_items": ("friendlyName", "protectionState", "protectionStatus", "lastBackupStatus",
                        "lastBackupTime", "lastRecoveryPoint", "policyId"),
    "replication_items": ("friendlyName", "protectionState", "replicationHealth"),
}


class RecoveryObjectivesWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    rpo_hours: int = Field(strict=True, ge=1, le=8760)
    rto_minutes: int = Field(strict=True, ge=1, le=525600)


class RestoreTestWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    resource_name: str = Field(min_length=1, max_length=200)
    tested_at: AwareDatetime
    outcome: Literal["passed", "failed", "partial"]
    recovery_minutes: int | None = Field(default=None, strict=True, ge=1, le=525600)
    evidence_reference: str | None = Field(default=None, min_length=1, max_length=500)
    notes: str | None = Field(default=None, min_length=1, max_length=1000)


class RestoreTestRead(RestoreTestWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: AwareDatetime


@router.get("/backup/objectives", response_model=RecoveryObjectivesWrite | None)
async def read_recovery_objectives(
    subscription_id: UUID,
    client_id: UUID = Depends(client_access),
    db: AsyncSession = Depends(get_db),
):
    select_subscription(await connection_values(db, client_id), subscription_id)
    return await db.get(AzureRecoveryObjectives, (client_id, subscription_id))


@router.put("/backup/objectives", response_model=RecoveryObjectivesWrite)
async def save_recovery_objectives(
    payload: RecoveryObjectivesWrite,
    request: Request,
    subscription_id: UUID,
    client_id: UUID = Depends(client_access),
    db: AsyncSession = Depends(get_db),
):
    connection = await db.scalar(select(AzureConnection).where(AzureConnection.client_id == client_id).with_for_update())
    values = await connection_values(db, client_id, connection) if connection else None
    select_subscription(values, subscription_id)
    changes = payload.model_dump()
    await db.execute(insert(AzureRecoveryObjectives).values(
        client_id=client_id, subscription_id=subscription_id, **changes,
    ).on_conflict_do_update(
        index_elements=[AzureRecoveryObjectives.client_id, AzureRecoveryObjectives.subscription_id], set_=changes,
    ))
    audit(db, "save_azure_recovery_objectives", request.state.account, client_id, str(subscription_id))
    await db.commit()
    return payload


@router.get("/backup/restore-tests", response_model=list[RestoreTestRead])
async def list_restore_tests(
    subscription_id: UUID | None = None,
    client_id: UUID = Depends(client_access),
    db: AsyncSession = Depends(get_db),
):
    selected = UUID(select_subscription(await connection_values(db, client_id), subscription_id))
    return (await db.scalars(select(AzureRestoreTest).where(
        AzureRestoreTest.client_id == client_id, AzureRestoreTest.subscription_id == selected,
    ).order_by(AzureRestoreTest.tested_at.desc(), AzureRestoreTest.id).limit(50))).all()


@router.put("/backup/restore-tests/{record_id}", response_model=RestoreTestRead)
async def record_restore_test(
    record_id: UUID,
    payload: RestoreTestWrite,
    request: Request,
    subscription_id: UUID | None = None,
    client_id: UUID = Depends(client_access),
    db: AsyncSession = Depends(get_db),
):
    if payload.tested_at > datetime.now(timezone.utc):
        raise HTTPException(422, "Restore test time cannot be in the future")
    connection = await db.scalar(select(AzureConnection).where(AzureConnection.client_id == client_id).with_for_update())
    selected = UUID(select_subscription(
        await connection_values(db, client_id, connection) if connection else None, subscription_id,
    ))
    existing = await db.get(AzureRestoreTest, record_id)
    values = payload.model_dump()
    if existing is not None:
        same_scope = existing.client_id == client_id and existing.subscription_id == selected
        same_values = same_scope and all(getattr(existing, key) == value for key, value in values.items())
        if not same_values:
            raise HTTPException(409, "Restore test record identifier already used")
        return RestoreTestRead.model_validate(existing)
    record = AzureRestoreTest(
        id=record_id, client_id=client_id, subscription_id=selected,
        actor_id=request.state.account.id, **values,
    )
    db.add(record)
    await db.flush()
    audit(db, "record_azure_restore_test", request.state.account, client_id, str(record_id))
    result = RestoreTestRead.model_validate(record)
    await db.commit()
    return result


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


def retention_summary(policy):
    if not isinstance(policy, dict):
        return ""
    schedules = [(label, policy.get(key)) for label, key in (
        ("Daily", "dailySchedule"), ("Weekly", "weeklySchedule"),
        ("Monthly", "monthlySchedule"), ("Yearly", "yearlySchedule"),
    )]
    schedules.append(("", policy))
    parts = []
    for label, schedule in schedules:
        duration = schedule.get("retentionDuration") if isinstance(schedule, dict) else None
        if not isinstance(duration, dict):
            continue
        count, unit = duration.get("count"), duration.get("durationType")
        if type(count) is int and count > 0 and unit in ("Days", "Weeks", "Months", "Years"):
            parts.append(f"{label} {count} {unit.lower()}".strip())
    return "; ".join(parts)


def asr_item_in_vault(item_id, vault):
    if not isinstance(item_id, str) or not item_id.casefold().startswith(f"{vault.casefold()}/"):
        return False
    item = ASR_ITEM_PATH.fullmatch(item_id[len(vault):])
    return item is not None and not {".", ".."}.intersection(item.groups())


def asr_recovery_point(properties):
    details = properties.get("providerSpecificDetails")
    value = details.get("lastRecoveryPointReceived") if isinstance(details, dict) else None
    if isinstance(value, str) and len(value) <= 40:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.utcoffset() is not None:
            return value
    return None


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
                if collection == "replication_items" and status == "synced":
                    status = "partial_failure"
                continue
            if collection == "replication_items" and not asr_item_in_vault(item.get("id"), vault):
                if status == "synced":
                    status = "partial_failure"
                continue
            row = {key: props[key][:512] for key in PROPERTIES[collection] if isinstance(props.get(key), str)}
            if collection == "policies":
                name = item.get("name")
                if isinstance(name, str):
                    row["name"] = name[:160]
                row["retention"] = retention_summary(props.get("retentionPolicy"))
            if collection == "replication_items":
                point = asr_recovery_point(props)
                if point:
                    row["lastRecoveryPointReceived"] = point
            rows.append(row)
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
            jobs, items, policies, replication = await asyncio.gather(
                read_rows(http, semaphore, headers, vault, "jobs", "backupJobs", "2025-08-01"),
                read_rows(http, semaphore, headers, vault, "protected_items", "backupProtectedItems", "2025-02-01"),
                read_rows(http, semaphore, headers, vault, "policies", "backupPolicies", "2025-08-01"),
                read_rows(http, semaphore, headers, vault, "replication_items", "replicationProtectedItems", "2025-08-01"),
            )
            return {"id": vault, "name": name, "jobs": jobs, "protected_items": items, "policies": policies,
                    "replication_items": replication}

        return await asyncio.gather(*(collect(*vault) for vault in vaults))


@router.get("/backup/evidence")
async def backup_evidence(request: Request, subscription_id: UUID | None = None,
                          client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db)):
    context = await observation_context(db, client_id, subscription_id)
    if not context or not context.inventory_exists:
        return {"status": "inventory_required" if context else "not_configured", "vaults": [], "limitations": []}
    all_vaults = vaults_for_inventory(context.resources, context.subscription_id)
    limitations = ["Each vault shows up to 25 records per evidence type from the first Azure response page.",
                   "Retention is shown for supported policy shapes. Restore jobs and recovery points require separate validation against recovery objectives.",
                   "Site Recovery last recovery point received times are shown where provided. Replication status alone cannot establish recovery readiness."]
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
        statuses = {vault[key]["status"] for vault in vaults for key in PROPERTIES}
        status = next(iter(statuses)) if len(statuses) == 1 else "partial_failure"
    await confirm_active_connection(db, request, client_id, context.ciphertext)
    return {"status": status, "retrieved_at": datetime.now(timezone.utc), "vaults": vaults, "limitations": limitations}
