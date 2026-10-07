"""Typed video provenance carried from an IR seed to Milvus and citations."""
from __future__ import annotations

from typing import Annotated
import hashlib
import hmac
import json
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator, model_serializer

PositiveId = Annotated[int, Field(gt=0, strict=True)]
Seconds = Annotated[float, Field(ge=0, allow_inf_nan=False, strict=True)]
NonBlank = Annotated[str, Field(min_length=1, strict=True)]


class VideoKnowledgeMetadata(BaseModel):
    """A complete binding is required whenever an IR seed claims video provenance."""

    model_config = ConfigDict(extra="ignore")
    series_id: PositiveId
    session_id: PositiveId
    video_id: PositiveId
    start_seconds: Seconds
    end_seconds: Seconds
    distill_artifact_id: NonBlank
    distill_artifact_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", strict=True)]
    source_bvid: Annotated[str, Field(pattern=r"^BV[0-9A-Za-z]{10}$", strict=True)] | None = None
    source_cid: PositiveId | None = None
    source_kind: Annotated[str, Field(pattern=r"^existing_video$", strict=True)] | None = None
    source_asset_id: PositiveId | None = None
    source_media_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", strict=True)] | None = None
    compiler_version: NonBlank
    generation: NonBlank

    @model_validator(mode="after")
    def valid_range_and_labels(self):
        if self.source_kind == "existing_video":
            if self.source_asset_id is None or self.source_media_sha256 is None or self.source_bvid is not None or self.source_cid is not None:
                raise ValueError("EDU video requires real asset/media identity without platform IDs")
        elif self.source_bvid is None or self.source_cid is None or self.source_asset_id is not None or self.source_media_sha256 is not None:
            raise ValueError("Platform video requires its BVID/CID")
        if self.end_seconds <= self.start_seconds:
            raise ValueError("video knowledge end_seconds must exceed start_seconds")
        for name in ("distill_artifact_id", "compiler_version", "generation"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be blank")
        return self

    @model_serializer(mode="wrap")
    def unchanged_legacy_shape(self, handler):
        # Old platform signatures hash exactly their original fields. Optional
        # EDU identities must not alter any existing metadata or proof bytes.
        return {key: value for key, value in handler(self).items() if value is not None}


VIDEO_METADATA_FIELDS = tuple(VideoKnowledgeMetadata.model_fields)
VIDEO_PROVENANCE_FIELDS = ("video_publication_id", "video_provenance_version", "video_provenance_signature")
VIDEO_PROVENANCE_CONTEXT_FIELDS = ("document_id", "parse_fingerprint", "parser_backend", "security_scope", "module_code")
_PROOF_PURPOSE = "edu.published-native-course-video.internal-classification.v1"


def video_metadata_for_chunk(extra: dict) -> dict:
    """Validate video metadata without changing historical non-video row shapes."""
    metadata = extra.get("seed_metadata")
    if not isinstance(metadata, dict) or not any(
        key in metadata for key in ("video_id", "distill_artifact_id", "source_bvid")
    ):
        return {}
    return VideoKnowledgeMetadata.model_validate(metadata).model_dump()


def _proof_payload(row: dict) -> bytes:
    from app.config import settings

    if (row.get("internal") is not False or row.get("tenant_id") != settings.COURSE_PUBLIC_PARTITION
            or row.get("visibility") != "public" or row.get("parser_backend") != "edu-video-compiler"
            or row.get("content_type") != "doc_chunk"
            or type(row.get("video_provenance_version")) is not int or row["video_provenance_version"] != 1
            or type(row.get("video_publication_id")) is not int or row["video_publication_id"] <= 0
            or not re.fullmatch(r"[0-9a-f]{32}", str(row.get("document_id") or ""))
            or not re.fullmatch(r"[0-9a-f]{16}", str(row.get("parse_fingerprint") or ""))):
        raise ValueError("not a complete published public video provenance")
    metadata = VideoKnowledgeMetadata.model_validate(row).model_dump()
    owner = row.get("owner_id")
    if type(owner) is not int or owner <= 0:
        raise ValueError("published video requires its accountable operator")
    for field in ("security_scope", "source_file", "content", "raw_content", "series_code", "module_code"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise ValueError(f"published video provenance lacks {field}")
    if metadata["generation"] != metadata["distill_artifact_id"]:
        raise ValueError("published video generation differs from immutable artifact ID")
    # Canonical IDs and candidate/active state are derived by the existing loader.
    # Bind their stable document/fingerprint and exact text instead, so promotion
    # preserves a producer signature without exposing a signing path in loader.
    payload = {"purpose": _PROOF_PURPOSE, **metadata,
        **{key: row[key] for key in ("tenant_id", "visibility", "owner_id", "security_scope", "source_file",
                                   "document_id", "parse_fingerprint", "parser_backend", "video_publication_id",
                                   "video_provenance_version", "content_type", "series_code", "module_code")},
        **{key: row.get(key, "") for key in ("series_codes", "module_codes", "series_name", "context_prefix")},
        "content_sha256": hashlib.sha256(row["content"].encode()).hexdigest(),
        "raw_content_sha256": hashlib.sha256(row["raw_content"].encode()).hexdigest()}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _proof_key() -> bytes:
    from app.config import settings
    return hmac.new(settings.JWT_SECRET.encode(), _PROOF_PURPOSE.encode(), hashlib.sha256).digest()


def _sign_published_video_row(row: dict) -> str:
    """Producer-only signing primitive. Upload and loader paths only verify."""
    return hmac.new(_proof_key(), _proof_payload(row), hashlib.sha256).hexdigest()


def is_trusted_public_video(row: dict) -> bool:
    """Authenticate exact teaching text and ACL; invalid proofs use legacy policy."""
    signature = row.get("video_provenance_signature")
    if not isinstance(signature, str) or not re.fullmatch(r"[0-9a-f]{64}", signature):
        return False
    try:
        expected = hmac.new(_proof_key(), _proof_payload(row), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
    except (ValueError, TypeError, KeyError):
        return False
