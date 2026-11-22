import asyncio
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from .models import Account, AuditEvent, Client, LoginSession, Membership

router = APIRouter()
audit_router = APIRouter()
hasher = PasswordHasher()
dummy_hash = hasher.hash(secrets.token_urlsafe(32))
COOKIE = "monitorai_session"
SESSION_AGE = timedelta(hours=8)
password_slots = asyncio.Semaphore(2)


async def run_password_work(operation, *args):
    if password_slots.locked():
        raise HTTPException(429, "Password service busy")
    async with password_slots:
        return await asyncio.to_thread(operation, *args)


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=1, max_length=256)


class NewAccount(Login):
    password: str = Field(min_length=12, max_length=256)


class ResetPassword(BaseModel):
    new_password: str = Field(min_length=12, max_length=256)


class ChangePassword(ResetPassword):
    current_password: str = Field(min_length=1, max_length=256)


class NewClient(BaseModel):
    name: str = Field(min_length=1, max_length=160, pattern=r"\S")


class MemberWrite(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    role: Literal["admin", "editor", "viewer"]


class AuditEventRead(BaseModel):
    id: UUID
    occurred_at: datetime
    actor: str | None
    action: str
    target: str | None
    outcome: str


async def get_db():
    async with SessionLocal() as db:
        yield db


def require_request_header(request: Request):
    if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("X-MonitorAI-Request") != "1":
        raise HTTPException(403, "Request header required")


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def password_matches(password_hash: str, password: str) -> bool:
    try:
        return await run_password_work(hasher.verify, password_hash, password)
    except VerifyMismatchError:
        return False


def audit(db: AsyncSession, action: str, account=None, client_id=None, target=None, outcome="success"):
    db.add(AuditEvent(account_id=account.id if account else None,
                      client_id=client_id, action=action, target=target, outcome=outcome))


async def bootstrap_admin():
    username = os.getenv("MONITORAI_BOOTSTRAP_USERNAME")
    password = os.getenv("MONITORAI_BOOTSTRAP_PASSWORD")
    if not username and not password:
        return
    async with SessionLocal() as db:
        await db.execute(text("SELECT pg_advisory_xact_lock(23829018)"))
        if await db.scalar(select(Account.id).where(Account.is_platform_admin).limit(1)):
            return
        try:
            account = NewAccount(username=username, password=password)
        except ValidationError:
            raise RuntimeError("Invalid administrator bootstrap settings") from None
        if await db.scalar(select(Account.id).where(Account.username == account.username.lower())):
            raise RuntimeError("Bootstrap administrator username is already in use")
        await db.execute(insert(Account).values(
            username=account.username.lower(),
            password_hash=await run_password_work(hasher.hash, account.password),
            is_platform_admin=True,
        ).on_conflict_do_nothing(index_elements=[Account.username]))
        await db.commit()


async def current_account(request: Request, db: AsyncSession = Depends(get_db)) -> Account:
    token = request.cookies.get(COOKIE, "")
    if token:
        account = await db.scalar(
            select(Account).join(LoginSession, Account.id == LoginSession.account_id)
            .where(LoginSession.token_hash == digest(token), LoginSession.expires_at > datetime.now(timezone.utc))
        )
        if account:
            return account
    raise HTTPException(401, "Sign in required")


async def platform_admin(account: Account = Depends(current_account)) -> Account:
    if not account.is_platform_admin:
        raise HTTPException(403, "Platform administrator required")
    return account


async def client_access(request: Request, db: AsyncSession = Depends(get_db),
                        account: Account = Depends(current_account)) -> UUID:
    try:
        client_id = UUID(request.headers.get("X-Client-ID", ""))
    except ValueError:
        raise HTTPException(403, "Select an authorized client") from None
    if account.is_platform_admin and await db.get(Client, client_id):
        role = "admin"
    else:
        membership = await db.get(Membership, (account.id, client_id))
        role = membership.role if membership else None
    if role is None or (role == "viewer" and request.method not in {"GET", "HEAD"}):
        audit(db, "client_access", account, client_id, outcome="denied")
        await db.commit()
        raise HTTPException(403, "Client access denied")
    request.state.client_role = role
    request.state.account = account
    db.info["client_id"] = client_id
    return client_id


async def client_admin(request: Request, client_id: UUID = Depends(client_access)) -> UUID:
    if request.state.client_role != "admin":
        raise HTTPException(403, "Client administrator required")
    return client_id


async def recent_audit_events(db: AsyncSession, client_id: UUID | None, platform: bool):
    query = (
        select(AuditEvent.id, AuditEvent.occurred_at, Account.username.label("actor"),
               AuditEvent.action, AuditEvent.target, AuditEvent.outcome)
        .outerjoin(Account, Account.id == AuditEvent.account_id)
        .where(AuditEvent.client_id == client_id)
        .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .limit(50)
    )
    if not platform:
        # Denied boundary checks can contain identities or targets from other tenants.
        query = query.where(AuditEvent.action.not_in(("client_access", "architecture_access")))
    return (await db.execute(query)).mappings().all()


@router.get("/audit", response_model=list[AuditEventRead])
async def platform_audit(_actor: Account = Depends(platform_admin), db: AsyncSession = Depends(get_db)):
    return await recent_audit_events(db, None, platform=True)


@audit_router.get("/audit", response_model=list[AuditEventRead])
async def client_audit(client_id: UUID = Depends(client_admin), db: AsyncSession = Depends(get_db),
                       actor: Account = Depends(current_account)):
    return await recent_audit_events(db, client_id, platform=actor.is_platform_admin)


@router.post("/login")
async def login(payload: Login, response: Response, request: Request, db: AsyncSession = Depends(get_db)):
    account = await db.scalar(select(Account).where(Account.username == payload.username.lower()).with_for_update())
    now = datetime.now(timezone.utc)
    if account and account.locked_until and account.locked_until > now:
        raise HTTPException(401, "Invalid username or password")
    valid = await password_matches(account.password_hash if account else dummy_hash, payload.password)
    if not account or not valid:
        if account:
            account.failed_logins += 1
            if account.failed_logins >= 5:
                account.failed_logins = 0
                account.locked_until = now + timedelta(minutes=15)
        audit(db, "login", account, outcome="denied")
        await db.commit()
        raise HTTPException(401, "Invalid username or password")
    account.failed_logins = 0
    account.locked_until = None
    await db.execute(delete(LoginSession).where(LoginSession.expires_at <= now))
    if old_token := request.cookies.get(COOKIE):
        await db.execute(delete(LoginSession).where(LoginSession.token_hash == digest(old_token)))
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=digest(token), account_id=account.id, expires_at=now + SESSION_AGE))
    audit(db, "login", account)
    await db.commit()
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict",
                        secure=os.getenv("MONITORAI_INSECURE_LOCAL_COOKIE") != "1",
                        max_age=int(SESSION_AGE.total_seconds()))
    return await me(account, db)


