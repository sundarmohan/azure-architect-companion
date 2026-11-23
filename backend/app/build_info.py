"""Allowlisted application build provenance for operational verification."""

import os
import re
from datetime import datetime

PRODUCT_VERSION = "2.2"
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{7,64}$", re.IGNORECASE)


def build_metadata() -> dict[str, str | None]:
    """Return release identity without exposing arbitrary environment data."""
    commit = os.getenv("MONITORAI_BUILD_SHA", "").strip()
    built_at = os.getenv("MONITORAI_BUILD_TIME", "").strip()
    if not COMMIT_PATTERN.fullmatch(commit):
        commit = None
    try:
        parsed = datetime.fromisoformat(built_at.replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            raise ValueError
        built_at = parsed.isoformat().replace("+00:00", "Z")
    except ValueError:
        built_at = None
    return {"commit": commit, "built_at": built_at}
