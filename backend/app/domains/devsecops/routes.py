import asyncio
import json
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime, BaseModel, Field

from app.domains.access.routes import client_access

router = APIRouter()
API_ROOT = "https://api.github.com"
RUN_LIMIT = 20
RESPONSE_LIMIT = 1024 * 1024


class WorkflowRun(BaseModel):
    id: int = Field(gt=0)
    name: str | None = None
    head_branch: str | None = None
    head_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    event: str = Field(max_length=80)
    status: str = Field(max_length=80)
    conclusion: str | None = Field(default=None, max_length=80)
    created_at: AwareDatetime


class PipelineRead(BaseModel):
    repository: str
    runs: list[WorkflowRun]
    total_count: int
    collected_at: AwareDatetime


async def read_public_runs(owner, repository):
    url = f"{API_ROOT}/repos/{owner}/{repository}/actions/runs"
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    async with asyncio.timeout(12), httpx.AsyncClient(timeout=8, follow_redirects=False, trust_env=False) as client:
        async with client.stream("GET", url, params={"per_page": RUN_LIMIT}, headers=headers) as response:
            if response.status_code == 429 or (response.status_code == 403 and (
                response.headers.get("x-ratelimit-remaining") == "0" or response.headers.get("retry-after")
            )):
                raise HTTPException(429, "GitHub's public API rate limit was reached. Try again later.")
            if response.status_code == 404:
                raise HTTPException(404, "Public repository or workflow runs were not found.")
            if response.status_code == 403:
                raise HTTPException(403, "GitHub denied access to these workflow runs.")
            if response.status_code != 200:
                raise HTTPException(502, "GitHub did not return workflow evidence.")
            body = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=65536):
                if len(body) + len(chunk) > RESPONSE_LIMIT:
                    raise HTTPException(502, "GitHub workflow evidence exceeded the response limit.")
                body.extend(chunk)
    return json.loads(body)


@router.get("/github/runs", response_model=PipelineRead)
async def github_runs(
    owner: Annotated[str, Query(pattern=r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?$")],
    repository: Annotated[str, Query(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")],
    _client_id: UUID = Depends(client_access),
):
    if repository in {".", ".."}:
        raise HTTPException(422, "Provide a repository name.")
    try:
        payload = await read_public_runs(owner, repository)
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
    for run in runs:
        if run.name:
            run.name = run.name[:180]
        if run.head_branch:
            run.head_branch = run.head_branch[:250]
    return PipelineRead(repository=f"{owner}/{repository}", runs=runs, total_count=total,
                        collected_at=datetime.now(timezone.utc))
