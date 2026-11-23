"""Client-scoped records for authorized human-led security work."""

from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator
from sqlalchemy import case, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.access.routes import audit, client_access, client_admin, get_db
from .models import Assessment, AssessmentFinding, FindingEvent, FindingRiskAcceptance

router = APIRouter()
Severity = Literal["critical", "high", "medium", "low", "informational"]
FindingStatus = Literal["open", "confirmed", "in_remediation", "ready_for_retest", "closed"]
TRANSITIONS = {
    "open": {"confirmed"}, "confirmed": {"open", "in_remediation"},
    "in_remediation": {"open", "ready_for_retest"}, "ready_for_retest": {"open", "in_remediation", "closed"},
    "closed": {"open"},
}


class RecordInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AssessmentWrite(RecordInput):
    name: str = Field(min_length=1, max_length=180)
    scope: str = Field(min_length=1, max_length=4000)
    authorization: str = Field(min_length=1, max_length=2000)
    environment: str | None = Field(default=None, max_length=80)
    window_start: AwareDatetime
    window_end: AwareDatetime

    @model_validator(mode="after")
    def ordered_window(self):
        if self.window_end <= self.window_start:
            raise ValueError("The testing window must end after it starts")
        return self


class AssessmentRead(AssessmentWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: AwareDatetime


class FindingImport(RecordInput):
    external_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=240)
    severity: Severity
    source: str = Field(min_length=1, max_length=100)
    evidence: str = Field(min_length=1, max_length=2000)
    tool_version: str | None = Field(default=None, max_length=100)
    methodology: str | None = Field(default=None, max_length=400)
    observed_at: AwareDatetime | None = None

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, value):
        return value.casefold() if isinstance(value, str) else value


class ImportBatch(RecordInput):
    findings: list[FindingImport] = Field(min_length=1, max_length=100)


class TrackingWrite(RecordInput):
    status: FindingStatus
    owner: str | None = Field(default=None, max_length=120)
    due_date: date | None = None
    retest_note: str | None = Field(default=None, max_length=2000)


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    status: FindingStatus
    note: str | None
    created_at: AwareDatetime


class RiskAcceptanceWrite(RecordInput):
    rationale: str = Field(min_length=1, max_length=2000)
    expires_on: date
    previous_id: UUID | None = None


class RiskAcceptanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    rationale: str
    expires_on: date
    actor_username: str
    created_at: AwareDatetime

    @computed_field
    @property
    def active(self) -> bool:
        return self.expires_on > datetime.now(timezone.utc).date()


class FindingRead(FindingImport, TrackingWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: AwareDatetime
    history: list[EventRead] = Field(default_factory=list)
    risk_acceptance: RiskAcceptanceRead | None = None


class AssessmentDetail(AssessmentRead):
    findings: list[FindingRead] = Field(default_factory=list)


class PortfolioFinding(BaseModel):
    id: UUID
    assessment_id: UUID
    assessment_name: str
    title: str
    severity: Severity
    source: str
    evidence: str
    status: FindingStatus
    owner: str | None
    due_date: date | None
    observed_at: AwareDatetime | None


class PortfolioPage(BaseModel):
    findings: list[PortfolioFinding]
    has_next: bool


async def scoped_assessment(db, client_id, assessment_id):
    item = await db.scalar(select(Assessment).where(Assessment.id == assessment_id, Assessment.client_id == client_id))
    if not item:
        raise HTTPException(404, "Assessment not found")
    return item


def latest_risk_acceptances():
    decision = FindingRiskAcceptance
    return select(decision).order_by(decision.finding_id, decision.created_at.desc(), decision.id.desc())


@router.get("", response_model=list[AssessmentRead])
async def list_assessments(client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db)):
    return (await db.scalars(select(Assessment).where(Assessment.client_id == client_id)
                             .order_by(Assessment.created_at.desc(), Assessment.id))).all()


@router.post("", response_model=AssessmentDetail, status_code=201)
async def create_assessment(payload: AssessmentWrite, request: Request,
                            client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db)):
    item = Assessment(client_id=client_id, **payload.model_dump())
    db.add(item)
    await db.flush()
    audit(db, "create_security_assessment", request.state.account, client_id, str(item.id))
    await db.commit()
    return item


@router.get("/portfolio", response_model=PortfolioPage)
async def list_portfolio(page: int = Query(default=1, ge=1, le=1000),
                         client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db)):
    page_size = 25
    finding = AssessmentFinding
    severity = case(
        {"critical": 0, "high": 1, "medium": 2, "low": 3},
        value=finding.severity, else_=4,
    )
    query = (
        select(finding.id, finding.assessment_id, Assessment.name.label("assessment_name"),
               finding.title, finding.severity, finding.source, finding.evidence,
               finding.status, finding.owner, finding.due_date, finding.observed_at)
        .join(Assessment, finding.assessment_id == Assessment.id)
        .where(Assessment.client_id == client_id)
        .order_by(severity, finding.created_at.desc(), finding.id)
        .offset((page - 1) * page_size)
        .limit(page_size + 1)
    )
    rows = (await db.execute(query)).mappings().all()
    return PortfolioPage(findings=[PortfolioFinding.model_validate(row) for row in rows[:page_size]],
                         has_next=page < 1000 and len(rows) > page_size)


