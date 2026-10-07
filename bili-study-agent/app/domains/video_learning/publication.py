"""Publish immutable video knowledge; MySQL stores only verified object references."""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

from pymysql.err import ProgrammingError, OperationalError
from asyncmy.errors import ProgrammingError as AsyncMyProgrammingError, OperationalError as AsyncMyOperationalError

from app.common.exceptions import AppException
from app.config import settings
from app.database import fetch_one, execute_write, transaction
from app.domains.learning.study_context import _load_authorized_context
from app.domains.video_learning.artifacts import EduVideoSource, VideoArtifact, load_video_artifact
from app.domains.video_learning.schema import PUBLICATION_DDL
from app.services.source_asset_store import SourceAssetError, SourceAssetStore


async def get_video_publication(video_id: int) -> dict[str, Any] | None:
    """Read the latest RAG-ready reviewed pointer without reading derived objects."""
    if type(video_id) is not int or video_id <= 0:
        raise ValueError("video_id must be a positive integer")
    try:
        row = await fetch_one(
            "SELECT * FROM video_learning_publication WHERE video_id=%s AND rag_status='ready' ORDER BY id DESC LIMIT 1",
            (video_id,),
        )
    except (AsyncMyProgrammingError, ProgrammingError, AsyncMyOperationalError, OperationalError) as exc:
        # Older deployments may not have applied this additive migration yet.
        # Other database failures must remain visible, never become legacy answers.
        if exc.args and exc.args[0] == 1146:
            return None
        if exc.args and exc.args[0] == 1054:
            # No readiness authority exists on that legacy schema. Keep ordinary
            # course retrieval and playback, but never infer READY from a row.
            return None
        raise
    if row is not None and row.get("video_id") != video_id:
        raise ValueError("Publication is bound to a different video")
    return row


async def ensure_publication_schema() -> None:
    """Add readiness/lineage columns, leaving existing approved rows ready."""
    await execute_write(PUBLICATION_DDL)
    columns = {
        "rag_status": "VARCHAR(16) NOT NULL DEFAULT 'ready'",
        "previous_publication_id": "BIGINT UNSIGNED NULL",
        "activated_at": "DATETIME(6) NULL",
    }
    for column, definition in columns.items():
        exists = await fetch_one("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='video_learning_publication' AND COLUMN_NAME=%s", (column,))
        if not exists:
            try:
                await execute_write(f"ALTER TABLE video_learning_publication ADD COLUMN {column} {definition}")
            except (AsyncMyProgrammingError, ProgrammingError, AsyncMyOperationalError, OperationalError) as exc:
                if not exc.args or exc.args[0] != 1060:
                    raise


def validate_artifact_video_binding(artifact: VideoArtifact, video_id: int, row: dict) -> None:
    """Verify object identities before publication or registration in RAG."""
    if isinstance(artifact.source, EduVideoSource):
        if (artifact.source.video_id != video_id or row.get("asset_id") != artifact.source.asset_id
                or row.get("session_id") != artifact.source.session_id):
            raise ValueError("Artifact source identity differs from the bound EDU video")
    elif row["video_code"] != f"{artifact.source.bvid}_P{artifact.source.page}_{artifact.source.cid}":
        raise ValueError("Artifact source identity differs from the bound video")
    if abs(float(row["duration_seconds"]) - artifact.source.duration) > 3:
        raise ValueError("Artifact duration differs from the bound video")


