"""Resolve authorized course video references independently of derived knowledge."""
from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlsplit

from app.config import settings
from app.database import get_minio_signing_client


def playback_url(reference: str | None) -> str | None:
    if not reference or not reference.startswith("minio://"):
        return reference
    parsed = urlsplit(reference)
    key = parsed.path.lstrip("/")
    if (parsed.netloc != settings.MINIO_BUCKET_COURSE or not key.startswith("video/")
            or any(part in {"", ".", ".."} for part in key.split("/"))
            or parsed.query or parsed.fragment):
        raise ValueError("Invalid course video storage reference")
    return get_minio_signing_client().presigned_get_object(parsed.netloc, key, expires=timedelta(hours=1))
