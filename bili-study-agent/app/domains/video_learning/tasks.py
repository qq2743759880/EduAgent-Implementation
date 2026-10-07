"""Project-owned video production lifecycle, with leased, fenced writes."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.exceptions import AppException
from app.database import fetch_one, fetch_all, execute_write, transaction
from app.domains.video_learning.task_schema import TASK_DDL

LEASE_SECONDS = 120


class CreateVideoTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: int = Field(gt=0)
    source_kind: Literal["bilibili", "existing_video"] = "bilibili"
    bvid: str | None = Field(default=None, pattern=r"^BV[0-9A-Za-z]{10}$")
    page: int | None = Field(default=None, ge=1, le=1000)
    video_id: int | None = Field(default=None, gt=0)
    regenerate: bool = Field(default=False, strict=True)
    transcript_mode: Literal["auto", "asr"] = "auto"
    exercises_only: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def exclusive_source(self):
        if self.exercises_only and self.source_kind != "existing_video":
            raise ValueError("Exercise completion requires an existing formal video")
        if self.source_kind == "bilibili":
            if self.bvid is None or self.page is None or self.video_id is not None:
                raise ValueError("Bilibili input requires BVID/page and cannot select a bound video")
        elif self.video_id is None or self.bvid is not None or self.page is not None:
            raise ValueError("Existing video input requires video_id without BVID/page")
        return self


class ReviewFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def strip_reason(cls, value):
        return value.strip() if isinstance(value, str) else value


class ApproveVideoTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_revision: int = Field(ge=0, le=20, strict=True)


class RejectVideoTask(ReviewFeedback):
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_revision: int = Field(ge=0, le=20, strict=True)


def retry_state(row: dict, now: datetime | None = None) -> str:
    now = now or datetime.now()
    db_expired = bool(row["lease_expired"]) if "lease_expired" in row else (
        row.get("lease_expires_at") is not None and row["lease_expires_at"] < now)
    expired = row.get("status") == "running" and db_expired
    if row.get("task_lock_owner") is not None or (row.get("status") != "failed" and not expired):
        raise AppException("40900", "仅失败或工作进程租约已过期的任务可以重试", http_status=409)
    return "approved" if row.get("reviewed_by") else "queued"


def task_dto(row: dict) -> dict:
    """Explicit allowlist: provider traces, local paths and lease tokens stay internal."""
    fields = ("id", "session_id", "bvid", "page", "transcript_mode", "created_by", "status",
              "stage", "attempt", "error_code", "error_message", "reviewed_by", "reviewed_at",
              "created_at", "updated_at")
    result = {key: row.get(key) for key in fields}
    try:
        retry_state(row)
        result["retry_allowed"] = True
    except AppException:
        result["retry_allowed"] = False
    result["review_allowed"] = row.get("status") == "awaiting_review"
    data = json.loads(row.get("data_json") or "{}")
    binding = data.get("binding") or {}
    result["video_id"] = binding.get("video_id")
    result["playback_available"] = bool(binding.get("video_id")) and (
        (data.get("bound_source") or {}).get("duration_seconds") != 0 or bool(data.get("metadata_verified")))
    result["transcript_origin"] = data.get("transcript_origin")
    result["review_revision"] = data.get("review_revision", 0)
    result["artifact_sha256"] = data.get("artifact_sha256")
    result["generation"] = data.get("artifact_generation")
    result["source_kind"] = data.get("source_kind", "bilibili")
    if result["source_kind"] == "existing_video":
        result["bvid"], result["page"] = None, None
    result["previous_task_id"] = data.get("previous_task_id")
    result["previous_publication_id"] = (data.get("previous_publication") or {}).get("id")
    result["published"] = bool(data.get("publication"))
    result["rag_ready"] = bool((data.get("ingestion") or data.get("reused_ready_publication")) and row.get("status") == "completed")
    result["exercises_only"] = data.get("exercises_only", False)
    result["exercise_count"] = (data.get("exercise_publication") or {}).get("question_count", 0)
    result["exercise_bank_id"] = (data.get("exercise_publication") or {}).get("bank_id")
    result['graph_projection']=data.get('graph_projection')
    result['production_trace_id']=(data.get('production_trace') or {}).get('trace_id')
    from app.config import settings
    result['jaeger_url']=settings.JAEGER_UI_URL
    result["lease_expired"] = bool(row.get("status") == "running" and row.get("lease_expired"))
    result["display_status"] = "stalled" if result["lease_expired"] else row.get("status")
    return result


async def ensure_schema() -> None:
    await execute_write(TASK_DDL)
    from app.domains.video_learning.publication import ensure_publication_schema
    await ensure_publication_schema()
    from app.domains.video_learning.schema import EXERCISE_DDL
    await execute_write(EXERCISE_DDL)


async def worker_status() -> dict:
    # Advisory locks are connection/server-local; inspect the primary, never a
    # read replica that cannot observe the consuming worker.
    async with transaction() as (_, cur):
        await cur.execute("SELECT IS_USED_LOCK('edu_video_knowledge_worker')")
        value = await cur.fetchone()
    running = bool(value and value[0] is not None)
    stopped = (Path(__file__).resolve().parents[3] / "data" / "video_knowledge_tasks" / "stop.request").exists()
    state = ("stopping" if running else "paused") if stopped else ("running" if running else "offline")
    return {"state": state, "running": running, "stop_requested": stopped}


def _dict(cur, row):
    return dict(zip((item[0] for item in cur.description), row)) if row else None


async def get_task(task_id: str) -> dict:
    row = await fetch_one("SELECT *,lease_expires_at<NOW(6) AS lease_expired,IS_USED_LOCK(CONCAT('edu_video_task_',id)) AS task_lock_owner FROM video_knowledge_task WHERE id=%s", (task_id,))
    if not row:
        raise AppException("40400", "视频知识任务不存在", http_status=404)
    return row


async def list_tasks(limit: int = 30, session_id: int | None = None) -> list[dict]:
    where, args = ("WHERE session_id=%s", (session_id, limit)) if session_id else ("", (limit,))
    return [task_dto(row) for row in await fetch_all(
        "SELECT *,lease_expires_at<NOW(6) AS lease_expired,IS_USED_LOCK(CONCAT('edu_video_task_',id)) AS task_lock_owner "
        f"FROM video_knowledge_task {where} ORDER BY created_at DESC LIMIT %s", args)]


async def bound_video(cur, session_id: int, video_id: int) -> dict:
    """Same canonical selection as playback; caller holds the lesson row lock."""
    from app.domains.learning.playable_video import PLAYABLE_VIDEO_ORDER, PLAYABLE_VIDEO_PREDICATE
    await cur.execute("SELECT sv.id AS video_id,sv.video_title,sv.duration_seconds,sv.video_code,"
                      "sa.id AS asset_id,sa.session_id,sa.file_url,sa.file_size FROM session_video sv "
                      "JOIN session_asset sa ON sa.id=sv.asset_id WHERE sa.session_id=%s "
                      f"AND sa.material_category='video' AND {PLAYABLE_VIDEO_PREDICATE} ORDER BY {PLAYABLE_VIDEO_ORDER} LIMIT 1",
                      (session_id,))
    video = _dict(cur, await cur.fetchone())
    if not video:
        # Legacy uploads marked completed but zero duration require a real probe
        # before becoming playable. Do not supersede another canonical video.
        await cur.execute("SELECT sv.id AS video_id,sv.video_title,sv.duration_seconds,sv.video_code,"
                          "sa.id AS asset_id,sa.session_id,sa.file_url,sa.file_size FROM session_video sv "
                          "JOIN session_asset sa ON sa.id=sv.asset_id WHERE sa.session_id=%s AND sv.id=%s "
                          "AND sa.material_category='video' AND sv.transcode_status='completed' AND sv.duration_seconds=0",
                          (session_id, video_id))
        video = _dict(cur, await cur.fetchone())
    if not video or int(video["video_id"]) != video_id:
        raise AppException("40900", "所选视频不是该课次当前可播放视频，请刷新视频管理", http_status=409)
    if not isinstance(video["file_url"], str) or not (video["file_url"].startswith("minio://") or video["file_url"].startswith("/media/videos/")):
        raise AppException("40900", "目前仅支持已上传到课程存储的原视频，请先完成现有视频上传", http_status=409)
    return video


async def resolve_bound_task(task: dict) -> dict:
    data = json.loads(task["data_json"])
    original = data["bound_source"]
    async with transaction() as (_, cur):
        await cur.execute("SELECT id FROM series_cohort_session WHERE id=%s FOR UPDATE", (task["session_id"],))
        current = await bound_video(cur, task["session_id"], data["binding"]["video_id"])
        if any(current[key] != original[key] for key in ("video_id", "asset_id", "session_id", "file_url")):
            raise AppException("40900", "原视频绑定已变化，不能将旧任务用于新视频", http_status=409)
        return current


async def repair_missing_duration(task: dict, token: str, prepared: dict) -> None:
    """Repair only legacy zero metadata after probing exact original media."""
    data = json.loads(task["data_json"])
    original = data["bound_source"]
    async with transaction() as (_, cur):
        await cur.execute("SELECT id FROM video_knowledge_task WHERE id=%s AND lease_token=%s "
                          "AND status='running' AND lease_expires_at>NOW(6) FOR UPDATE", (task["id"], token))
        if not await cur.fetchone():
            raise LeaseLost("Video task lost its lease before metadata repair")
        await cur.execute("SELECT id FROM series_cohort_session WHERE id=%s FOR UPDATE", (task["session_id"],))
        current = await bound_video(cur, task["session_id"], original["video_id"])
        if current["file_url"] != original["file_url"] or current["asset_id"] != original["asset_id"]:
            raise AppException("40900", "原视频绑定已变化，请重新查看课次", http_status=409)
        if current["duration_seconds"] == 0:
            await cur.execute("UPDATE session_video SET duration_seconds=%s WHERE id=%s AND duration_seconds=0",
                              (max(1, round(prepared["duration"])), current["video_id"]))
        elif abs(float(current["duration_seconds"]) - prepared["duration"]) > 3:
            raise AppException("40900", "视频时长记录与原媒体不符", http_status=409)


async def create_task(payload: CreateVideoTask, operator_id: int, *, trace_context: dict | None = None) -> dict:
    task_id = uuid.uuid4().hex
    async with transaction() as (_, cur):
        await cur.execute("SELECT id FROM series_cohort_session WHERE id=%s FOR UPDATE", (payload.session_id,))
        if not await cur.fetchone():
            raise AppException("40400", "课次不存在或已停用", http_status=404)
        data = {"source_kind": payload.source_kind, "auto_publish": True, "exercise_enabled": True,
                "exercises_only": payload.exercises_only}
        if trace_context:data['trace_context']=trace_context
        if payload.source_kind == "existing_video":
            video = await bound_video(cur, payload.session_id, payload.video_id)
            data["binding"] = {"video_id": video["video_id"], "asset_id": video["asset_id"]}
            data["bound_source"] = video
        if payload.exercises_only:
            await cur.execute("SELECT id,artifact_sha256,artifact_id FROM video_learning_publication WHERE video_id=%s AND rag_status='ready' ORDER BY id DESC LIMIT 1", (payload.video_id,))
            ready = _dict(cur, await cur.fetchone())
            if not ready:
                raise AppException("40900", "请先生成正式视频资料，再补生成本课习题", http_status=409)
            data["reused_ready_publication"] = ready
        await cur.execute("SELECT *,lease_expires_at<NOW(6) AS lease_expired,"
                          "IS_USED_LOCK(CONCAT('edu_video_task_',id)) AS task_lock_owner FROM video_knowledge_task "
                          "WHERE session_id=%s ORDER BY created_at DESC,id DESC LIMIT 1", (payload.session_id,))
        previous = _dict(cur, await cur.fetchone())
        if previous:
            previous_data = json.loads(previous["data_json"])
            compatible = (previous_data.get("source_kind", "bilibili") == payload.source_kind
                and bool(previous_data.get("exercises_only")) == payload.exercises_only
                and previous["transcript_mode"] == payload.transcript_mode
                and (int((previous_data.get("binding") or {}).get("video_id") or 0) == payload.video_id
                     if payload.source_kind == "existing_video" else previous["bvid"] == payload.bvid and previous["page"] == payload.page))
            if previous["status"] != "completed":
                if compatible:
                    return task_dto(previous)
                raise AppException("40900", "课次已有生产任务，请先查看、审核或重试，不能并行生产不同来源", http_status=409)
            if payload.exercises_only and compatible and previous_data.get("reused_ready_publication") == data["reused_ready_publication"]:
                return task_dto(previous)
            if not payload.regenerate and not payload.exercises_only:
                raise AppException("40900", "资料已经完成；请明确选择重新生成新版", http_status=409)
            data["previous_task_id"] = previous["id"]
        if payload.source_kind == "bilibili":
            await cur.execute("SELECT sv.id FROM session_video sv JOIN session_asset sa ON sa.id=sv.asset_id "
                              "WHERE sa.session_id=%s LIMIT 1", (payload.session_id,))
            if await cur.fetchone():
                raise AppException("40900", "课次已有原视频；请直接选择该视频生成资料，不能替换播放来源", http_status=409)
        if payload.source_kind == "existing_video":
            await cur.execute("SELECT id,artifact_sha256,artifact_id FROM video_learning_publication "
                              "WHERE video_id=%s ORDER BY id DESC LIMIT 1", (payload.video_id,))
            publication = _dict(cur, await cur.fetchone())
            if publication:
                if not payload.regenerate and not payload.exercises_only:
                    raise AppException("40900", "视频已有正式资料；请明确选择重新生成新版", http_status=409)
                data["previous_publication"] = publication
        await cur.execute("INSERT INTO video_knowledge_task "
                          "(id,session_id,bvid,page,transcript_mode,created_by,data_json,stage) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                          (task_id, payload.session_id, payload.bvid or "", payload.page or 0,
                           payload.transcript_mode, operator_id, json.dumps(data, ensure_ascii=False),
                           "exercises" if payload.exercises_only else "acquiring"))
    return task_dto(await get_task(task_id))


async def retry_task(task_id: str) -> dict:
    async with transaction() as (_, cur):
        await cur.execute("SELECT *,lease_expires_at<NOW(6) AS lease_expired,IS_USED_LOCK(CONCAT('edu_video_task_',id)) AS task_lock_owner FROM video_knowledge_task WHERE id=%s FOR UPDATE", (task_id,))
        row = _dict(cur, await cur.fetchone())
        if not row:
            raise AppException("40400", "视频知识任务不存在", http_status=404)
        status = retry_state(row)
        # A task-local advisory fence remains held until in-flight media/RAG
        # operations drain, even if the database lease has expired.
        await cur.execute("SELECT GET_LOCK(%s,0)", ("edu_video_task_" + task_id,))
        acquired = await cur.fetchone()
        if not acquired or acquired[0] != 1:
            raise AppException("40900", "原工作进程仍在处理或安全停止，请稍后刷新再重试", http_status=409)
        try:
            data = json.loads(row.get("data_json") or "{}")
            if not row.get("reviewed_by"):
                data["auto_publish"] = True
            await cur.execute("UPDATE video_knowledge_task SET data_json=%s,status=%s,lease_token=NULL,lease_expires_at=NULL,"
                              "error_code=NULL,error_message=NULL WHERE id=%s", (json.dumps(data, ensure_ascii=False), status, task_id))
        finally:
            await cur.execute("SELECT RELEASE_LOCK(%s)", ("edu_video_task_" + task_id,))
    return task_dto(await get_task(task_id))


async def approve_task(task_id: str, operator_id: int, *, expected_artifact_sha256: str,
                       expected_generation: str, expected_review_revision: int) -> dict:
    # Preview can be slow (verified object/file read). Hold the row lock only
    # while comparing the exact immutable identity it checked and committing
    # the approval, so reject/recompile cannot swap the reviewed generation.
    async with transaction() as (_, cur):
        await cur.execute("SELECT * FROM video_knowledge_task WHERE id=%s FOR UPDATE", (task_id,))
        row = _dict(cur, await cur.fetchone())
        if not row:
            raise AppException("40400", "视频知识任务不存在", http_status=404)
        if row["status"] != "awaiting_review" or row.get("reviewed_by") is not None:
            raise AppException("40900", "仅未审核发布的待审核任务可以发布，请先查看预览", http_status=409)
        data = json.loads(row["data_json"])
        current = (data.get("artifact_sha256"), data.get("artifact_generation"), data.get("review_revision", 0))
        if current != (expected_artifact_sha256, expected_generation, expected_review_revision):
            raise AppException("40900", "待审核资料已更新，请重新预览当前版本", http_status=409)
        await cur.execute("UPDATE video_knowledge_task SET status='approved',stage='publishing',"
                          "reviewed_by=%s,reviewed_at=NOW(6) WHERE id=%s", (operator_id, task_id))
    return task_dto(await get_task(task_id))


async def reject_task(task_id: str, operator_id: int, reason: str, *, expected_artifact_sha256: str,
                      expected_review_revision: int) -> dict:
    """Record rejected immutable identity, then recompile without replacing media."""
    reason = ReviewFeedback(reason=reason).reason
    async with transaction() as (_, cur):
        await cur.execute("SELECT *,NOW(6) AS audit_time FROM video_knowledge_task WHERE id=%s FOR UPDATE", (task_id,))
        row = _dict(cur, await cur.fetchone())
        if not row:
            raise AppException("40400", "视频知识任务不存在", http_status=404)
        if row["status"] != "awaiting_review" or row.get("reviewed_by") is not None:
            raise AppException("40900", "仅未审核发布的待审核任务可以拒绝", http_status=409)
        data = json.loads(row["data_json"])
        if (data.get("artifact_sha256"), data.get("review_revision", 0)) != (expected_artifact_sha256, expected_review_revision):
            raise AppException("40900", "待审核资料已更新，请重新预览当前版本", http_status=409)
        history = data.get("review_history", [])
        if not isinstance(history, list):
            raise AppException("40900", "审核记录格式异常，请检查任务", http_status=409)
        if len(history) >= 20:
            raise AppException("40900", "本任务已达到20次审核拒绝上限，请检查生成方案", http_status=409)
        if data.get("publication") or data.get("ingestion"):
            raise AppException("40900", "已有发布记录的任务不能通过拒绝撤回", http_status=409)
        identity = {"artifact_sha256": data.get("artifact_sha256"), "generation": data.get("artifact_generation")}
        if not all(isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
                   for value in identity.values()):
            raise AppException("40900", "待审核资料缺少完整标识，请检查任务", http_status=409)
        history = [*history, {**identity, "artifact_directory": data.get("artifact_directory", "compiled"),
                   "reason": reason, "operator_id": operator_id, "rejected_at": row["audit_time"].isoformat()}]
        data["review_history"] = history
        data["review_revision"] = len(history)
        for field in ("artifact_path", "artifact_sha256", "artifact_generation", "artifact_directory",
                      "exercise_package", "exercise_publication"):
            data.pop(field, None)
        # Existing immutable files and all playback/RAG records remain untouched.
        await cur.execute("UPDATE video_knowledge_task SET status='queued',stage='compiling',data_json=%s,"
                          "error_code=NULL,error_message=NULL,lease_token=NULL,lease_expires_at=NULL "
                          "WHERE id=%s", (json.dumps(data, ensure_ascii=False), task_id))
    return task_dto(await get_task(task_id))


async def claim_task() -> tuple[dict, str] | None:
    token = uuid.uuid4().hex
    async with transaction() as (_, cur):
        # A replacement advisory-lock owner must not start heavy work while an
        # old process is still draining an operation after losing its connection.
        # Expired running tasks remain explicit operator recovery decisions.
        await cur.execute("SELECT id FROM video_knowledge_task WHERE status='running' LIMIT 1 FOR UPDATE")
        if await cur.fetchone():
            return None
        await cur.execute("SELECT * FROM video_knowledge_task WHERE status IN ('queued','approved') "
                          "ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED")
        row = _dict(cur, await cur.fetchone())
        if not row:
            return None
        await cur.execute("UPDATE video_knowledge_task SET status='running',attempt=attempt+1,lease_token=%s,"
                          "lease_expires_at=DATE_ADD(NOW(6),INTERVAL %s SECOND) WHERE id=%s",
                          (token, LEASE_SECONDS, row["id"]))
    row["status"] = "running"
    row["attempt"] += 1
    return row, token


class LeaseLost(RuntimeError):
    pass


async def _assert_owned(task_id: str, token: str) -> None:
    # MySQL normally reports changed rows. Setting an identical stage/JSON or
    # renewing twice within one clock tick can affect zero rows without losing
    # ownership. Recheck on the primary connection, with the database clock.
    async with transaction() as (_, cur):
        await cur.execute("SELECT id FROM video_knowledge_task WHERE id=%s AND lease_token=%s "
                          "AND status='running' AND lease_expires_at>NOW(6)", (task_id, token))
        if not await cur.fetchone():
            raise LeaseLost("Video production lease lost")


async def auto_approve_owned(task_id: str, token: str, operator_id: int, data: dict) -> None:
    """Fence automatic authorization to the validated immutable candidate and creator."""
    data["publication_policy"] = "automatic_after_validation"
    changed = await execute_write(
        "UPDATE video_knowledge_task SET reviewed_by=%s,reviewed_at=NOW(6),data_json=%s "
        "WHERE id=%s AND created_by=%s AND reviewed_by IS NULL AND lease_token=%s "
        "AND status='running' AND lease_expires_at>NOW(6) "
        "AND JSON_UNQUOTE(JSON_EXTRACT(data_json,'$.artifact_sha256'))=%s "
        "AND JSON_UNQUOTE(JSON_EXTRACT(data_json,'$.artifact_generation'))=%s",
        (operator_id, json.dumps(data, ensure_ascii=False), task_id, operator_id, token,
         data["artifact_sha256"], data["artifact_generation"]))
    if changed != 1:
        raise LeaseLost("Automatic publication candidate or ownership changed")


async def heartbeat(task_id: str, token: str) -> None:
    changed = await execute_write("UPDATE video_knowledge_task SET lease_expires_at=DATE_ADD(NOW(6),INTERVAL %s SECOND) "
                                  "WHERE id=%s AND lease_token=%s AND status='running' AND lease_expires_at>NOW(6)",
                                  (LEASE_SECONDS, task_id, token))
    if changed != 1:
        await _assert_owned(task_id, token)


async def update_owned(task_id: str, token: str, *, stage: str | None = None, data: dict | None = None,
                       status: str | None = None, error_code: str | None = None, error_message: str | None = None) -> None:
    fields, values = [], []
    for field, value in (("stage", stage), ("data_json", json.dumps(data, ensure_ascii=False) if data is not None else None),
                         ("status", status), ("error_code", error_code), ("error_message", error_message)):
        if value is not None:
            fields.append(f"{field}=%s")
            values.append(value)
    if status in ("failed", "awaiting_review", "completed"):
        fields += ["lease_token=NULL", "lease_expires_at=NULL"]
    if not fields:
        return
    changed = await execute_write("UPDATE video_knowledge_task SET " + ",".join(fields) +
                                  " WHERE id=%s AND lease_token=%s AND status='running' AND lease_expires_at>NOW(6)",
                                  tuple(values + [task_id, token]))
    if changed != 1:
        await _assert_owned(task_id, token)
