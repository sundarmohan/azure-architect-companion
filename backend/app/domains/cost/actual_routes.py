"""Read-only actual Azure cost queries for a configured client subscription."""

import asyncio
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.access.azure import confirm_active_connection, connection_values, select_subscription
from app.domains.access.models import AzureConnection
from app.domains.access.routes import client_access, get_db
from .azure_cost_management_adapter import AzureCostManagementAdapter
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
