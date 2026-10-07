"""One project-owned video worker; web jobs reuse its existing BGE singleton.

Run with the EDU Python environment: python -m app.domains.video_learning.task_worker.
MySQL's advisory lock enforces a single worker even with multiple web processes.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import suppress
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from app.database import init_mysql, close_mysql, init_minio, close_minio, get_mysql_pool, transaction
from app.domains.video_learning import tasks
from app.domains.video_learning.artifacts import load_video_artifact
from app.common.logging import logger

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TASK_ROOT = PROJECT_ROOT / "data" / "video_knowledge_tasks"


# Lazy imports keep API startup independent from optional download/ASR packages.
def prepare_media(workdir: Path, bvid: str, page: int) -> dict:
    from app.domains.video_learning.media import prepare_media as prepare
    return prepare(workdir, bvid, page)


def transcribe_media(prepared: dict, mode: str) -> Path:
    if prepared["source"].get("platform") == "edu":
        from app.domains.video_learning.bound_media import transcribe_bound_media
        return transcribe_bound_media(prepared, mode)
    from app.domains.video_learning.media import transcribe_media as transcribe
    return transcribe(prepared, mode)


def compile_artifact(transcript: Path, prepared: dict, output: Path, review_feedback: str = ""):
    from app.domains.video_learning.compiler import compile_video
    return compile_video(subtitle=transcript, discovery=Path(prepared["discovery"]), output=output,
                         review_feedback=review_feedback)


def fetch_ready_for_exercises(row: dict, workdir: Path) -> Path:
    from app.services.source_asset_store import SourceAssetStore
    # Use the same verified immutable object as student video knowledge.
    from app.domains.video_learning.publication import _read_verified_artifact
    store = SourceAssetStore()
    artifact = _read_verified_artifact(store, row)
    path = workdir / "compiled" / artifact.content_sha256 / "artifact.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
    return path


async def produce_exercises(task: dict, data: dict, artifact, workdir: Path, *, token: str, check_lock=None):
    from app.domains.video_learning.exercises import generate_exercises, install_exercises
    if (data.get("exercise_package") or {}).get("generation") != artifact.content_sha256:
        data.pop("exercise_package", None)
        data.pop("exercise_publication", None)
    if not data.get("exercise_package"):
        data["exercise_package"] = await _blocking(generate_exercises, artifact, workdir)
    if check_lock:
        await check_lock()
    await tasks.update_owned(task["id"], token, stage="exercises", data=data)
    data["exercise_publication"] = await install_exercises(
        {**task, "data_json": json.dumps(data, ensure_ascii=False)}, artifact, data["exercise_package"], lease_token=token)


class IngestionProcessError(RuntimeError):
    """Native worker termination with a safe numeric result, never log content."""
    def __init__(self, exit_code: int):
        if type(exit_code) is not int:
            raise TypeError("Ingestion exit code must be an integer")
        self.exit_code = exit_code
        super().__init__(f"EDU RAG ingestion process exited with code {exit_code}")


def _compiler_failure(exc: Exception) -> tuple[str, str, str] | None:
    """Classify only finite known messages; never serialize validation inputs."""
    from pydantic import ValidationError
    from app.domains.video_learning.artifacts import ArtifactValidationError
    if isinstance(exc, ValidationError):
        # .errors() and str(exc) can include full input values and credentials.
        return "SCHEMA_VALIDATION", "schema_fields_rejected", "学习资料字段格式不符合要求；请检查字幕与模型结构化输出"
    if not isinstance(exc, ArtifactValidationError):
        return None
    message = str(exc)
    known = {
        "compiler requires a configured HTTPS LLM endpoint/model/key":
            ("LLM_CONFIGURATION", "llm_configuration_missing", "模型服务配置不完整；请检查 EDU 的 HTTPS 模型端点、模型名称及 API 密钥"),
        "input must be an uncompiled verified transcript source":
            ("TRANSCRIPT_SOURCE_CONTRACT", "transcript_source_unverified", "字幕来源合同未通过；请检查未编译字幕及来源标记"),
        "input must be an uncompiled platform-subtitle source":
            ("TRANSCRIPT_SOURCE_CONTRACT", "native_transcript_required", "此入口要求原生字幕；请检查任务转写模式"),
        "ASR transcript source lacks media provenance":
            ("ASR_MEDIA_PROVENANCE", "asr_media_provenance_missing", "ASR 转写缺少媒体溯源证据；请检查媒体校验和转写结果"),
        "platform subtitle source differs from source discovery":
            ("TRANSCRIPT_SOURCE_IDENTITY", "transcript_source_identity_mismatch", "字幕与视频来源身份不一致；请检查 BVID、分 P 与 CID"),
        "native source lacks a valid transcript/source contract":
            ("TRANSCRIPT_SOURCE_CONTRACT", "transcript_source_fields_invalid", "字幕输入字段不符合要求；请检查来源和转写结构"),
        "native subtitle has invalid time ordering or video bounds":
            ("TRANSCRIPT_TIMELINE", "transcript_timeline_invalid", "字幕时间顺序或范围超出视频；请检查转写时间轴"),
        "native subtitle segment count differs from discovery identity":
            ("TRANSCRIPT_SEGMENT_COUNT", "transcript_segment_count_mismatch", "字幕段数与来源记录不一致；请检查转写结果"),
        "native full transcript differs from its timed segments":
            ("TRANSCRIPT_TEXT_MISMATCH", "transcript_full_text_mismatch", "字幕全文与带时间戳分段不一致；请检查转写结果"),
        "discovery must contain one successfully probed page":
            ("SOURCE_DISCOVERY_INVALID", "source_discovery_unverified", "来源探查记录不完整；请检查指定分 P 的探查结果"),
        "chapter start is not near an actual subtitle segment":
            ("CHAPTER_ANCHOR_INVALID", "chapter_anchor_not_in_transcript", "章节起点没有对应字幕；请检查章节时间锚点"),
        "chapters must start at zero and increase":
            ("CHAPTER_TIMELINE_INVALID", "chapter_timeline_invalid", "章节须从零开始并递增；请检查生成的章节时间轴"),
        "knowledge-note stage must return only its Markdown field":
            ("NOTE_FORMAT_INVALID", "note_markdown_field_invalid", "AI 笔记字段格式不正确；请检查模型结构化输出"),
        "knowledge note must be a complete nonempty Markdown note":
            ("NOTE_CONTENT_INVALID", "note_content_incomplete", "AI 笔记为空或不完整；请检查笔记生成结果"),
        "compiler checkpoint checksum or stage input changed":
            ("COMPILER_CHECKPOINT_INVALID", "checkpoint_input_changed", "已完成阶段的断点校验不一致；请检查任务断点和来源输入"),
        "compiler checkpoint has mismatched model provenance":
            ("COMPILER_CHECKPOINT_INVALID", "checkpoint_model_mismatch", "已完成阶段的模型记录不一致；请检查任务断点"),
        "model reply provenance does not match its compiler stage":
            ("LLM_PROVENANCE_INVALID", "model_stage_provenance_mismatch", "模型回复的阶段溯源不一致；请检查生成记录"),
    }
    if message in known:
        return known[message]
    labels = {"summary": "课程总结", "knowledge_note": "AI 笔记", "exercises": "本课习题"}
    transport = re.fullmatch(r"LLM (summary|knowledge_note|exercises) transport failed \(([A-Za-z]+)\)", message)
    if transport:
        stage, kind = transport.groups()
        timeouts = {"ConnectTimeout", "ReadTimeout", "WriteTimeout", "PoolTimeout", "TimeoutException"}
        connections = {"ConnectError", "ReadError", "WriteError", "CloseError", "ProxyError", "NetworkError"}
        protocols = {"RemoteProtocolError", "LocalProtocolError", "ProtocolError", "UnsupportedProtocol", "DecodingError", "TooManyRedirects"}
        if kind in timeouts:
            return "LLM_TRANSPORT_TIMEOUT", f"{stage}_{kind}", f"{labels[stage]}模型请求超时（{kind}）；成功阶段已保留，请检查模型服务连接后重试"
        if kind in connections:
            return "LLM_TRANSPORT_CONNECTION", f"{stage}_{kind}", f"{labels[stage]}模型连接失败（{kind}）；请检查网络与模型服务可用性后重试"
        if kind in protocols:
            return "LLM_TRANSPORT_PROTOCOL", f"{stage}_{kind}", f"{labels[stage]}模型连接协议异常（{kind}）；请检查模型端点后重试"
    http_error = re.fullmatch(r"LLM (summary|knowledge_note|exercises) request failed with HTTP ([1-5][0-9]{2})", message)
    if http_error:
        stage, status = http_error.groups()
        return "LLM_HTTP_STATUS", f"{stage}_http_{status}", f"{labels[stage]}模型服务返回 HTTP {status}；检查服务权限、额度或限流后重试"
    response = re.fullmatch(r"LLM (summary|knowledge_note|exercises) returned an invalid response contract", message)
    if response:
        stage = response[1]
        return "LLM_RESPONSE_CONTRACT", f"{stage}_response_contract_invalid", f"{labels[stage]}模型响应格式不符合要求；请检查模型是否支持结构化输出"
    content = re.fullmatch(r"LLM (summary|knowledge_note|exercises) failed its content contract after one repair", message)
    if content:
        stage = content[1]
        return "LLM_CONTENT_CONTRACT", f"{stage}_content_contract_rejected_after_repair", f"{labels[stage]}内容在一次修复后仍未满足要求；请检查生成内容的结构和时间锚点后重试"
    budget = re.match(r"^LLM (summary|knowledge_note|exercises) output exceeded its bounded token budget:", message)
    if budget:
        stage = budget[1]
        return "LLM_TOKEN_BUDGET", f"{stage}_token_budget_exceeded", f"{labels[stage]}模型输出超过预算；请检查模型输出限制后重试"
    return "UNKNOWN_ARTIFACT_VALIDATION", "unspecified_artifact_validation", "学习资料校验未通过；请检查字幕和模型输出后重试"


def operator_error(exc: Exception) -> str:
    """Explain known, bounded errors without exposing raw provider payloads."""
    from app.domains.video_learning.media import MediaError
    if isinstance(exc, IngestionProcessError):
        return f"入库进程退出，退出码 {exc.exit_code}；请检查模型运行环境后重试，已发布的学习资料仍可使用"
    if isinstance(exc, MediaError):
        return str(exc)[:200]  # MediaError contains only local operator-safe messages.
    failure = _compiler_failure(exc)
    if failure:
        return failure[2]
    return "阶段执行失败；请检查系统连接和任务日志后重试"


def write_diagnostic(workdir: Path, stage: str, exc: Exception) -> None:
    """Task-local diagnostic allowlist; never log SQL arguments or raw responses."""
    from asyncmy.errors import MySQLError
    from pymysql.err import MySQLError as SyncMySQLError
    database_code = None
    if isinstance(exc, (MySQLError, SyncMySQLError)) and exc.args and type(exc.args[0]) is int:
        database_code = exc.args[0]
    failure = _compiler_failure(exc)
    packet = {"at": datetime.now(timezone.utc).isoformat(), "stage": stage,
              "exception": type(exc).__name__, "database_code": database_code,
              "validation_code": failure[0] if failure else None,
              "known_reason": failure[1] if failure else None,
              "safe_reason": operator_error(exc)}
    # data/video_knowledge_tasks is outside public/static media paths and is not
    # exposed by task DTOs. Diagnostics are for local service operators only.
    with (workdir / "diagnostics.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(packet, ensure_ascii=False) + "\n")


async def _blocking(function, *args):
    from app.observability.tracing import span
    with span('video.'+function.__name__):
        return await _blocking_operation(function,*args)


async def _blocking_operation(function, *args):
    # Losing a lease must not start the next expensive task while an abandoned
    # to_thread download/ASR still runs. Drain that operation before proceeding;
    # the caller remains cancelled and cannot bind/publish its result.
    operation = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(operation)
    except asyncio.CancelledError:
        with suppress(Exception):
            await asyncio.shield(operation)
        raise


class WorkerLockLost(tasks.LeaseLost):
    """The pinned worker connection lost its global advisory lock."""


async def verify_worker_lock(connection, owner_id: int) -> None:
    # Do not ping/reconnect: a new connection cannot inherit the old lock.
    try:
        async with connection.cursor() as cur:
            await cur.execute("SELECT CONNECTION_ID(),IS_USED_LOCK('edu_video_knowledge_worker')")
            row = await cur.fetchone()
        if not row or row[0] != owner_id or row[1] != owner_id:
            raise WorkerLockLost("Dedicated video worker connection lost lock ownership")
    except WorkerLockLost:
        raise
    except Exception as exc:
        raise WorkerLockLost("Dedicated video worker lock connection is unavailable") from exc


def worker_lock_guard(connection, owner_id: int):
    # asyncmy has one protocol reader per connection. The stage runner and
    # renewal coroutine share this pinned connection, so serialize their probes.
    verification_lock = asyncio.Lock()
    async def check_lock():
        async with verification_lock:
            await verify_worker_lock(connection, owner_id)
    return check_lock


async def bind_playback(task: dict, prepared: dict) -> dict:
    """Atomic authoritative binding before any derived operation; never replace."""
    from app.domains.course_admin.schemas import AssetCreateAdmin, VideoCreateAdmin
    source = prepared["source"]
    code = f"{source['bvid']}_P{source['page']}_{source['cid']}"
    reference = f"minio://{prepared['bucket']}/{prepared['key']}"
    size = prepared.get("size_bytes") or Path(prepared["media"]).stat().st_size
    duration = float(prepared["duration"])
    asset = AssetCreateAdmin(session_id=task["session_id"], asset_code=code, asset_name=source["title"],
        file_type="mp4", material_category="video", access_scope="enrolled_only", file_url=reference,
        file_size=size, uploader_user_id=task["created_by"]).model_dump()
    video = VideoCreateAdmin(asset_id=1, video_code=code, video_title=source["title"],
        duration_seconds=round(duration), bitrate_kbps=round(size * 8 / duration / 1000),
        transcode_status="completed", review_status="approved").model_dump()
    async with transaction() as (_, cur):
        await cur.execute("SELECT id FROM series_cohort_session WHERE id=%s FOR UPDATE", (task["session_id"],))
        if not await cur.fetchone():
            raise ValueError("Target lesson no longer exists")
        await cur.execute("SELECT sv.id,sv.video_code,sa.id,sa.file_url FROM session_video sv "
                          "JOIN session_asset sa ON sa.id=sv.asset_id WHERE sa.session_id=%s ORDER BY sv.id", (task["session_id"],))
        existing = await cur.fetchall()
        if existing:
            if len(existing) != 1 or existing[0][1] != code or existing[0][3] != reference:
                raise ValueError("Existing lesson playback source differs; replacement is prohibited")
            return {"video_id": int(existing[0][0]), "asset_id": int(existing[0][2])}
        await cur.execute("SELECT id FROM session_video WHERE video_code=%s LIMIT 1", (code,))
        if await cur.fetchone():
            raise ValueError("Video is already bound to a different lesson")
        await cur.execute("INSERT INTO session_asset (session_id,asset_code,asset_name,file_type,material_category,"
                          "sort_no,access_scope,file_url,file_size,uploader_user_id,created_at,updated_at) "
                          "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(6),NOW(6))",
                          tuple(asset[k] for k in ("session_id", "asset_code", "asset_name", "file_type", "material_category",
                                                 "sort_no", "access_scope", "file_url", "file_size", "uploader_user_id")))
        asset_id = int(cur.lastrowid)
        await cur.execute("INSERT INTO session_video (asset_id,video_code,video_title,duration_seconds,bitrate_kbps,"
                          "transcode_status,review_status,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,NOW(6),NOW(6))",
                          (asset_id, video["video_code"], video["video_title"], video["duration_seconds"], video["bitrate_kbps"],
                           video["transcode_status"], video["review_status"]))
        return {"video_id": int(cur.lastrowid), "asset_id": asset_id}


async def publish_artifact(video_id: int, path: Path) -> dict:
    from app.domains.video_learning.publication import publish_video_artifact
    return await publish_video_artifact(video_id, path, rag_pending=True)


async def activate_artifact(video_id: int, artifact_sha256: str, receipt: dict) -> dict:
    from app.domains.video_learning.publication import activate_video_publication
    return await activate_video_publication(video_id, artifact_sha256, receipt)


async def ingest_artifact(task: dict, data: dict, workdir: Path, *, borrowed_resources: bool = False) -> dict:
    receipt = workdir / "ingestion.json"
    if borrowed_resources:
        from app.domains.video_learning.ingestion import ingest
        args = argparse.Namespace(artifact=Path(data["artifact_path"]), video_id=data["binding"]["video_id"],
                                  operator_id=task["reviewed_by"], receipt=receipt,trace_context=data.get('production_trace'))
        async def complete_ingestion():
            result = await ingest(args, borrowed_resources=True)
            if result.get("status") not in ("PASS", "passed", "completed", "ingested"):
                raise ValueError("Ingestion receipt did not verify success")
            temporary = receipt.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
            os.replace(temporary, receipt)
            return result
        operation = asyncio.create_task(complete_ingestion())
        try:
            return await asyncio.shield(operation)
        except asyncio.CancelledError:
            # A lost task/global fence may cancel the runner. Keep the owner
            # awaiting the same bounded import until its threads and writes end.
            while not operation.done():
                with suppress(asyncio.CancelledError, Exception):
                    await asyncio.shield(operation)
            with suppress(Exception):
                operation.result()
            raise
    output = workdir / "ingestion.log"
    command = [sys.executable, "-m", "app.domains.video_learning.ingestion", "--artifact", data["artifact_path"],
               "--video-id", str(data["binding"]["video_id"]), "--operator-id", str(task["reviewed_by"]),
               "--receipt", str(receipt)]
    # Avoid stdout pipes filling on embedding initialization. Logs remain local,
    # and public task errors never contain raw provider responses or credentials.
    started_at = datetime.now(timezone.utc).isoformat()
    with output.open("ab") as log:
        child = await asyncio.create_subprocess_exec(*command, cwd=PROJECT_ROOT, stdout=log, stderr=log,
                  env={**os.environ,'EDU_VIDEO_TRACE_CONTEXT':json.dumps(data.get('production_trace') or {})},
                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            code = await child.wait()
        except BaseException:
            if child.returncode is None:
                child.terminate()
                await child.wait()
            raise
    process_result = {"exit_code": code, "started_at": started_at,
                      "ended_at": datetime.now(timezone.utc).isoformat()}
    process_receipt = workdir / "ingestion-process.json"
    temporary = process_receipt.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(process_result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, process_receipt)
    if code != 0:
        raise IngestionProcessError(code)
    result = json.loads(receipt.read_text(encoding="utf-8"))
    if result.get("status") not in ("PASS", "passed", "completed", "ingested"):
        raise ValueError("Ingestion receipt did not verify success")
    return result


async def run_task(task: dict, token: str, *, root: Path = TASK_ROOT, check_lock=None,
                   borrowed_resources: bool = False) -> None:
    from app.observability.tracing import span,remote_parent
    data=json.loads(task.get('data_json') or '{}')
    with span('video.produce',parent=remote_parent(data.get('trace_context')),
              attributes={'task.id':task['id'],'session.id':task.get('session_id',0)}) as trace:
        if trace:data['production_trace']={'trace_id':trace.trace_id,'span_id':trace.span_id}
        return await _run_task({**task,'data_json':json.dumps(data)},token,root=root,check_lock=check_lock,borrowed_resources=borrowed_resources)


def _relocate_task_data(data: dict, workdir: Path) -> dict:
    """Resolve this task's pre-rename local paths without rewriting stored evidence."""
    if len(workdir.parents) < 3 or workdir.parents[2].name != "bili-study-agent":
        return data
    legacy = (workdir.parents[2].with_name("edu-agent") / "data" / "video_knowledge_tasks" / workdir.name).resolve()

    def relocate(value):
        if isinstance(value, dict):
            return {key: relocate(item) for key, item in value.items()}
        if isinstance(value, list):
            return [relocate(item) for item in value]
        if isinstance(value, str) and Path(value).is_absolute():
            try:
                relative = Path(value).resolve().relative_to(legacy)
            except ValueError:
                return value
            return str((workdir / relative).resolve())
        return value

    return relocate(data)