@router.get("/me")
async def me(account: Account = Depends(current_account), db: AsyncSession = Depends(get_db)):
    query = select(Client.id, Client.name).order_by(Client.name)
    if account.is_platform_admin:
        rows = [(client_id, name, "admin") for client_id, name in (await db.execute(query)).all()]
    else:
        rows = (await db.execute(query.add_columns(Membership.role)
                .join(Membership).where(Membership.account_id == account.id))).all()
    return {"username": account.username, "is_platform_admin": account.is_platform_admin,
            "memberships": [{"client_id": client_id, "client_name": name, "role": role}
                            for client_id, name, role in rows]}


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, account: Account = Depends(current_account),
                 db: AsyncSession = Depends(get_db)):
    await db.execute(delete(LoginSession).where(LoginSession.token_hash == digest(request.cookies[COOKIE])))
    audit(db, "logout", account)
    await db.commit()
    response.delete_cookie(COOKIE)


async def replace_password(db, account, password):
    account.password_hash = await run_password_work(hasher.hash, password)
    account.failed_logins = 0
    account.locked_until = None
    await db.execute(delete(LoginSession).where(LoginSession.account_id == account.id))


@router.post("/password", status_code=204)
async def change_password(payload: ChangePassword, response: Response,
                          account: Account = Depends(current_account), db: AsyncSession = Depends(get_db)):
    await db.refresh(account, with_for_update=True)
    if not await password_matches(account.password_hash, payload.current_password):
        raise HTTPException(403, "Current password is incorrect")
    await replace_password(db, account, payload.new_password)
    audit(db, "change_password", account)
    await db.commit()
    response.delete_cookie(COOKIE)


@router.post("/users", status_code=201)
async def create_user(payload: NewAccount, actor: Account = Depends(platform_admin), db: AsyncSession = Depends(get_db)):
    username = payload.username.lower()
    result = await db.execute(insert(Account).values(username=username,
        password_hash=await run_password_work(hasher.hash, payload.password))
        .on_conflict_do_nothing(index_elements=[Account.username]).returning(Account.id))
    if not result.scalar_one_or_none():
        raise HTTPException(409, "Username already exists")
    audit(db, "create_user", actor, target=username)
    await db.commit()
    return {"username": username}


@router.post("/users/{username}/password", status_code=204)
async def reset_password(username: str, payload: ResetPassword, actor: Account = Depends(platform_admin),
                         db: AsyncSession = Depends(get_db)):
    account = await db.scalar(select(Account).where(Account.username == username.lower()).with_for_update())
    if not account:
        raise HTTPException(404, "User not found")
    if account.is_platform_admin:
        raise HTTPException(403, "Platform administrators must change their own password")
    await replace_password(db, account, payload.new_password)
    audit(db, "reset_password", actor, target=account.username)
    await db.commit()


@router.post("/clients", status_code=201)
async def create_client(payload: NewClient, actor: Account = Depends(platform_admin), db: AsyncSession = Depends(get_db)):
    name = payload.name.strip()
    client_id = (await db.execute(insert(Client).values(name=name)
        .on_conflict_do_nothing(index_elements=[Client.name]).returning(Client.id))).scalar_one_or_none()
    if not client_id:
        raise HTTPException(409, "Client already exists")
    db.add(Membership(account_id=actor.id, client_id=client_id, role="admin"))
    audit(db, "create_client", actor, client_id, target=name)
    await db.commit()
    return {"client_id": client_id, "client_name": name}


@router.post("/clients/{client_id}/members", status_code=204)
async def set_member(client_id: UUID, payload: MemberWrite, actor: Account = Depends(platform_admin),
                     db: AsyncSession = Depends(get_db)):
    account = await db.scalar(select(Account).where(Account.username == payload.username.lower()))
    if not account or not await db.get(Client, client_id):
        raise HTTPException(404, "User or client not found")
    await db.execute(insert(Membership).values(account_id=account.id, client_id=client_id, role=payload.role)
        .on_conflict_do_update(index_elements=[Membership.account_id, Membership.client_id], set_={"role": payload.role}))
    audit(db, "set_membership", actor, client_id, target=account.username)
    await db.commit()