@router.get("/{assessment_id}", response_model=AssessmentDetail)
async def assessment_detail(assessment_id: UUID, client_id: UUID = Depends(client_access),
                            db: AsyncSession = Depends(get_db)):
    item = await scoped_assessment(db, client_id, assessment_id)
    findings = (await db.scalars(select(AssessmentFinding).where(AssessmentFinding.assessment_id == item.id)
                                 .order_by(AssessmentFinding.created_at.desc(), AssessmentFinding.id))).all()
    history = {}
    risk_acceptances = {}
    if findings:
        for event in await db.scalars(select(FindingEvent).join(AssessmentFinding).where(
            AssessmentFinding.assessment_id == item.id
        ).order_by(FindingEvent.created_at, FindingEvent.id)):
            history.setdefault(event.finding_id, []).append(EventRead.model_validate(event))
        latest = (latest_risk_acceptances().join(AssessmentFinding)
                  .where(AssessmentFinding.assessment_id == item.id).distinct(FindingRiskAcceptance.finding_id))
        for decision in await db.scalars(latest):
            risk_acceptances[decision.finding_id] = RiskAcceptanceRead.model_validate(decision)
    return AssessmentDetail(**AssessmentRead.model_validate(item).model_dump(), findings=[
        FindingRead.model_validate(finding).model_copy(update={
            "history": history.get(finding.id, []), "risk_acceptance": risk_acceptances.get(finding.id),
        })
        for finding in findings
    ])


@router.post("/{assessment_id}/findings/import")
async def import_findings(assessment_id: UUID, payload: ImportBatch, request: Request,
                          client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db)):
    item = await scoped_assessment(db, client_id, assessment_id)
    for finding in payload.findings:
        if finding.observed_at and not item.window_start <= finding.observed_at <= item.window_end:
            raise HTTPException(422, "Finding observation time is outside the recorded assessment window")
    values = [{"assessment_id": assessment_id, **finding.model_dump(), "status": "open"} for finding in payload.findings]
    rows = await db.execute(insert(AssessmentFinding).values(values).on_conflict_do_nothing(
        constraint="uq_assessment_finding_source"
    ).returning(AssessmentFinding.id))
    inserted = len(rows.scalars().all())
    audit(db, "import_security_findings", request.state.account, client_id, str(assessment_id))
    await db.commit()
    return {"inserted": inserted, "duplicates": len(values) - inserted}


@router.put("/{assessment_id}/findings/{finding_id}/risk-acceptance", response_model=RiskAcceptanceRead)
async def record_risk_acceptance(assessment_id: UUID, finding_id: UUID, payload: RiskAcceptanceWrite,
                                 request: Request, client_id: UUID = Depends(client_admin),
                                 db: AsyncSession = Depends(get_db)):
    await scoped_assessment(db, client_id, assessment_id)
    finding = await db.scalar(select(AssessmentFinding).where(
        AssessmentFinding.assessment_id == assessment_id, AssessmentFinding.id == finding_id
    ).with_for_update())
    if finding is None:
        raise HTTPException(404, "Finding not found")
    actor = request.state.account
    previous = await db.scalar(latest_risk_acceptances().where(FindingRiskAcceptance.finding_id == finding_id).limit(1))
    if (previous and previous.actor_id == actor.id and previous.rationale == payload.rationale
            and previous.expires_on == payload.expires_on):
        return previous
    if payload.previous_id != (previous.id if previous else None):
        raise HTTPException(409, "Risk acceptance changed. Reload the assessment before recording a decision.")
    if payload.expires_on <= datetime.now(timezone.utc).date():
        raise HTTPException(422, "The UTC expiry date must be in the future")
    if finding.status == "closed":
        raise HTTPException(409, "Risk acceptance can only be recorded for an open finding")
    decision = FindingRiskAcceptance(finding_id=finding_id, actor_id=actor.id, actor_username=actor.username,
                                     rationale=payload.rationale, expires_on=payload.expires_on)
    db.add(decision)
    await db.flush()
    audit(db, "record_vulnerability_risk_acceptance", actor, client_id, str(decision.id))
    await db.commit()
    return decision


@router.put("/{assessment_id}/findings/{finding_id}", response_model=FindingRead)
async def track_finding(assessment_id: UUID, finding_id: UUID, payload: TrackingWrite, request: Request,
                       client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db)):
    await scoped_assessment(db, client_id, assessment_id)
    item = await db.scalar(select(AssessmentFinding).where(
        AssessmentFinding.assessment_id == assessment_id, AssessmentFinding.id == finding_id
    ).with_for_update())
    if not item:
        raise HTTPException(404, "Finding not found")
    if payload.status != item.status and payload.status not in TRANSITIONS[item.status]:
        raise HTTPException(409, "Invalid finding status transition")
    updates = payload.model_dump(exclude_unset=True)
    note = updates.get("retest_note", item.retest_note)
    if payload.status == "closed" and not note:
        raise HTTPException(422, "Record a retest note before closing the finding")
    if payload.status == "open" and item.status != "open":
        updates["retest_note"] = None
    if payload.status != item.status or updates.get("retest_note", item.retest_note) != item.retest_note:
        db.add(FindingEvent(finding_id=item.id, actor_id=request.state.account.id,
                            status=payload.status, note=updates.get("retest_note", item.retest_note)))
    for key, value in updates.items():
        setattr(item, key, value or None if key in {"owner", "retest_note"} else value)
    audit(db, "track_security_assessment_finding", request.state.account, client_id, str(finding_id))
    decision = await db.scalar(latest_risk_acceptances().where(FindingRiskAcceptance.finding_id == finding_id).limit(1))
    result = FindingRead.model_validate(item).model_copy(update={
        "risk_acceptance": RiskAcceptanceRead.model_validate(decision) if decision else None,
    })
    await db.commit()
    return result