async def publish_video_artifact(video_id: int, path: Path, *, rag_pending: bool = False) -> dict[str, Any]:
    """Verify reviewed output and actual video, upload, then append a pointer.

    Playback has no dependency on this table or its object. Repeating publication
    of the same immutable artifact leaves the existing pointer unchanged. Formal
    production uses rag_pending=True; students retain the previous ready version
    until activate_video_publication verifies the exact completed RAG receipt.
    """
    artifact = load_video_artifact(path)
    if artifact.quality not in ("native_compiled", "asr_compiled"):
        raise ValueError("Only fresh verified transcript compilations may be published")
    video = await fetch_one(
        "SELECT sv.*,sa.session_id FROM session_video sv JOIN session_asset sa ON sa.id=sv.asset_id WHERE sv.id=%s",
        (int(video_id),),
    )
    if not video or video["transcode_status"] != "completed" or int(video["duration_seconds"]) <= 0:
        raise ValueError("Publication requires a verified playable video")
    validate_artifact_video_binding(artifact, int(video_id), video)
    if isinstance(artifact.source, EduVideoSource):
        from app.domains.video_learning.bound_media import verify_bound_source
        await verify_bound_source(artifact.source)
    # Hash and upload a stable snapshot of the validated model. Formatting a
    # JSON file differently must never overwrite the object of an existing
    # publication or change its byte checksum.
    raw = (json.dumps(artifact.model_dump(mode="json"), ensure_ascii=False,
                      sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    if len(raw) > 5_000_000:
        raise ValueError("Artifact exceeds the student publication size limit")
    digest = hashlib.sha256(raw).hexdigest()
    bucket = settings.MINIO_BUCKET_ARTIFACTS
    key = f"video/{artifact.content_sha256}/{artifact.artifact_sha256}.json"
    expected = {
        "video_id": int(video_id), "artifact_id": artifact.content_sha256,
        "artifact_sha256": artifact.artifact_sha256, "object_sha256": digest,
        "bucket": bucket, "object_key": key, "size_bytes": len(raw),
    }
    existing = await fetch_one(
        "SELECT * FROM video_learning_publication WHERE video_id=%s AND artifact_sha256=%s",
        (int(video_id), artifact.artifact_sha256),
    )
    if existing:
        _verify_reference(existing, expected)
        await asyncio.to_thread(_read_publication, existing)
        return existing

    store = SourceAssetStore()
    try:
        # A previous upload may have succeeded before the DB transaction. Reuse
        # only a verified object; an existing conflicting object is never replaced.
        await asyncio.to_thread(_read_verified_artifact, store, expected)
    except SourceAssetError as exc:
        if exc.outcome != "object not found":
            raise
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", suffix=".json", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(raw)
            await asyncio.to_thread(store.put_artifact, bucket, key, temporary, "application/json")
            # Read after write, hash-check the object students will actually read.
            await asyncio.to_thread(_read_verified_artifact, store, expected)
        finally:
            if temporary is not None:
                store.cleanup_temp(temporary)
    previous = await get_video_publication(int(video_id))
    async with transaction() as (_, cur):
        await cur.execute(
            "INSERT IGNORE INTO video_learning_publication "
            "(video_id,artifact_id,artifact_sha256,object_sha256,bucket,object_key,size_bytes,rag_status,previous_publication_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (int(video_id), artifact.content_sha256, artifact.artifact_sha256, digest, bucket, key, len(raw),
             "pending" if rag_pending else "ready", previous["id"] if previous else None),
        )
    result = await fetch_one(
        "SELECT * FROM video_learning_publication WHERE video_id=%s AND artifact_sha256=%s",
        (int(video_id), artifact.artifact_sha256),
    )
    _verify_reference(result, expected)
    return result


async def activate_video_publication(video_id: int, artifact_sha256: str, receipt: dict) -> dict:
    """Expose a reviewed version only after its exact existing-RAG ingest succeeds.

    This internal worker seam never deletes or retires another generation. A
    failure keeps both pending immutable output and the previous ready pointer.
    """
    row = await fetch_one("SELECT * FROM video_learning_publication WHERE video_id=%s AND artifact_sha256=%s", (video_id, artifact_sha256))
    if (not row or receipt.get("status") != "PASS" or receipt.get("task_status") != "succeeded"
            or receipt.get("generation") != row["artifact_id"]
            or receipt.get("binding", {}).get("video_id") != video_id
            or receipt.get("artifact_source", {}).get("sha256") != row["object_sha256"]
            or type(receipt.get("active_vector_count")) is not int or receipt["active_vector_count"] <= 0
            or receipt.get("pending_messages") != 0):
        raise ValueError("Publication activation requires its verified successful RAG receipt")
    await asyncio.to_thread(_read_publication, row)
    async with transaction() as (_, cur):
        await cur.execute("UPDATE video_learning_publication SET rag_status='ready',activated_at=CURRENT_TIMESTAMP WHERE video_id=%s AND artifact_sha256=%s AND rag_status='pending'", (video_id, artifact_sha256))
    result = await fetch_one("SELECT * FROM video_learning_publication WHERE video_id=%s AND artifact_sha256=%s", (video_id, artifact_sha256))
    if not result or result.get("rag_status") != "ready":
        raise ValueError("Publication activation was fenced out")
    return result


def _verify_reference(row: dict[str, Any] | None, expected: dict[str, Any]) -> None:
    if not row or any(row.get(field) != value for field, value in expected.items()):
        raise ValueError("Immutable publication reference conflicts with stored output")


def _read_verified_artifact(store: SourceAssetStore, row: dict[str, Any]) -> VideoArtifact:
    path = store.fetch_to_temp(
        row["bucket"], row["object_key"], expected_sha256=row["object_sha256"], max_bytes=5_000_000,
    )
    try:
        artifact = load_video_artifact(Path(path))
        if (artifact.quality not in ("native_compiled", "asr_compiled") or artifact.content_sha256 != row["artifact_id"]
                or artifact.artifact_sha256 != row["artifact_sha256"] or Path(path).stat().st_size != row["size_bytes"]):
            raise ValueError("Publication identity or generation mismatch")
        return artifact
    finally:
        store.cleanup_temp(path)


def _read_publication(row: dict[str, Any]) -> dict[str, Any]:
    artifact = _read_verified_artifact(SourceAssetStore(), row)
    # Student DTO contains learning content and its lineage ID; secrets and
    # provider request/response traces stay in the canonical operator artifact.
    return {
        "artifact_id": artifact.content_sha256,
        "generation": artifact.content_sha256,
        "source": artifact.source.model_dump(mode="json"),
        "transcript_origin": artifact.compiler.transcript_origin,
        "transcript": artifact.transcript.model_dump(mode="json"),
        "chapters": [c.model_dump(mode="json") for c in artifact.chapters],
        "summary": artifact.summary.model_dump(mode="json"),
        "knowledge_note": artifact.knowledge_note,
        "mindmap": artifact.mindmap.model_dump(mode="json"),
    }


async def get_video_knowledge(session_id: int, user_id: int) -> dict[str, Any]:
    context = await _load_authorized_context(session_id, user_id)
    video = context.get("video")
    if not video:
        raise AppException("40440", "本课次暂无可播放视频", http_status=404)
    row = await get_video_publication(int(video["video_id"]))
    if not row:
        raise AppException("40440", "本视频的 AI 学习资料尚未发布", http_status=404)
    try:
        data = await asyncio.to_thread(_read_publication, row)
    except Exception as exc:
        raise AppException("50300", "AI 学习资料暂不可用，可继续观看视频", http_status=503) from exc
    from app.domains.video_learning.exercises import ready_exercises
    exercise = await ready_exercises(int(video["video_id"]), row)
    return {"series_id": context["series_id"], "session_id": int(session_id), "video_id": video["video_id"],
            "exercise_count": exercise["question_count"] if exercise else 0,
            "exercise_bank_id": exercise["bank_id"] if exercise else None, **data}
