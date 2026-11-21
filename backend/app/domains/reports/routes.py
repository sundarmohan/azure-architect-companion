from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.domains.architecture.models import (
    Architecture,
    ArchitectureRelationship,
    ArchitectureResource,
    AzureResourceGroup,
    AzureSubscription,
)

from .schemas import ArchitectureExecutiveReportRead, ExecutiveReportRequest
from .service import ExecutiveReportService

router = APIRouter()


async def get_db():
    async with SessionLocal() as session:
        yield session


async def _get_architecture_or_404(db: AsyncSession, architecture_id: UUID) -> Architecture:
    architecture = await db.get(Architecture, architecture_id)
    if not architecture:
        raise HTTPException(status_code=404, detail="Architecture not found")
    return architecture


@router.post("/architectures/{architecture_id}/executive-summary", response_model=ArchitectureExecutiveReportRead)
async def get_architecture_executive_summary(
    architecture_id: UUID,
    payload: ExecutiveReportRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    architecture = await _get_architecture_or_404(db, architecture_id)

    resources_result = await db.execute(
        select(ArchitectureResource)
        .where(ArchitectureResource.architecture_id == architecture_id)
        .order_by(ArchitectureResource.created_at)
    )
    resources = list(resources_result.scalars().all())

    relationships_result = await db.execute(
        select(ArchitectureRelationship)
        .where(ArchitectureRelationship.architecture_id == architecture_id)
        .order_by(ArchitectureRelationship.created_at)
    )
    relationships = list(relationships_result.scalars().all())

    groups_result = await db.execute(
        select(AzureResourceGroup)
        .where(AzureResourceGroup.architecture_id == architecture_id)
        .order_by(AzureResourceGroup.created_at)
    )
    resource_groups = list(groups_result.scalars().all())

    subscriptions_result = await db.execute(
        select(AzureSubscription)
        .where(AzureSubscription.architecture_id == architecture_id)
        .order_by(AzureSubscription.created_at)
    )
    subscriptions = list(subscriptions_result.scalars().all())

    service = ExecutiveReportService()
    return await service.build_architecture_executive_report(
        db=db,
        architecture=architecture,
        resources=resources,
        relationships=relationships,
        resource_groups=resource_groups,
        subscriptions=subscriptions,
        request=payload or ExecutiveReportRequest(),
    )