async def _run_task(task: dict, token: str, *, root: Path = TASK_ROOT, check_lock=None,
                    borrowed_resources: bool = False) -> None:
    workdir = root / task["id"]
    workdir.mkdir(parents=True, exist_ok=True)
    data = _relocate_task_data(json.loads(task.get("data_json") or "{}"), workdir)
    stage = task.get("stage", "acquiring")
    async def save(next_stage: str, *, status: str | None = None):
        nonlocal stage
        if check_lock:
            await check_lock()
        stage = next_stage
        await tasks.update_owned(task["id"], token, stage=stage, data=data, status=status)
    try:
        if data.get("exercises_only"):
            await save("exercises")
            if not data.get("artifact_path"):
                from app.domains.video_learning.publication import get_video_publication
                row = await get_video_publication(int(data["binding"]["video_id"]))
                if not row or row["artifact_sha256"] != data["reused_ready_publication"]["artifact_sha256"]:
                    raise ValueError("Formal video version changed")
                path = await _blocking(fetch_ready_for_exercises, row, workdir)
                artifact = load_video_artifact(path)
                data.update(artifact_path=str(path.resolve()), artifact_sha256=artifact.artifact_sha256,
                            artifact_generation=artifact.content_sha256, artifact_directory="compiled")
                data["publication"] = {k: row[k] for k in ("id", "video_id", "artifact_sha256")}
            artifact = load_video_artifact(Path(data["artifact_path"]))
            await produce_exercises(task, data, artifact, workdir, token=token, check_lock=check_lock)
            await save("complete", status="completed")
            return
        if not task.get("reviewed_by"):
            if not data.get("prepared"):
                await save("acquiring")
                if data.get("source_kind") == "existing_video":
                    from app.domains.video_learning.bound_media import prepare_bound_media
                    source = await tasks.resolve_bound_task(task)
                    data["prepared"] = await _blocking(prepare_bound_media, workdir, source)
                    if check_lock:
                        await check_lock()
                else:
                    data["prepared"] = await _blocking(prepare_media, workdir, task["bvid"], task["page"])
            if data.get("source_kind") == "existing_video":
                # Acquisition can be cached after a metadata-write failure.
                # Repair must therefore be retried independently of download.
                await tasks.repair_missing_duration(task, token, data["prepared"])
                data["metadata_verified"] = True
            await save("binding")
            if not data.get("binding"):
                data["binding"] = await bind_playback(task, data["prepared"])
            # Persist playback independently, including when later ASR fails.
            await save("transcribing")
            if not data.get("transcript_path"):
                transcript = await _blocking(transcribe_media, data["prepared"], task["transcript_mode"])
                data["transcript_path"] = str(transcript.resolve())
                raw = json.loads(transcript.read_text(encoding="utf-8"))
                data["transcript_origin"] = raw.get("transcript_source")
            await save("compiling")
            revision = data.get("review_revision", 0)
            if type(revision) is not int or not 0 <= revision <= 20:
                raise ValueError("Invalid bounded review revision")
            artifact_directory = "compiled" if revision == 0 else f"compiled-r{revision}"
            arguments = (Path(data["transcript_path"]), data["prepared"], workdir / artifact_directory)
            if revision:
                history = data.get("review_history", [])
                if not isinstance(history, list) or not history or len(history) != revision:
                    raise ValueError("Review revision differs from audit history")
                # Every recompile starts from source. Preserve all reviewed
                # requirements rather than making the latest rejection erase
                # fixes requested by earlier operators.
                reasons = [tasks.ReviewFeedback(reason=entry["reason"]).reason for entry in history]
                feedback = "以下是按审核版本顺序累积的反馈；较新反馈覆盖冲突的旧要求，其余要求继续保留。\n" + "\n".join(
                    f"第{index}次审核：{reason}" for index, reason in enumerate(reasons, 1))
                from app.domains.video_learning.compiler import MAX_REVIEW_FEEDBACK_CHARS
                if len(feedback) > MAX_REVIEW_FEEDBACK_CHARS:
                    raise ValueError("Accumulated review feedback exceeds its bounded contract")
                artifact_path = await _blocking(compile_artifact, *arguments, feedback)
            else:
                artifact_path = await _blocking(compile_artifact, *arguments)
            artifact = load_video_artifact(artifact_path)
            data["artifact_path"] = str(artifact_path.resolve())
            data["artifact_sha256"] = artifact.artifact_sha256
            data["artifact_generation"] = artifact.content_sha256
            data["artifact_directory"] = artifact_directory
            if data.get("exercise_enabled"):
                await save("exercises")
                await produce_exercises(task, data, artifact, workdir, token=token, check_lock=check_lock)
            if not data.get("auto_publish", not data.get("review_history")):
                await save("review", status="awaiting_review")
                return
            await save("publishing")
            await tasks.auto_approve_owned(task["id"], token, task["created_by"], data)
            task["reviewed_by"] = task["created_by"]
        # Review approves exactly the compiled immutable artifact, not a mutable
        # source file or provider response. Retries resume the same generation.
        await save("publishing")
        path = Path(data["artifact_path"])
        artifact = load_video_artifact(path)
        if artifact.artifact_sha256 != data["artifact_sha256"]:
            raise ValueError("Reviewed artifact identity changed")
        if not data.get("publication"):
            publication = await publish_artifact(data["binding"]["video_id"], path)
            data["publication"] = {k: publication[k] for k in ("id", "video_id", "artifact_sha256")}
        await save("ingesting")
        if not data.get("ingestion"):
            if borrowed_resources:
                result = await ingest_artifact(task, data, workdir, borrowed_resources=True)
            else:
                result = await ingest_artifact(task, data, workdir)
            data["ingestion"] = result
            await save("ingesting")
        if not data.get("activation"):
            activated = await activate_artifact(data["binding"]["video_id"], data["artifact_sha256"], data["ingestion"])
            data["activation"] = {"id": activated["id"], "rag_status": activated["rag_status"]}
        # Graph is derived from READY authority and existing vector IDs. Failure
        # must not undo activation, trigger another embedding, or disable playback.
        await save('graph')
        try:
            from .graph import project_ready_video
            data['graph_projection']=await project_ready_video(data['binding']['video_id'],expected_sha256=data['artifact_sha256'])
        except Exception as graph_error:
            data['graph_projection']={'status':'degraded','error':'课程图谱暂不可用，可在视频管理中重新同步；播放与正式 RAG 保持可用','reason':type(graph_error).__name__}
        await save("complete", status="completed")
    except tasks.LeaseLost:
        raise
    except Exception as exc:
        logger.warning(f"Video knowledge task {task['id']} failed at {stage}: {type(exc).__name__}")
        try:
            write_diagnostic(workdir, stage, exc)
        except Exception as diagnostic_error:
            logger.warning(f"Video task diagnostic unavailable: {type(diagnostic_error).__name__}")
        labels = {"acquiring": "获取视频", "binding": "绑定播放来源", "transcribing": "生成字幕",
                  "compiling": "编译学习资料", "exercises": "生成本课习题", "publishing": "发布学习资料", "ingesting": "知识入库"}
        playback = "原视频仍可独立播放。" if data.get("binding") else "尚未生成播放绑定。"
        await tasks.update_owned(task["id"], token, stage=stage, data=data, status="failed",
                                 error_code=type(exc).__name__,
                                 error_message=f"{labels.get(stage, stage)}失败：{operator_error(exc)}。{playback}")


