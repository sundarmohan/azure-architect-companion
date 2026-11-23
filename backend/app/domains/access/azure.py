import asyncio
import json
import os
from datetime import datetime, timezone
from uuid import UUID

import httpx
from azure.identity.aio import ClientSecretCredential
from azure.core.exceptions import AzureError, ClientAuthenticationError, HttpResponseError, ServiceRequestError
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.monitoring.observation_models import AzureObservation, AzureObservationSchedule, AzureSecurityTracking
from app.domains.settings.schemas import AzureIntegrationStatusRead
from .models import AzureConnection, AzureInventorySnapshot, Client
from .routes import audit, client_access, client_admin, current_account, get_db

router = APIRouter()


class Credentials(BaseModel):
    tenant_id: UUID
    client_id: UUID
    subscription_id: UUID
    additional_subscription_ids: list[UUID] = Field(default_factory=list, max_length=25)
    client_secret: SecretStr = Field(min_length=1, max_length=4096)


def cipher() -> Fernet:
    try:
        return Fernet(os.environ["MONITORAI_AZURE_ENCRYPTION_KEY"].encode())
    except (KeyError, ValueError):
        raise HTTPException(503, "Azure credential encryption is unavailable") from None


class ConnectionStatus(AzureIntegrationStatusRead):
    configured_subscription_ids: list[str] = Field(default_factory=list)


def subscription_ids(values):
    return [values["subscription_id"], *values.get("additional_subscription_ids", [])] if values else []


def select_subscription(values, subscription_id):
    if not values:
        if subscription_id:
            raise HTTPException(404, "Azure subscription is not configured")
        return None
    selected = str(subscription_id) if subscription_id else values["subscription_id"]
    if selected not in subscription_ids(values):
        raise HTTPException(404, "Azure subscription is not configured")
    return selected


def request_correlation_id(request):
    return getattr(request.state, "correlation_id", None) if request else None


def status_for(values=None, record=None, state=None, request=None, **extra):
    connection_state = state or (record.connection_state if record else None)
    return ConnectionStatus(
        configured_subscription_ids=subscription_ids(values),
        enabled=bool(values),
        configuration_state="configured" if values else "not_configured",
        connection_state=connection_state or ("unverified" if values else "not_configured"),
        configured_tenant_id=values["tenant_id"] if values else None,
        configured_subscription_id=values["subscription_id"] if values else None,
        configured_client_id_hint=values["client_id"][-4:] if values else None,
        last_tested_at=record.last_tested_at.isoformat() if record and record.last_tested_at else None,
        last_successful_test_at=record.last_success_at.isoformat() if record and record.last_success_at else None,
        failure_stage=record.failure_stage if record else None,
        failure_reason=record.failure_reason if record else None,
        correlation_id=request_correlation_id(request),
        **extra,
    )


def azure_failure(error, stage):
    """Map provider-boundary exceptions to bounded states without returning exception text."""
    if isinstance(error, ClientAuthenticationError):
        return "authentication_failure", stage, "credential_rejected"
    if isinstance(error, HttpResponseError):
        status = getattr(error, "status_code", None)
        if status == 401:
            return "authentication_failure", stage, "credential_rejected"
        if status == 403:
            return "permission_failure", stage, "insufficient_permission"
        if status == 429:
            return "provider_error", stage, "throttled"
        return "provider_error", stage, "azure_http_error"
    if isinstance(error, (httpx.TimeoutException, TimeoutError)):
        return "provider_error", stage, "timeout"
    if isinstance(error, (ServiceRequestError, httpx.HTTPError, OSError)):
        return "provider_error", stage, "network_error"
    if isinstance(error, (ValueError, KeyError, TypeError)):
        configuration_stage = stage in {"credential_setup", "token_acquisition"}
        return "configuration_error" if configuration_stage else "provider_error", stage, (
            "invalid_configuration" if configuration_stage else "invalid_response"
        )
    if isinstance(error, AzureError):
        return "provider_error", stage, "azure_sdk_error"
    return "provider_error", stage, "unexpected_provider_error"


def response_failure(status_code, stage):
    if status_code == 401:
        return "authentication_failure", stage, "credential_rejected"
    if status_code == 403:
        return "permission_failure", stage, "insufficient_permission"
    if status_code == 429:
        return "provider_error", stage, "throttled"
    if isinstance(status_code, int) and 400 <= status_code < 500:
        return "provider_error", stage, "azure_request_rejected"
    return "provider_error", stage, "azure_service_error"


async def connection_values(db, client_id, record=None):
    if record is None:
        record = await db.get(AzureConnection, client_id)
    if not record:
        return None
    try:
        values = json.loads(cipher().decrypt(record.ciphertext.encode()))
        if values.pop("workspace_id") != str(client_id):
            raise ValueError("Client mismatch")
        return values
    except (InvalidToken, ValueError, KeyError):
        raise HTTPException(503, "Azure credentials are unavailable") from None


