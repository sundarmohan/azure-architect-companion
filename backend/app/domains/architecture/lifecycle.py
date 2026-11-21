from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.access.routes import audit, client_access, get_db
from .lifecycle_models import DesignLifecycleEvent, DesignRevision
from .models import (
    Architecture,
    ArchitectureDependency,
    ArchitectureRelationship,
    ArchitectureResource,
    AzureResourceGroup,
    AzureSubscription,
)
from .schemas import (
    ArchitectureRead,
    DependencyRead,
    RelationshipRead,
    ResourceGroupRead,
    ResourceRead,
    SubscriptionRead,
)

router = APIRouter()

DesignStatus = Literal["draft", "in_review", "approved", "archived"]
TRANSITIONS = {
    "draft": {"in_review", "archived"},
    "in_review": {"draft", "approved", "archived"},
    "approved": {"draft", "archived"},
    "archived": {"draft"},
}
GRAPH_SECTIONS = (
    ("subscriptions", AzureSubscription, SubscriptionRead),
    ("resource_groups", AzureResourceGroup, ResourceGroupRead),
    ("resources", ArchitectureResource, ResourceRead),
    ("relationships", ArchitectureRelationship, RelationshipRead),
    ("dependencies", ArchitectureDependency, DependencyRead),
)


class DuplicateDesign(BaseModel):
    name: str = Field(min_length=1, max_length=200, pattern=r"\S")


class ChangeStatus(BaseModel):
    status: DesignStatus
    note: str | None = Field(default=None, max_length=1000)


class DescribeRevision(BaseModel):
    description: str = Field(min_length=1, max_length=1000, pattern=r"\S")


class RevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    number: int
    description: str
    actor: str
    created_at: datetime


class RevisionDetail(RevisionRead):
    snapshot: dict


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: str
    from_status: str
    to_status: DesignStatus
    note: str | None
    actor: str
    created_at: datetime


async def scoped_design(db: AsyncSession, architecture_id: UUID, client_id: UUID, *, lock: bool = False):
    query = select(Architecture).where(Architecture.id == architecture_id, Architecture.client_id == client_id)
    if lock:
        query = query.with_for_update()
    design = await db.scalar(query)
    if design is None:
        raise HTTPException(404, "Architecture not found")
    return design


def require_draft(design: Architecture) -> None:
    if design.status != "draft":
        raise HTTPException(409, "Only draft designs can be changed")


async def capture_snapshot(db: AsyncSession, design: Architecture) -> dict:
    snapshot = {"architecture": ArchitectureRead.model_validate(design).model_dump(mode="json")}
    for section, model, schema in GRAPH_SECTIONS:
        rows = await db.scalars(select(model).where(model.architecture_id == design.id).order_by(model.id))
        snapshot[section] = [
            schema.model_validate(row).model_dump(mode="json", exclude={"architecture_id"}) for row in rows
        ]
    return snapshot


async def add_revision(db, design, actor, description, snapshot):
    latest = await db.scalar(select(func.max(DesignRevision.number)).where(
        DesignRevision.architecture_id == design.id
    ))
    revision = DesignRevision(
        architecture_id=design.id,
        number=(latest or 0) + 1,
        description=description,
        actor=actor,
        snapshot=snapshot,
    )
    db.add(revision)
    await db.flush()
    return revision


async def find_revision(db: AsyncSession, architecture_id: UUID, revision_id: UUID) -> DesignRevision:
    revision = await db.scalar(select(DesignRevision).where(
        DesignRevision.architecture_id == architecture_id, DesignRevision.id == revision_id
    ))
    if revision is None:
        raise HTTPException(404, "Revision not found")
    return revision


def replace_design_ids(value, ids: dict[str, str]):
    if isinstance(value, str):
        return ids.get(value, value)
    if isinstance(value, list):
        return [replace_design_ids(item, ids) for item in value]
    if isinstance(value, dict):
        return {ids.get(key, key): replace_design_ids(item, ids) for key, item in value.items()}
    return value


async def apply_graph_snapshot(db: AsyncSession, design: Architecture, snapshot: dict) -> None:
    # Delete children first. Keeping unchanged row identities preserves links
    # to those rows from operational records.
    for section, model, _ in reversed(GRAPH_SECTIONS):
        ids = [UUID(row["id"]) for row in snapshot[section]]
        await db.execute(delete(model).where(model.architecture_id == design.id, model.id.not_in(ids)))

    delayed_parents = []
    for section, model, schema in GRAPH_SECTIONS:
        existing = {
            row.id: row for row in
            await db.scalars(select(model).where(model.architecture_id == design.id))
        }
        for data in snapshot[section]:
            values = schema.model_validate({**data, "architecture_id": design.id}).model_dump()
            item_id = values.pop("id")
            parent_id = values.pop("parent_resource_id", None)
            item = existing.get(item_id)
            if item is None:
                item = model(id=item_id, **values)
                db.add(item)
            else:
                for key, value in values.items():
                    setattr(item, key, value)
            if section == "resources":
                delayed_parents.append((item, parent_id))
        await db.flush()

    for item, parent_id in delayed_parents:
        item.parent_resource_id = parent_id
    await db.flush()