async def _keep_lease(task_id: str, token: str, check_lock=None):
    while True:
        await asyncio.sleep(30)
        if check_lock:
            await check_lock()
        await tasks.heartbeat(task_id, token)


async def serve(*, once: bool = False, owns_resources: bool = True, stop_event: asyncio.Event | None = None,
                resume: bool = False):
    if owns_resources:
        await init_mysql()
        init_minio()
    lock_connection = None
    task_connection = None
    try:
        await tasks.ensure_schema()
        from app.domains.video_learning.schema import PUBLICATION_DDL
        await tasks.execute_write(PUBLICATION_DDL)
        pool = get_mysql_pool()
        lock_connection = await pool.acquire()
        async with lock_connection.cursor() as cur:
            await cur.execute("SELECT CONNECTION_ID(),GET_LOCK('edu_video_knowledge_worker',0)")
            ownership = await cur.fetchone()
            if ownership[1] != 1:
                return
            owner_id = int(ownership[0])
        check_lock = worker_lock_guard(lock_connection, owner_id)
        if resume:
            # Resume only after this process owns the global fence. A paused
            # web supervisor cannot race a fresh standalone worker for claims.
            (TASK_ROOT / "stop.request").unlink(missing_ok=True)
        while not (TASK_ROOT / "stop.request").exists() and not (stop_event and stop_event.is_set()):
            await check_lock()
            claimed = await tasks.claim_task()
            if claimed:
                task, token = claimed
                task_connection = await pool.acquire()
                task_lock_key = "edu_video_task_" + task["id"]
                async with task_connection.cursor() as cur:
                    await cur.execute("SELECT CONNECTION_ID(),GET_LOCK(%s,0)", (task_lock_key,))
                    acquired = await cur.fetchone()
                if not acquired or acquired[1] != 1:
                    pool.release(task_connection)
                    task_connection = None
                    await tasks.update_owned(task["id"], token, status="failed", error_code="TaskLockBusy",
                                             error_message="原工作进程仍在安全停止；稍后刷新再重试，原视频不受影响")
                    continue
                task_owner = acquired[0]
                task_verification_lock = asyncio.Lock()
                async def check_operation_lock():
                    await check_lock()
                    async with task_verification_lock:
                        try:
                            async with task_connection.cursor() as cur:
                                await cur.execute("SELECT CONNECTION_ID(),IS_USED_LOCK(%s)", (task_lock_key,))
                                current = await cur.fetchone()
                            if not current or current[0] != task_owner or current[1] != task_owner:
                                raise WorkerLockLost("Video task operation lock was lost")
                        except WorkerLockLost:
                            raise
                        except Exception as exc:
                            raise WorkerLockLost("Video task operation lock is unavailable") from exc
                runner = asyncio.create_task(run_task(task, token, check_lock=check_operation_lock,
                                                      borrowed_resources=not owns_resources))
                renewal = asyncio.create_task(_keep_lease(task["id"], token, check_lock=check_operation_lock))
                global_lock_lost = False
                try:
                    done, _ = await asyncio.wait((runner, renewal), return_when=asyncio.FIRST_COMPLETED)
                    for completed in done:
                        await completed
                except WorkerLockLost:
                    global_lock_lost = True
                    logger.warning(f"Video worker lost its global lock during task {task['id']}; draining current operation")
                except tasks.LeaseLost:
                    logger.warning(f"Video task {task['id']} lost its fence; waiting for in-flight work before next task")
                finally:
                    runner.cancel()
                    renewal.cancel()
                    with suppress(asyncio.CancelledError, tasks.LeaseLost):
                        await runner
                    with suppress(asyncio.CancelledError, tasks.LeaseLost):
                        await renewal
                    with suppress(Exception):
                        async with task_connection.cursor() as cur:
                            await cur.execute("SELECT RELEASE_LOCK(%s)", (task_lock_key,))
                    pool.release(task_connection)
                    task_connection = None
                if global_lock_lost:
                    break
            if once:
                break
            if stop_event:
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(stop_event.wait(), timeout=2)
            else:
                await asyncio.sleep(2)
    except WorkerLockLost:
        logger.warning("Video worker lost its global lock before claim; stopping consumer")
    finally:
        if task_connection:
            # An acquisition/protocol failure before runner creation must not
            # leak the separate pinned operation connection into the pool.
            task_connection.close()
            get_mysql_pool().release(task_connection)
        if lock_connection:
            with suppress(Exception):
                async with lock_connection.cursor() as cur:
                    await cur.execute("SELECT RELEASE_LOCK('edu_video_knowledge_worker')")
            get_mysql_pool().release(lock_connection)
        if owns_resources:
            close_minio()
            await close_mysql()


