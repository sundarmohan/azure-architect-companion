import re
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, computed_field, model_validator
from sqlalchemy import case, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.access.routes import audit, client_access, get_db

from .models import RepositoryFinding
router = APIRouter()

Category = Literal["dependency", "container", "iac", "secrets", "dockerfile"]
Severity = Literal["critical", "high", "medium", "low", "informational"]
RECOMMENDATIONS = {
    "dependency": "Review the affected dependency and plan an upgrade or approved mitigation.",
    "container": "Review the affected image and validate a rebuild from a patched base or package.",
    "iac": "Review the configuration finding and validate the proposed infrastructure change.",
    "secrets": "Verify exposure through your approved process and rotate the affected credential if needed.",
    "dockerfile": "Review the Dockerfile finding and validate the image build after correction.",
}
CREDENTIAL_PREFIX = re.compile(r"(?:gh[pousr]_|github_pat_|xox[baprs]-|(?:AKIA|ASIA)[A-Z0-9]{16})", re.I)
PAGE_SIZE = 25


class FindingWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    owner: str = Field(pattern=r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?$")
    repository: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")
    source: str = Field(min_length=1, max_length=60, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    category: Category
    severity: Severity
    commit_sha: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    image: str | None = Field(default=None, max_length=255,
        pattern=r"^[a-z0-9][a-z0-9_.-]*(?::[0-9]{1,5})?(?:/[a-z0-9][a-z0-9_.-]*)*(?::[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})?(?:@sha256:[0-9a-f]{64})?$")

    @model_validator(mode="after")
    def normalize_reference(self):
        if self.repository in {".", ".."} or (self.image and (
            "//" in self.image or any(segment in {".", "..", ""} for segment in self.image.split("/"))
        )):
            raise ValueError("Provide valid repository and image identifiers")
        if any(CREDENTIAL_PREFIX.search(value) for value in (
            self.owner, self.repository, self.source, self.image or "",
        )):
            raise ValueError("Credential-shaped values are not permitted in repository metadata")
        self.owner = self.owner.lower()
        self.repository = self.repository.lower()
        self.source = self.source.lower()
        return self


class FindingRead(FindingWrite):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: AwareDatetime

    @computed_field
    @property
    def recommendation(self) -> str:
        return RECOMMENDATIONS[self.category]


class FindingPage(BaseModel):
    findings: list[FindingRead]
    has_next: bool


class FindingBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    findings: list[FindingWrite] = Field(min_length=1, max_length=50)


class BatchRead(BaseModel):
    inserted: int
    duplicates: int


@router.get("/findings", response_model=FindingPage)
async def list_findings(page: int = Query(default=1, ge=1, le=1000),
                        client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db)):
    severity = case({"critical": 0, "high": 1, "medium": 2, "low": 3},
                    value=RepositoryFinding.severity, else_=4)
    rows = (await db.scalars(select(RepositoryFinding).where(RepositoryFinding.client_id == client_id)
                            .order_by(severity, RepositoryFinding.created_at.desc(), RepositoryFinding.id)
                            .offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE + 1))).all()
    return FindingPage(findings=[FindingRead.model_validate(row) for row in rows[:PAGE_SIZE]],
                       has_next=page < 1000 and len(rows) > PAGE_SIZE)


@router.post("/findings/import", response_model=BatchRead)
async def import_findings(payload: FindingBatch, request: Request, client_id: UUID = Depends(client_access),
                          db: AsyncSession = Depends(get_db)):
    values = [{"client_id": client_id, **item.model_dump()} for item in payload.findings]
    rows = await db.scalars(insert(RepositoryFinding).values(values).on_conflict_do_nothing(
        constraint="uq_devsecops_finding_source",
    ).returning(RepositoryFinding.id))
    count = len(rows.all())
    if count:
        audit(db, "import_devsecops_findings", request.state.account, client_id, str(count))
    await db.commit()
    return BatchRead(inserted=count, duplicates=len(values) - count)
