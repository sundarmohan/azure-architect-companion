"""Client-configured vulnerability remediation deadlines for imported findings."""

from datetime import date, datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.access.models import Client
from app.domains.access.routes import audit, client_access, client_admin, get_db
from .models import VulnerabilitySlaPolicy

router = APIRouter()
DeadlineDays = Annotated[int, Field(strict=True, ge=1, le=3650)]


class SlaPolicyFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    critical_days: DeadlineDays
    high_days: DeadlineDays
    medium_days: DeadlineDays
    low_days: DeadlineDays
    informational_days: DeadlineDays


class SlaPolicyWrite(SlaPolicyFields):
    updated_at: AwareDatetime | None = None


class SlaPolicyRead(SlaPolicyFields):
    model_config = ConfigDict(from_attributes=True)
    updated_at: AwareDatetime


class FindingSlaRead(BaseModel):
    age_days: int
    age_source: Literal["observed", "imported"]
    deadline: date | None
    deadline_source: Literal["manual", "policy"] | None
    status: Literal["closed", "unconfigured", "overdue", "due_today", "on_track"]


def finding_sla(finding, policy, today):
    since = (finding.observed_at or finding.created_at).astimezone(timezone.utc).date()
    deadline = finding.due_date
    source = "manual" if deadline else None
    if deadline is None and policy:
        days = getattr(policy, f"{finding.severity}_days")
        deadline = date.fromordinal(min(since.toordinal() + days, date.max.toordinal()))
        source = "policy"
    if finding.status == "closed":
        status = "closed"
    elif deadline is None:
        status = "unconfigured"
    elif deadline < today:
        status = "overdue"
    elif deadline == today:
        status = "due_today"
    else:
        status = "on_track"
    return FindingSlaRead(age_days=max(0, (today - since).days),
                          age_source="observed" if finding.observed_at else "imported",
                          deadline=deadline, deadline_source=source, status=status)


@router.get("/sla-policy", response_model=SlaPolicyRead | None)
async def read_sla_policy(client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db)):
    return await db.get(VulnerabilitySlaPolicy, client_id)


@router.put("/sla-policy", response_model=SlaPolicyRead)
async def save_sla_policy(payload: SlaPolicyWrite, request: Request, client_id: UUID = Depends(client_admin),
                          db: AsyncSession = Depends(get_db)):
    await db.scalar(select(Client.id).where(Client.id == client_id).with_for_update())
    policy = await db.get(VulnerabilitySlaPolicy, client_id)
    values = payload.model_dump(exclude={"updated_at"})
    if policy and all(getattr(policy, field) == value for field, value in values.items()):
        return SlaPolicyRead.model_validate(policy)
    if payload.updated_at != (policy.updated_at if policy else None):
        raise HTTPException(409, "SLA policy changed. Reload it before editing.")
    if policy is None:
        policy = VulnerabilitySlaPolicy(client_id=client_id, **values)
        db.add(policy)
    else:
        for field, value in values.items():
            setattr(policy, field, value)
        policy.updated_at = datetime.now(timezone.utc)
    await db.flush()
    audit(db, "update_vulnerability_sla_policy", request.state.account, client_id, str(client_id))
    result = SlaPolicyRead.model_validate(policy)
    await db.commit()
    return result