def start_worker() -> subprocess.Popen:
    """Start a detached, hidden worker. MySQL prevents duplicate consumers.

    This optional standalone worker owns separate infrastructure pools. The
    default shared web worker instead drains before the web pools are closed.
    """
    TASK_ROOT.mkdir(parents=True, exist_ok=True)
    with (TASK_ROOT / "worker.log").open("ab") as log:
        return subprocess.Popen([sys.executable, "-m", "app.domains.video_learning.task_worker"],
                                cwd=PROJECT_ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)


async def supervise_worker(stop: asyncio.Event) -> None:
    """Consume the project queue with web-owned pools and its loaded BGE model."""
    while not stop.is_set():
        try:
            await serve(owns_resources=False, stop_event=stop)
        except Exception as exc:
            logger.warning(f"Video worker supervision unavailable: {type(exc).__name__}")
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=10)


async def drain_worker(supervisor: asyncio.Task, stop: asyncio.Event) -> None:
    """Stop new claims and finish the active operation before closing web pools."""
    stop.set()
    while not supervisor.done():
        try:
            await asyncio.shield(supervisor)
        except asyncio.CancelledError:
            # Lifespan cancellation must not abandon an embedding/write thread.
            # A second forced OS termination remains outside process guarantees.
            logger.warning("Video shutdown is waiting for the active operation to finish")
    await supervisor


