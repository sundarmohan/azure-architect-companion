"""Read-only actual Azure cost queries for a configured client subscription."""

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.access.azure import confirm_active_connection, connection_values, select_subscription
from app.domains.access.models import AzureConnection
from app.domains.access.routes import audit, client_access, get_db
from .advisor import AdvisorCostRead, read_advisor_cost
from .azure_cost_management_adapter import AzureCostManagementAdapter
from .models import AzureCostBudget
from .schemas import ActualCostDailyItem

router = APIRouter()


class SubscriptionActualCostRead(BaseModel):
    subscription_id: UUID
    start_date: date
    end_date: date
    available: bool
    currency: str | None = None
    total_cost: float | None = None
    daily: list[ActualCostDailyItem] = Field(default_factory=list)
    retrieved_at: datetime | None = None
    error: str | None = None


class BudgetWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


@router.get("/recommendations", response_model=AdvisorCostRead)
async def read_cost_recommendations(
    request: Request,
    subscription_id: UUID,
    client_id: UUID = Depends(client_access),
    db: AsyncSession = Depends(get_db),
):
    connection = await db.get(AzureConnection, client_id)
    values = await connection_values(db, client_id, connection) if connection else None
    selected = select_subscription(values, subscription_id)
    ciphertext = connection.ciphertext
    await db.rollback()
    result = await read_advisor_cost(selected, values)
    await confirm_active_connection(db, request, client_id, ciphertext)
    return result


@router.get("/budget", response_model=BudgetWrite | None)
async def read_budget(
    subscription_id: UUID,
    client_id: UUID = Depends(client_access),
    db: AsyncSession = Depends(get_db),
):
    select_subscription(await connection_values(db, client_id), subscription_id)
    return await db.get(AzureCostBudget, (client_id, subscription_id))


@router.put("/budget", response_model=BudgetWrite)
async def save_budget(
    payload: BudgetWrite,
    request: Request,
    subscription_id: UUID,
    client_id: UUID = Depends(client_access),
    db: AsyncSession = Depends(get_db),
):
    connection = await db.scalar(select(AzureConnection).where(AzureConnection.client_id == client_id).with_for_update())
    values = await connection_values(db, client_id, connection) if connection else None
    select_subscription(values, subscription_id)
    changes = payload.model_dump()
    await db.execute(insert(AzureCostBudget).values(client_id=client_id, subscription_id=subscription_id, **changes)
                     .on_conflict_do_update(index_elements=[AzureCostBudget.client_id, AzureCostBudget.subscription_id],
                                            set_=changes))
    audit(db, "save_azure_cost_budget", request.state.account, client_id, str(subscription_id))
    await db.commit()
    return payload


@router.get("/actual", response_model=SubscriptionActualCostRead)
async def read_actual_cost(
    request: Request,
    start_date: date,
    end_date: date,
    subscription_id: UUID | None = None,
    client_id: UUID = Depends(client_access),
    db: AsyncSession = Depends(get_db),
):
    if not start_date <= end_date <= datetime.now(timezone.utc).date() or (end_date - start_date).days >= 31:
        raise HTTPException(422, "Choose a date range of at most 31 days ending today or earlier")
    connection = await db.get(AzureConnection, client_id)
    values = await connection_values(db, client_id, connection) if connection else None
    selected = select_subscription(values, subscription_id)
    if selected is None:
        raise HTTPException(404, "Azure subscription is not configured")

    ciphertext = connection.ciphertext
    await db.rollback()
    try:
        async with asyncio.timeout(30):
            result = await AzureCostManagementAdapter().get_actual_cost(
                subscription_id=selected, start_date=start_date, end_date=end_date, credentials=values,
            )
    except TimeoutError:
        result = {"available": False, "error": "Azure Cost Management query timed out"}

    await confirm_active_connection(db, request, client_id, ciphertext)
    return SubscriptionActualCostRead(
        subscription_id=selected, start_date=start_date, end_date=end_date,
        available=result["available"], currency=result.get("currency"), total_cost=result.get("total_cost"),
        daily=result.get("daily", []), retrieved_at=result.get("retrieved_at"), error=result.get("error"),
    )
