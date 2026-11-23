import asyncio
import json
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

import httpx
from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import AwareDatetime, BaseModel, Field, SecretStr
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.access.azure import cipher
from app.domains.access.routes import audit, client_access, client_admin, current_account, get_db
from .models import GitHubConnection, RepositoryFinding

router = APIRouter()
API_ROOT = "https://api.github.com"
RUN_LIMIT = 20
RESPONSE_LIMIT = 1024 * 1024
OWNER_PATTERN = r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?$"
REPOSITORY_PATTERN = r"^[a-zA-Z0-9_.-]+$"


class WorkflowRun(BaseModel):
    id: int = Field(gt=0)
    name: str | None = None
    head_branch: str | None = None
    head_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    event: str = Field(max_length=80)
    status: str = Field(max_length=80)
    conclusion: str | None = Field(default=None, max_length=80)
    created_at: AwareDatetime
    finding_counts: dict[str, int] = Field(default_factory=dict)


class PipelineRead(BaseModel):
    repository: str
    runs: list[WorkflowRun]
    total_count: int
    collected_at: AwareDatetime


class ConnectionRead(BaseModel):
    owner: str
    repository: str


class ConnectionWrite(ConnectionRead):
    owner: str = Field(pattern=OWNER_PATTERN)
    repository: str = Field(min_length=1, max_length=100, pattern=REPOSITORY_PATTERN)
    token: SecretStr = Field(min_length=20, max_length=512)


def connection_data(row):
    return ConnectionRead(owner=row.owner, repository=row.repository) if row else None


@router.get("/github/connection", response_model=ConnectionRead | None)
async def get_connection(client_id: UUID = Depends(client_access), db: AsyncSession = Depends(get_db)):
    return connection_data(await db.get(GitHubConnection, client_id))


@router.put("/github/connection", response_model=ConnectionRead)
async def save_connection(payload: ConnectionWrite, request: Request,
                          client_id: UUID = Depends(client_admin), db: AsyncSession = Depends(get_db)):
    token = payload.token.get_secret_value()
    if payload.repository in {".", ".."} or not token.isascii() or not all(
        char.isalnum() or char in "_-" for char in token
    ):
        raise HTTPException(422, "Provide a valid repository and access token.")
    owner, repository = payload.owner.lower(), payload.repository.lower()
    binding = f"{client_id}/{owner}/{repository}/"
    encrypted = cipher().encrypt(f"{binding}{token}".encode()).decode()
    values = {"owner": owner, "repository": repository, "ciphertext": encrypted}
    await db.execute(insert(GitHubConnection).values(client_id=client_id, **values).on_conflict_do_update(
        index_elements=[GitHubConnection.client_id], set_=values,
    ))
    audit(db, "save_github_connection", request.state.account, client_id, f"{owner}/{repository}")
    await db.commit()
    return ConnectionRead(owner=owner, repository=repository)


@router.delete("/github/connection", status_code=204)
async def clear_connection(request: Request, client_id: UUID = Depends(client_admin),
                           db: AsyncSession = Depends(get_db)):
    await db.execute(delete(GitHubConnection).where(GitHubConnection.client_id == client_id))
    audit(db, "clear_github_connection", request.state.account, client_id)
    await db.commit()


def connection_token(connection):
    binding = f"{connection.client_id}/{connection.owner}/{connection.repository}/"
    try:
        plaintext = cipher().decrypt(connection.ciphertext.encode()).decode()
    except (InvalidToken, UnicodeError):
        raise HTTPException(503, "GitHub credentials are unavailable.") from None
    if not plaintext.startswith(binding):
        raise HTTPException(503, "GitHub credentials are unavailable.")
    return plaintext[len(binding):]


async def read_github_json(owner, repository, path, token=None):
    url = f"{API_ROOT}/repos/{owner}/{repository}/{path}"
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with asyncio.timeout(12), httpx.AsyncClient(timeout=8, follow_redirects=False, trust_env=False) as client:
        async with client.stream("GET", url, params={"per_page": RUN_LIMIT}, headers=headers) as response:
            if response.status_code == 429 or (response.status_code == 403 and (
                response.headers.get("x-ratelimit-remaining") == "0" or response.headers.get("retry-after")
            )):
                raise HTTPException(429, "GitHub's API rate limit was reached. Try again later.")
            if response.status_code == 404:
                raise HTTPException(404, "Repository or workflow runs were not accessible.")
            if response.status_code in {401, 403}:
                raise HTTPException(403, "GitHub denied access to these workflow runs.")
            if response.status_code != 200:
                raise HTTPException(502, "GitHub did not return workflow evidence.")
            body = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=65536):
                if len(body) + len(chunk) > RESPONSE_LIMIT:
                    raise HTTPException(502, "GitHub workflow evidence exceeded the response limit.")
                body.extend(chunk)
    return json.loads(body)