@router.get("/status", response_model=ConnectionStatus)
async def read_status(request: Request, client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db)):
    record = await db.get(AzureConnection, client_id)
    return status_for(await connection_values(db, client_id, record) if record else None, record, request=request)


@router.put("/credentials", response_model=ConnectionStatus)
async def save_credentials(payload: Credentials, request: Request, client_id: UUID = Depends(client_admin),
                           db: AsyncSession = Depends(get_db)):
    await db.scalar(select(Client.id).where(Client.id == client_id).with_for_update())
    try:
        previous = await connection_values(db, client_id)
    except HTTPException as error:
        if error.status_code != 503:
            raise
        previous = None
    values = payload.model_dump(mode="json")
    values["client_secret"] = payload.client_secret.get_secret_value()
    values["additional_subscription_ids"] = [
        item for item in dict.fromkeys(values["additional_subscription_ids"]) if item != values["subscription_id"]
    ]
    encrypted = cipher().encrypt(json.dumps(dict(values, workspace_id=str(client_id))).encode()).decode()
    connection_changes = {
        "ciphertext": encrypted, "connection_state": "unverified", "last_tested_at": None,
        "last_success_at": None, "failure_stage": None, "failure_reason": None,
    }
    await db.execute(insert(AzureConnection).values(client_id=client_id, **connection_changes)
        .on_conflict_do_update(index_elements=[AzureConnection.client_id], set_=connection_changes))
    same_identity = previous and all(previous[key] == values[key] for key in ("tenant_id", "client_id"))
    retained = [UUID(item) for item in subscription_ids(values)] if same_identity else []
    await retire_observations(db, client_id, retained)
    audit(db, "save_azure_connection", request.state.account, client_id)
    await db.commit()
    return status_for(values, await db.get(AzureConnection, client_id), request=request)


async def retire_observations(db, client_id, retained):
    for model in (AzureInventorySnapshot, AzureObservation, AzureObservationSchedule, AzureSecurityTracking):
        query = delete(model).where(model.client_id == client_id)
        if retained:
            query = query.where(model.subscription_id.not_in(retained))
        await db.execute(query)


@router.delete("/credentials", response_model=ConnectionStatus)
async def clear_credentials(request: Request, client_id: UUID = Depends(client_admin),
                            db: AsyncSession = Depends(get_db)):
    await db.scalar(select(Client.id).where(Client.id == client_id).with_for_update())
    await db.execute(delete(AzureConnection).where(AzureConnection.client_id == client_id))
    await retire_observations(db, client_id, [])
    audit(db, "clear_azure_connection", request.state.account, client_id)
    await db.commit()
    return status_for(request=request)


async def confirm_active_connection(db, request, client_id, ciphertext, *, admin=False):
    account = await current_account(request, db)
    await client_access(request, db, account)
    if admin:
        await client_admin(request, client_id)
    current = await db.scalar(select(AzureConnection.ciphertext).where(
        AzureConnection.client_id == client_id
    ).with_for_update())
    if current != ciphertext:
        raise HTTPException(409, "Azure connection changed during the request")
    return account


async def check_subscription(values):
    async with ClientSecretCredential(tenant_id=values["tenant_id"], client_id=values["client_id"],
                                      client_secret=values["client_secret"]) as credential:
        token = await credential.get_token("https://management.azure.com/.default")
    async with httpx.AsyncClient(timeout=10) as http:
        return await http.get(
            f'https://management.azure.com/subscriptions/{values["subscription_id"]}',
            params={"api-version": "2020-01-01"}, headers={"Authorization": f"Bearer {token.token}"},
        )


@router.post("/test", response_model=ConnectionStatus)
async def test_connection(request: Request, subscription_id: UUID | None = None,
                          client_id: UUID = Depends(client_admin),
                          db: AsyncSession = Depends(get_db)):
    connection = await db.get(AzureConnection, client_id)
    values = await connection_values(db, client_id, connection) if connection else None
    selected = select_subscription(values, subscription_id)
    if not selected:
        return status_for(request=request)
    ciphertext = connection.ciphertext
    await db.rollback()
    tested_at = datetime.now(timezone.utc)
    try:
        async with asyncio.timeout(25):
            response = await check_subscription(dict(values, subscription_id=selected))
        if response.status_code == 200:
            state, stage, reason = "configured", None, None
        else:
            state, stage, reason = response_failure(response.status_code, "subscription_read")
    except Exception as error:
        state, stage, reason = azure_failure(error, "subscription_read")
    account = await confirm_active_connection(db, request, client_id, ciphertext, admin=True)
    current = await db.get(AzureConnection, client_id)
    current.connection_state = state
    current.last_tested_at = tested_at
    current.failure_stage = stage
    current.failure_reason = reason
    if state == "configured":
        current.last_success_at = tested_at
    audit(db, "test_azure_connection", account, client_id, selected,
          outcome="success" if state == "configured" else "failed")
    await db.commit()
    return status_for(values, current, request=request)
