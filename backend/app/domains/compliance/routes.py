from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.access.azure import connection_values, select_subscription
from app.domains.access.models import AzureConnection
from app.domains.access.routes import audit, client_access, get_db
from app.domains.monitoring.observation_models import AzureObservation

from .catalog import FRAMEWORK_CATALOG, FRAMEWORK_TOPICS
from .models import ComplianceReview

router = APIRouter()
NEUTRAL_TOPICS = {"transport", "storage", "network", "recovery", "scope"}


class ReviewWrite(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    applicability: Literal["undetermined", "applicable", "not_applicable"] | None = None
    outcome: Literal["review_required", "unable_to_validate", "pass", "fail"] | None = None
    state: Literal["in_review", "action_required", "reviewed"]
    note: str = Field(min_length=1, max_length=2000)
    action: str | None = Field(default=None, min_length=1, max_length=1200)
    owner: str | None = Field(default=None, min_length=1, max_length=120)
    due_date: date | None = None
    action_status: Literal["planned", "in_progress", "completed"] | None = None

    @model_validator(mode="after")
    def complete_action(self):
        if self.action is None and (
            self.state == "action_required" or self.owner or self.due_date or self.action_status
        ):
            raise ValueError("Provide the corrective action before assigning or tracking it")
        if self.action and not self.action_status:
            raise ValueError("Provide the corrective action status")
        return self


class ReviewSubmission(ReviewWrite):
    snapshot_attempt_at: AwareDatetime | None = None


class ReviewRead(ReviewWrite):
    model_config = ConfigDict(from_attributes=True)

    topic: str
    evidence_at: AwareDatetime | None
    updated_at: AwareDatetime


@router.get("/catalog")
async def read_catalog(_client_id: UUID = Depends(client_access)):
    return {"version": 1, "entries": FRAMEWORK_CATALOG}


@router.get("/reviews", response_model=list[ReviewRead])
async def read_reviews(subscription_id: UUID, client_id: UUID = Depends(client_access),
                       db: AsyncSession = Depends(get_db)):
    selected = select_subscription(await connection_values(db, client_id), subscription_id)
    if not selected:
        raise HTTPException(404, "Subscription not configured")
    return (await db.scalars(select(ComplianceReview).where(
        ComplianceReview.client_id == client_id, ComplianceReview.subscription_id == UUID(selected),
    ).order_by(ComplianceReview.topic))).all()


@router.put("/reviews/{topic}", response_model=ReviewRead)
async def save_review(topic: str, subscription_id: UUID, payload: ReviewSubmission, request: Request,
                      client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db)):
    if topic not in NEUTRAL_TOPICS and topic not in FRAMEWORK_TOPICS:
        raise HTTPException(404, "Review topic not found")
    applicability, outcome = payload.applicability, payload.outcome
    if topic in FRAMEWORK_TOPICS:
        if applicability is None:
            raise HTTPException(422, "Record the framework review applicability")
        if applicability == "not_applicable":
            if outcome is not None:
                raise HTTPException(422, "Leave the outcome blank for a non-applicable review")
        elif outcome is None or (applicability == "undetermined" and outcome in {"pass", "fail"}):
            raise HTTPException(422, "Choose a review outcome consistent with applicability")
    elif applicability is not None or outcome is not None:
        raise HTTPException(422, "Applicability and outcomes belong to framework review records")
    connection = await db.scalar(select(AzureConnection).where(
        AzureConnection.client_id == client_id,
    ).with_for_update())
    selected = select_subscription(
        await connection_values(db, client_id, connection) if connection else None, subscription_id,
    )
    if not selected:
        raise HTTPException(404, "Subscription not configured")

    selected_id = UUID(selected)
    snapshot = await db.get(AzureObservation, (client_id, selected_id, "security"))
    if payload.snapshot_attempt_at != (snapshot.last_attempt_at if snapshot else None):
        raise HTTPException(409, "Azure evidence changed. Reload the saved snapshot before reviewing.")
    evidence_at = None
    if snapshot:
        evidence_at = snapshot.last_success_at
        if not evidence_at and snapshot.status == "partial_failure":
            evidence_at = snapshot.last_attempt_at

    values = {**payload.model_dump(exclude={"snapshot_attempt_at"}), "evidence_at": evidence_at, "updated_at": func.now()}
    review = await db.scalar(insert(ComplianceReview).values(
        client_id=client_id, subscription_id=selected_id, topic=topic, **values,
    ).on_conflict_do_update(
        index_elements=[ComplianceReview.client_id, ComplianceReview.subscription_id, ComplianceReview.topic],
        set_=values,
    ).returning(ComplianceReview))
    response = ReviewRead.model_validate(review)
    audit(db, "update_compliance_review", request.state.account, client_id, f"{selected}:{topic}")
    await db.commit()
    return response