async def read_public_runs(owner, repository, token=None):
    return await read_github_json(owner, repository, "actions/runs", token)


async def confirm_connection(db, request, client_id, ciphertext):
    await client_access(request, db, await current_account(request, db))
    if ciphertext:
        current = await db.scalar(select(GitHubConnection.ciphertext).where(GitHubConnection.client_id == client_id))
        if current != ciphertext:
            raise HTTPException(409, "The GitHub connection changed. Reload the saved evidence.")


@router.get("/github/dependencies")
async def dependency_alerts(request: Request, client_id: UUID = Depends(client_access),
                            db: AsyncSession = Depends(get_db)):
    connection = await db.get(GitHubConnection, client_id)
    if not connection:
        raise HTTPException(404, "Configure a GitHub repository to review dependency alerts.")
    owner, repository, ciphertext = connection.owner, connection.repository, connection.ciphertext
    token = connection_token(connection)
    await db.rollback()
    try:
        payload = await read_github_json(owner, repository, "dependabot/alerts", token)
        if not isinstance(payload, list):
            raise ValueError("Unexpected alert list")
        alerts = []
        for entry in payload[:RUN_LIMIT]:
            dependency = entry.get("dependency") or {}
            package = dependency.get("package") or {}
            advisory = entry.get("security_advisory") or {}
            vulnerability = entry.get("security_vulnerability") or {}
            patched = vulnerability.get("first_patched_version") or {}
            if type(entry["number"]) is not int or entry["number"] <= 0:
                continue
            fields = {"package": package.get("name"), "ecosystem": package.get("ecosystem"),
                      "manifest": dependency.get("manifest_path"), "state": entry.get("state"),
                      "severity": vulnerability.get("severity"), "advisory": advisory.get("ghsa_id"),
                      "patched_version": patched.get("identifier")}
            alerts.append({"number": entry["number"], **{
                field: value[:240] for field, value in fields.items() if isinstance(value, str)
            }})
    except (TimeoutError, httpx.TimeoutException):
        raise HTTPException(504, "GitHub did not respond in time.") from None
    except (AttributeError, KeyError, TypeError, httpx.HTTPError, ValueError):
        raise HTTPException(502, "GitHub dependency evidence could not be read.") from None
    await confirm_connection(db, request, client_id, ciphertext)
    return {"repository": f"{owner}/{repository}", "alerts": alerts, "collected_at": datetime.now(timezone.utc)}


@router.get("/github/runs", response_model=PipelineRead)
async def github_runs(
    owner: Annotated[str, Query(pattern=OWNER_PATTERN)],
    repository: Annotated[str, Query(min_length=1, max_length=100, pattern=REPOSITORY_PATTERN)],
    request: Request,
    client_id: UUID = Depends(client_access),
    db: AsyncSession = Depends(get_db),
):
    if repository in {".", ".."}:
        raise HTTPException(422, "Provide a repository name.")
    connection = await db.get(GitHubConnection, client_id)
    ciphertext = None
    token = None
    if connection and (connection.owner, connection.repository) == (owner.lower(), repository.lower()):
        ciphertext = connection.ciphertext
        token = connection_token(connection)
    await db.rollback()
    try:
        payload = await read_public_runs(owner, repository, token) if token else await read_public_runs(owner, repository)
        if not isinstance(payload, dict) or not isinstance(payload.get("workflow_runs"), list):
            raise ValueError("Unexpected workflow data")
        total = payload.get("total_count")
        if type(total) is not int or total < 0:
            raise ValueError("Unexpected workflow count")
        runs = [WorkflowRun.model_validate(run) for run in payload["workflow_runs"][:RUN_LIMIT]]
    except (TimeoutError, httpx.TimeoutException):
        raise HTTPException(504, "GitHub did not respond in time.") from None
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "GitHub workflow evidence could not be read.") from None
    await confirm_connection(db, request, client_id, ciphertext)
    counts = {}
    if runs:
        result = await db.execute(select(RepositoryFinding.commit_sha, RepositoryFinding.severity, func.count()).where(
            RepositoryFinding.client_id == client_id,
            RepositoryFinding.owner == owner.lower(),
            RepositoryFinding.repository == repository.lower(),
            RepositoryFinding.commit_sha.in_({run.head_sha for run in runs}),
        ).group_by(RepositoryFinding.commit_sha, RepositoryFinding.severity))
        for commit, severity, count in result:
            counts.setdefault(commit, {})[severity] = count
    for run in runs:
        run.finding_counts = counts.get(run.head_sha, {})
        if run.name:
            run.name = run.name[:180]
        if run.head_branch:
            run.head_branch = run.head_branch[:250]
    return PipelineRead(repository=f"{owner}/{repository}", runs=runs, total_count=total,
                        collected_at=datetime.now(timezone.utc))
