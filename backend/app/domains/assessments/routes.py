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
from app.domains.access.azure import connection_values, select_subscription
from app.domains.monitoring.observation_models import AzureHealthIncident, AzureIncidentSecurityEvidence, AzureObservation
from .models import Assessment, AssessmentFinding, FindingEvent, FindingRiskAcceptance, VulnerabilitySlaPolicy
from .sla import FindingSlaRead, finding_sla
from .sla import router as sla_router

router = APIRouter()
router.include_router(sla_router)
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


class AzureFindingImport(RecordInput):
    subscription_id: UUID
    finding_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    collected_at: AwareDatetime


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


class IncidentLinkRead(BaseModel):
    id: UUID
    status: str
    owner: str | None
    linked_at: AwareDatetime


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
    sla: FindingSlaRead | None = None
    incident_links: list[IncidentLinkRead] = Field(default_factory=list)


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
    sla: FindingSlaRead | None = None


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
               finding.status, finding.owner, finding.due_date, finding.observed_at, finding.created_at)
        .join(Assessment, finding.assessment_id == Assessment.id)
        .where(Assessment.client_id == client_id)
        .order_by(severity, finding.created_at.desc(), finding.id)
        .offset((page - 1) * page_size)
        .limit(page_size + 1)
    )
    rows = (await db.execute(query)).mappings().all()
    policy = await db.get(VulnerabilitySlaPolicy, client_id) if rows else None
    today = datetime.now(timezone.utc).date()
    return PortfolioPage(findings=[
        PortfolioFinding.model_validate(row).model_copy(update={"sla": finding_sla(row, policy, today)})
        for row in rows[:page_size]
    ], has_next=page < 1000 and len(rows) > page_size)