async def wait_stopped(*, timeout: float = 15) -> bool:
    """Read the advisory owner until it releases; never terminate a process."""
    await init_mysql()
    try:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            if not (await tasks.worker_status())["running"]:
                return True
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return False
            await asyncio.sleep(min(1, remaining))
    finally:
        await close_mysql()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Process at most one queued task")
    parser.add_argument("--stop", action="store_true", help="Stop after the current task; never interrupt playback or in-flight processing")
    parser.add_argument("--resume", action="store_true", help="Remove an operator stop request and run the worker")
    parser.add_argument("--unpause", action="store_true", help="Remove only the stop request; web supervision starts the worker")
    parser.add_argument("--wait-stopped", action="store_true", help="Wait for the worker lock to release; timeout never kills the backend")
    parser.add_argument("--timeout", type=int, default=15, help="Graceful stop wait in seconds, 0 to 600 (default 15)")
    args = parser.parse_args()
    if not 0 <= args.timeout <= 600:
        parser.error("--timeout must be between 0 and 600 seconds")
    if args.wait_stopped:
        try:
            stopped = asyncio.run(wait_stopped(timeout=args.timeout))
        except Exception as exc:
            print(f"Worker stop could not be verified ({type(exc).__name__}); backend must remain running.")
            sys.exit(2)
        if not stopped:
            print("Video task is still draining. Backend remains running; wait and retry, or use --timeout up to 600.")
            sys.exit(1)
        print("Video worker stopped; its advisory lock has been released.")
    elif args.stop:
        TASK_ROOT.mkdir(parents=True, exist_ok=True)
        (TASK_ROOT / "stop.request").write_text("operator requested graceful stop\n", encoding="utf-8")
    elif args.unpause:
        (TASK_ROOT / "stop.request").unlink(missing_ok=True)
    else:
        asyncio.run(serve(once=args.once, resume=args.resume))