@router.post("/{architecture_id}/duplicate", response_model=ArchitectureRead, status_code=201)
async def duplicate_design(
    architecture_id: UUID, payload: DuplicateDesign, request: Request,
    client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db),
):
    source = await scoped_design(db, architecture_id, client_id, lock=True)
    snapshot = await capture_snapshot(db, source)
    design_id = uuid4()
    ids = {str(source.id): str(design_id)}
    for section, _, _ in GRAPH_SECTIONS:
        ids.update({row["id"]: str(uuid4()) for row in snapshot[section]})
    snapshot = replace_design_ids(snapshot, ids)
    values = ArchitectureRead.model_validate(snapshot["architecture"]).model_dump(exclude={"id", "status", "name"})
    duplicate = Architecture(id=design_id, client_id=client_id, name=payload.name.strip(), status="draft", **values)
    db.add(duplicate)
    await db.flush()
    await apply_graph_snapshot(db, duplicate, snapshot)
    audit(db, "duplicate_design", request.state.account, client_id, target=str(duplicate.id))
    await db.commit()
    return duplicate


@router.post("/{architecture_id}/status", response_model=ArchitectureRead)
async def change_design_status(
    architecture_id: UUID, payload: ChangeStatus, request: Request,
    client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db),
):
    design = await scoped_design(db, architecture_id, client_id, lock=True)
    previous = design.status
    if payload.status not in TRANSITIONS[previous]:
        raise HTTPException(409, "Invalid design status transition")
    requires_admin = payload.status == "approved" or (payload.status == "draft" and previous in {"approved", "archived"})
    if requires_admin and request.state.client_role != "admin":
        raise HTTPException(403, "Client administrator required for this transition")
    account = request.state.account
    note = (payload.note or "").strip() or None
    design.status = payload.status
    db.add(DesignLifecycleEvent(architecture_id=design.id, action="status_changed", from_status=previous,
                                to_status=design.status, actor=account.username, note=note))
    if design.status == "approved":
        await add_revision(db, design, account.username, note or "Approved design", await capture_snapshot(db, design))
    audit(db, f"design_{design.status}", account, client_id, target=str(design.id))
    await db.commit()
    return design


@router.get("/{architecture_id}/history", response_model=list[EventRead])
async def design_history(
    architecture_id: UUID, client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db),
):
    await scoped_design(db, architecture_id, client_id)
    return (await db.scalars(select(DesignLifecycleEvent).where(
        DesignLifecycleEvent.architecture_id == architecture_id
    ).order_by(DesignLifecycleEvent.created_at.desc(), DesignLifecycleEvent.id))).all()


@router.get("/{architecture_id}/revisions", response_model=list[RevisionRead])
async def design_revisions(
    architecture_id: UUID, client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db),
):
    await scoped_design(db, architecture_id, client_id)
    return (await db.scalars(select(DesignRevision).where(
        DesignRevision.architecture_id == architecture_id
    ).order_by(DesignRevision.number.desc()))).all()


@router.post("/{architecture_id}/revisions", response_model=RevisionRead, status_code=201)
async def save_design_revision(
    architecture_id: UUID, payload: DescribeRevision, request: Request,
    client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db),
):
    design = await scoped_design(db, architecture_id, client_id, lock=True)
    require_draft(design)
    account = request.state.account
    revision = await add_revision(db, design, account.username, payload.description.strip(), await capture_snapshot(db, design))
    audit(db, "save_design_revision", account, client_id, target=str(design.id))
    await db.commit()
    return revision


@router.get("/{architecture_id}/revisions/{revision_id}", response_model=RevisionDetail)
async def design_revision(
    architecture_id: UUID, revision_id: UUID,
    client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db),
):
    await scoped_design(db, architecture_id, client_id)
    return await find_revision(db, architecture_id, revision_id)


def compare_snapshots(before: dict, after: dict) -> list[dict]:
    changes = []
    for section, values in before.items():
        if section == "architecture":
            left = {values["id"]: values}
            right = {after[section]["id"]: after[section]}
        else:
            left = {row["id"]: row for row in values}
            right = {row["id"]: row for row in after[section]}
        for row_id in sorted(left.keys() | right.keys()):
            previous, current = left.get(row_id), right.get(row_id)
            if previous != current:
                kind = "added" if previous is None else ("removed" if current is None else "changed")
                changes.append({"section": section, "id": row_id, "kind": kind, "before": previous, "after": current})
    return changes


@router.get("/{architecture_id}/revisions/{revision_id}/compare")
async def compare_design_revisions(
    architecture_id: UUID, revision_id: UUID, to: UUID,
    client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db),
):
    await scoped_design(db, architecture_id, client_id)
    before = await find_revision(db, architecture_id, revision_id)
    after = await find_revision(db, architecture_id, to)
    return {
        "from_revision": RevisionRead.model_validate(before),
        "to_revision": RevisionRead.model_validate(after),
        "changes": compare_snapshots(before.snapshot, after.snapshot),
    }


@router.post("/{architecture_id}/revisions/{revision_id}/restore", response_model=ArchitectureRead)
async def restore_design_revision(
    architecture_id: UUID, revision_id: UUID, payload: DescribeRevision, request: Request,
    client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db),
):
    design = await scoped_design(db, architecture_id, client_id, lock=True)
    require_draft(design)
    revision = await find_revision(db, architecture_id, revision_id)
    account = request.state.account
    await add_revision(db, design, account.username, "Before restore", await capture_snapshot(db, design))
    values = ArchitectureRead.model_validate(revision.snapshot["architecture"]).model_dump(exclude={"id", "status"})
    for key, value in values.items():
        setattr(design, key, value)
    await apply_graph_snapshot(db, design, revision.snapshot)
    await add_revision(db, design, account.username, payload.description.strip(), await capture_snapshot(db, design))
    audit(db, "restore_design_revision", account, client_id, target=str(design.id))
    await db.commit()
    return design
