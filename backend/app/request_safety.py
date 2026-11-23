"""Safe request correlation and unexpected-error boundary."""

import logging
import traceback
from pathlib import Path
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

CORRELATION_HEADER = "X-Correlation-ID"
logger = logging.getLogger("monitorai.request_errors")


def safe_origin(error: Exception) -> str:
    """Return a useful traceback location without logging exception text or locals."""
    frames = traceback.extract_tb(error.__traceback__, limit=20)
    if not frames:
        return "unknown"
    frame = frames[-1]
    return f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"


async def safe_request_boundary(request: Request, call_next):
    """Attach a server-generated reference and bound unexpected responses."""
    correlation_id = str(uuid4())
    request.state.correlation_id = correlation_id
    try:
        response = await call_next(request)
    except Exception as error:  # All modeled failures should be handled closer to their domain.
        logger.error(
            "unhandled_request correlation_id=%s method=%s path=%s error_type=%s origin=%s",
            correlation_id,
            request.method,
            request.url.path,
            type(error).__name__,
            safe_origin(error),
        )
        response = JSONResponse(status_code=500, content={
            "detail": {
                "message": "Unexpected server error. Use the reference when requesting support.",
                "correlation_id": correlation_id,
            },
        })
    response.headers[CORRELATION_HEADER] = correlation_id
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response
