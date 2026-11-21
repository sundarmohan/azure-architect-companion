import json
import os
from uuid import UUID

import httpx
from azure.identity.aio import ClientSecretCredential
from azure.core.exceptions import AzureError
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.settings.schemas import AzureIntegrationStatusRead
from .models import AzureConnection, AzureInventorySnapshot
from .routes import audit, client_access, client_admin, get_db

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


def status_for(values=None, state=None, **extra):
    return ConnectionStatus(
        configured_subscription_ids=subscription_ids(values),
        enabled=bool(values),
        configuration_state="configured" if values else "not_configured",
        connection_state=state or ("configured" if values else "not_configured"),
        configured_tenant_id=values["tenant_id"] if values else None,
        configured_subscription_id=values["subscription_id"] if values else None,
        configured_client_id_hint=values["client_id"][-4:] if values else None,
        **extra,
    )


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
async def read_status(client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db)):
    return status_for(await connection_values(db, client_id))


@router.put("/credentials", response_model=ConnectionStatus)
async def save_credentials(payload: Credentials, request: Request, client_id: UUID = Depends(client_admin),
                           db: AsyncSession = Depends(get_db)):
    values = payload.model_dump(mode="json")
    values["client_secret"] = payload.client_secret.get_secret_value()
    values["additional_subscription_ids"] = [
        item for item in dict.fromkeys(values["additional_subscription_ids"]) if item != values["subscription_id"]
    ]
    encrypted = cipher().encrypt(json.dumps(dict(values, workspace_id=str(client_id))).encode()).decode()
    await db.execute(insert(AzureConnection).values(client_id=client_id, ciphertext=encrypted)
        .on_conflict_do_update(index_elements=[AzureConnection.client_id], set_={"ciphertext": encrypted}))
    await db.execute(delete(AzureInventorySnapshot).where(
        AzureInventorySnapshot.client_id == client_id,
        AzureInventorySnapshot.subscription_id.not_in([UUID(item) for item in subscription_ids(values)]),
    ))
    audit(db, "save_azure_connection", request.state.account, client_id)
    await db.commit()
    return status_for(values)


@router.delete("/credentials", response_model=ConnectionStatus)
async def clear_credentials(request: Request, client_id: UUID = Depends(client_admin),
                            db: AsyncSession = Depends(get_db)):
    await db.execute(delete(AzureConnection).where(AzureConnection.client_id == client_id))
    await db.execute(delete(AzureInventorySnapshot).where(AzureInventorySnapshot.client_id == client_id))
    audit(db, "clear_azure_connection", request.state.account, client_id)
    await db.commit()
    return status_for()


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
    values = await connection_values(db, client_id)
    selected = select_subscription(values, subscription_id)
    if not selected:
        return status_for()
    try:
        response = await check_subscription(dict(values, subscription_id=selected))
        state = {200: "configured", 401: "authentication_failure", 403: "permission_failure"}.get(
            response.status_code, "provider_error")
    except AzureError:
        state = "authentication_failure"
    except httpx.HTTPError:
        state = "provider_error"
    audit(db, "test_azure_connection", request.state.account, client_id, selected,
          outcome="success" if state == "configured" else "failed")
    await db.commit()
    return status_for(values, state)