@router.get("/{assessment_id}", response_model=AssessmentDetail)
async def assessment_detail(assessment_id: UUID, client_id: UUID = Depends(client_access),
                            db: AsyncSession = Depends(get_db)):
    item = await scoped_assessment(db, client_id, assessment_id)
    findings = (await db.scalars(select(AssessmentFinding).where(AssessmentFinding.assessment_id == item.id)
                                 .order_by(AssessmentFinding.created_at.desc(), AssessmentFinding.id))).all()
    history = {}
    risk_acceptances = {}
    incident_links = {}
    policy = await db.get(VulnerabilitySlaPolicy, client_id) if findings else None
    today = datetime.now(timezone.utc).date()
    if findings:
        for event in await db.scalars(select(FindingEvent).join(AssessmentFinding).where(
            AssessmentFinding.assessment_id == item.id
        ).order_by(FindingEvent.created_at, FindingEvent.id)):
            history.setdefault(event.finding_id, []).append(EventRead.model_validate(event))
        latest = (latest_risk_acceptances().join(AssessmentFinding)
                  .where(AssessmentFinding.assessment_id == item.id).distinct(FindingRiskAcceptance.finding_id))
        for decision in await db.scalars(latest):
            risk_acceptances[decision.finding_id] = RiskAcceptanceRead.model_validate(decision)
        azure_finding_ids = [
            finding.external_id for finding in findings
            if len(finding.external_id) == 64 and all(character in "0123456789abcdef" for character in finding.external_id)
        ]
        if azure_finding_ids:
            rows = await db.execute(select(
                AzureIncidentSecurityEvidence.finding_id,
                AzureHealthIncident.id,
                AzureHealthIncident.status,
                AzureHealthIncident.owner,
                AzureIncidentSecurityEvidence.linked_at,
            ).join(AzureHealthIncident, AzureHealthIncident.id == AzureIncidentSecurityEvidence.incident_id).where(
                AzureHealthIncident.client_id == client_id,
                AzureIncidentSecurityEvidence.finding_id.in_(azure_finding_ids),
            ).order_by(AzureIncidentSecurityEvidence.linked_at, AzureHealthIncident.id))
            for external_id, incident_id, status, owner, linked_at in rows:
                incident_links.setdefault(external_id, []).append(IncidentLinkRead(
                    id=incident_id, status=status, owner=owner, linked_at=linked_at,
                ))
    return AssessmentDetail(**AssessmentRead.model_validate(item).model_dump(), findings=[
        FindingRead.model_validate(finding).model_copy(update={
            "history": history.get(finding.id, []), "risk_acceptance": risk_acceptances.get(finding.id),
            "sla": finding_sla(finding, policy, today),
            "incident_links": incident_links.get(finding.external_id, []),
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


def stored_azure_finding(snapshot, finding_id):
    return next((item for item in snapshot.payload.get("findings", []) if item.get("id") == finding_id), None)


def azure_finding_import(finding, collected_at):
    evidence = finding.get("evidence")
    if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
        raise HTTPException(409, "Saved Azure finding evidence is invalid")
    source = finding.get("source")
    title = finding.get("title")
    severity = finding.get("severity")
    if (not isinstance(source, str) or not isinstance(title, str) or severity not in Severity.__args__
            or len(source) > 100 or len(title) > 240):
        raise HTTPException(409, "Saved Azure finding does not fit the assessment evidence contract")
    evidence_text = "\n".join(evidence)
    if not evidence_text or len(evidence_text) > 2000:
        raise HTTPException(409, "Saved Azure finding evidence does not fit the assessment evidence contract")
    code = finding.get("code") if isinstance(finding.get("code"), str) else "unspecified"
    source_observed = finding.get("observed_at") if isinstance(finding.get("observed_at"), str) else "not reported"
    methodology = (
        f"Stored Azure evidence; code {code}; source observed {source_observed}; "
        f"snapshot {collected_at.isoformat()}"
    )
    return {
        "external_id": finding["id"], "title": title, "severity": severity, "source": source.casefold(),
        "evidence": evidence_text, "methodology": methodology[:400], "observed_at": collected_at,
    }


@router.post("/{assessment_id}/findings/import-azure")
async def import_azure_finding(assessment_id: UUID, payload: AzureFindingImport, request: Request,
                               client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db)):
    assessment = await scoped_assessment(db, client_id, assessment_id)
    selected = select_subscription(await connection_values(db, client_id), payload.subscription_id)
    snapshot = await db.get(AzureObservation, (client_id, UUID(selected), "security")) if selected else None
    if snapshot is None or snapshot.last_success_at is None:
        raise HTTPException(404, "Saved Azure security evidence not found")
    if snapshot.last_success_at != payload.collected_at:
        raise HTTPException(409, "Saved Azure security evidence changed. Reload it before importing.")
    if not assessment.window_start <= payload.collected_at <= assessment.window_end:
        raise HTTPException(422, "Azure evidence collection time is outside the recorded assessment window")
    finding = stored_azure_finding(snapshot, payload.finding_id)
    if finding is None:
        raise HTTPException(404, "Saved Azure security finding not found")
    values = {"assessment_id": assessment_id, **azure_finding_import(finding, payload.collected_at), "status": "open"}
    finding_id = await db.scalar(insert(AssessmentFinding).values(values).on_conflict_do_nothing(
        constraint="uq_assessment_finding_source"
    ).returning(AssessmentFinding.id))
    audit(db, "import_azure_security_finding", request.state.account, client_id, payload.finding_id,
          outcome="success" if finding_id else "duplicate")
    await db.commit()
    return {"inserted": bool(finding_id), "duplicate": finding_id is None}


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
    policy = await db.get(VulnerabilitySlaPolicy, client_id)
    result = FindingRead.model_validate(item).model_copy(update={
        "risk_acceptance": RiskAcceptanceRead.model_validate(decision) if decision else None,
        "sla": finding_sla(item, policy, datetime.now(timezone.utc).date()),
    })
    await db.commit()
    return result
