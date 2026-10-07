"""
知识库上传路由 - 支持多租户文件上传（P1 步骤 9）+ task36 RAG 双写增强

API 端点:
- POST /api/knowledge/upload        : 用户上传私有知识 → BackgroundTasks 跑 P1 pipeline(5 节点)
- POST /api/knowledge/admin/upload  : 管理员上传公共知识（RBAC 强制 require_role(admin/manager)）
- GET  /api/knowledge/tasks         : 管理员分页倒序查询导入任务（task36 新增，契约⑥）
- GET  /api/knowledge/status/{task_id} : 查询任务状态
- GET  /api/knowledge/partitions    : 查询所有分区（管理员）
- DELETE /api/knowledge/partitions/{tenant_id} : 删除指定分区（管理员）

task36 双写与留存：
- 任务状态写 MySQL knowledge_import_task（真相源）+ Redis edu:knowledge:task:{id} TTL 24h
- 上传源文件留存 MinIO edu-upload（30 天生命周期），object_key 记入任务表，导入完成不删源文件
- Redis / MinIO 任一不可用均优雅降级（MySQL 为真相源），不阻断上传主链路

P1 pipeline 流程：parse → chunk → embed → load(Milvus) → graph_build(Neo4j)
"""

import hashlib
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Annotated

import anyio
import asyncio
from fastapi import APIRouter, Depends, UploadFile, File, Form, BackgroundTasks, HTTPException
from loguru import logger

from app.auth import require_role, UserRole, get_current_user
from app.auth.dependencies import CurrentUser
from app.common.exceptions import DependencyUnavailableError
from app.config import settings
from app.knowledge.importer.loader import (
    ensure_collection_exists,
    ensure_partition_exists,
    list_all_partitions,
    drop_partition,
)
from app.knowledge.importer.pipeline import run_import_pipeline
from app.knowledge.models import ImportState, Visibility
from app.knowledge import task_store
from app.core.resp import ok
from app.services.minio_uploader import get_uploader

router = APIRouter(prefix="/api/knowledge", tags=["知识库管理"])

# 允许的最大单文件大小：200MB（课件 PDF/课程介绍 Markdown 够了；视频走 MinIO 独立接口）
_MAX_FILE_BYTES = 200 * 1024 * 1024
_ALLOWED_SUFFIXES = {".md", ".txt", ".markdown", ".pdf", ".docx"}

# edu-upload 30 天留存生命周期：进程内仅设置一次（best-effort）
_lifecycle_ensured = False


def _ensure_lifecycle_once() -> None:
    """进程内仅一次尝试为 edu-upload 设置 30 天生命周期（best-effort，失败不阻断）。"""
    global _lifecycle_ensured
    if _lifecycle_ensured:
        return
    _lifecycle_ensured = True
    try:
        get_uploader().ensure_upload_bucket_lifecycle(30)
    except Exception as exc:
        logger.warning(
            f"[task36] 初始化 edu-upload 生命周期失败（留存仍生效但不过期）：{exc}"
        )


def _resolve_upload_dir() -> Path:
    """本地临时落盘目录（MinIO 还没上传之前）。"""
    upload_dir = Path(settings.DATA_DIR) / "knowledge_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def _sanitize_filename(raw: str | None) -> str:
    if not raw:
        return "unnamed"
    name = Path(raw).name
    # 去掉路径分隔符/危险字符
    for ch in ['\\', '/', ':', '*', '?', '"', '<', '>', '|', '\x00']:
        name = name.replace(ch, '_')
    return name or "unnamed"


def _make_upload_basename(user_id: int | str, safe_name: str) -> str:
    """生成上传临时文件名（WNEXTRAG1 修复）。

    旧实现用 ``uuid4().hex[:12] + ext`` 作临时 basename（如 ``a1b2c3d4e5f6.md``），
    100% 命中 ``classify_internal`` 的来源正则 ``^[0-9a-f]{8,32}\\.(md|txt|pdf)$``
    → 所有用户上传的 doc_chunk 被标 ``internal=True`` → 学生检索侧剔除 →
    学生（含上传者本人）查不到自己上传的知识库（T10 实证 739/742）。

    新命名带显式非 hex 前缀 ``up_{user_id}_``，保证 basename 不会被该来源正则
    误判为内部工程文档；``safe_name`` 保留原文件名便于追溯，uuid 段仅作防碰撞。
    向后兼容：旧 hash 命名文件（如 ``_default`` 内部文档库导出）仍会被
    ``classify_internal`` 判为 internal（来源正则不变）。
    """
    return f"up_{user_id}_{uuid.uuid4().hex[:8]}_{safe_name}"


def _make_minio_object_key(safe_name: str, content_sha256: str) -> str:
    """为 MinIO edu-upload 构造全局唯一 object_key（W-NEXT-MINIO-001 修复）。

    旧实现把 ``safe_name``（如 ``my_doc.md``）原样作为 object_key 上传 MinIO，
    多次导入同名文件（不同用户 / 不同时刻 / 同内容/不同内容）会沿用同一 key
    → MinIO ``put_object`` 同名静默覆盖，导致 source_files 留存错位、无法按
    object_key 反查历史版本（T14 报告 §10 P2 观察）。

    新格式：``f"{content_hash8}_{rand6}_{safe_name}"``
      - ``content_hash8`` = sha256(文件内容) 的前 8 个 hex 字符：
          同名同内容两次上传 → 同一 hash → 同一 object_key（合法幂等）；
          同名不同内容（如笔记 v1 / 笔记 v2 改了几个字） → 不同 hash → 不同 key，
          绝不互相覆盖。
      - ``rand6`` = uuid4().hex[:6]：
          极小概率 hash 碰撞（如攻击者构造）下第二层防御；同内容连续两次上传也
          因 random6 不同而保留两份独立对象（默认行为：源文件按要求留存）。如果
          需严格幂等，调用方可在外部对 ``(sha256)`` 做查重。
      - ``safe_name`` 保留原文件名，便于运维/MinIO 控制台人眼定位。

    该函数纯函数、无副作用；仅在 _upload_to_minio 内部调用。
    """
    h8 = (content_sha256 or "")[:8] or "0" * 8
    return f"{h8}_{uuid.uuid4().hex[:6]}_{safe_name}"


def _user_tenant_id(user_id: int | str) -> str:
    return f"user_{user_id}"


async def _write_upload_to_disk(file: UploadFile, user_id: int | str | None = None) -> tuple[str, int, str]:
    """
    把 UploadFile 同步写磁盘（FastAPI UploadFile 是 SpooledTemporaryFile，需要读出来）。
    返回 (absolute_path, bytes_written, content_sha256_hex) — sha256 用于 W-NEXT-MINIO-001 派生
    唯一 object_key，避免同名文件多次上传在 MinIO edu-upload 中被同名覆盖。
    """
    upload_dir = _resolve_upload_dir()
    safe_name = _sanitize_filename(file.filename)
    uid = user_id if user_id is not None else "anon"
    unique = _make_upload_basename(uid, safe_name)
    dest = upload_dir / unique

    size_written = 0
    # 用 anyio.to_thread 避免阻塞事件循环；同时计算 sha256（流式一次读完即弃）
    def _sync_write() -> tuple[int, str]:
        total = 0
        h = hashlib.sha256()
        with open(dest, "wb") as f:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                total += len(chunk)
                if total > _MAX_FILE_BYTES:
                    raise ValueError(f"单文件超过大小限制 {_MAX_FILE_BYTES} 字节")
        return total, h.hexdigest()

    try:
        size_written, content_sha256 = await anyio.to_thread.run_sync(_sync_write)
    finally:
        await file.close()
    return str(dest), size_written, content_sha256


async def _upload_to_minio(
    path: str,
    original_name: str,
    content_type: str,
    content_sha256: str,
    recorder: Any | None = None,
) -> dict:
    """把本地临时文件留存到 MinIO edu-upload，返回源文件元数据（object_key 等）。

    object_key 由 ``_make_minio_object_key`` 基于文件内容 sha256 派生，保证同名
    不同内容两次上传不会互相覆盖（T14 报告 P2 观察）；同名同内容两次上传若需严格
    幂等可由调用方对 (sha256) 做查重，这里保留两份独立对象作为源文件留存（W-NEXT-MINIO-001）。

    MinIO 不可用时降级：object_key=None + warn（不阻断上传主链路，但源文件留存不满足 30 天要求）。

    G0-HARDENING CMD-H1：``recorder``（request-scoped StorageCallRecorder）非空时，
    每次 MinIO 调用（成功或降级）真实记录为 storage side effect——shadow diff 的
    old_capture 由此获得真实存储面，替代旧的"恒空集"假设。
    """
    object_key = _make_minio_object_key(original_name, content_sha256)
    try:
        up = get_uploader().upload_file(
            path, object_key, content_type=content_type
        )
        if recorder is not None:
            recorder.record_storage(method="upload_file", object_key=up["object_key"],
                                    bucket="edu-upload", outcome="ok")
        return {
            "object_key": up["object_key"],
            "file_name": original_name,
            "file_size": up["size_bytes"],
            "content_type": content_type,
        }
    except Exception as exc:
        logger.warning(
            f"[task36] MinIO 源文件留存失败（任务仍跑，但不满足 30 天留存）：{exc}"
        )
        if recorder is not None:
            recorder.record_storage(method="upload_file", object_key=object_key,
                                    bucket="edu-upload", outcome="degraded",
                                    detail=f"{type(exc).__name__}: {exc}")
        return {
            "object_key": None,
            "file_name": original_name,
            "file_size": os.path.getsize(path) if os.path.exists(path) else 0,
            "content_type": content_type,
        }


def _write_task_names_cache(task_id: str, file_names: list[str]) -> None:
    """B0-FIX（P1-4 续）：legacy 上传任务不落 import_source_asset 行，任务列表要显示
    文件名 → 上传时刻把紧凑文件名写 Redis（持久，无 TTL）。写失败仅 WARN 不阻断。"""
    try:
        from app.database import get_redis
        get_redis().set(
            f"kb:task_names:{task_id}",
            json.dumps([{"file_name": n} for n in file_names], ensure_ascii=False),
        )
    except Exception as exc:  # noqa: BLE001 — 名字缓存属锦上添花，失败不影响任务
        logger.warning(f"[upload] task names cache 写入失败（不影响任务）：{exc!r}")


def select_document_parser(filename: str, requested: str) -> str:
    return 'mineru' if requested == 'auto' and settings.MINERU_ENABLED and Path(filename).suffix.lower() == '.pdf' else requested


async def _w3_worker_path_ready(source_files_meta: list[dict]) -> bool:
    """Fail closed unless the worker route has durable MinIO sources and live consumers."""
    typed_document = any(item.get("business_metadata", {}).get("parser_backend") in {'mineru','legacy_str'} for item in source_files_meta)
    if getattr(settings, "IMPORT_COMMAND_MODE", "legacy") != "primary" and not typed_document:
        return False
    if not source_files_meta or any(
        not (item.get("object_key") and item.get("sha256")) for item in source_files_meta
    ):
        return False
    try:
        from app.database import get_minio_client, get_redis
        client = get_minio_client()
        if not client.bucket_exists(settings.MINIO_BUCKET_UPLOAD):
            return False
        redis = get_redis()
        await redis.ping()
        names = ("parser-worker", "ingest-worker", "reconciler")
        for name in names:
            if not await redis.exists(f"worker:alive:{name}"):
                return False
        return True
    except Exception as exc:  # noqa: BLE001 — legacy pipeline is the documented fallback
        logger.warning("W3 worker route unavailable; selecting legacy import path: %s", exc)
        return False


async def _dispatch_w3_task(task_id: str) -> bool:
    """Dispatch durable source assets; false means reconcile/retry is still required."""
    try:
        await task_store.dispatch_pending_assets()
        assets = await task_store.get_source_assets(task_id)
    except Exception as exc:  # noqa: BLE001 — MySQL remains authoritative; leave task visible
        logger.exception("W3 durable dispatch failed for task=%s: %s", task_id, exc)
        return False
    return bool(assets) and all(
        item.get("stage") != "queued_parser"
        or item.get("dispatched_epoch") == item.get("execution_epoch")
        for item in assets
    )


async def _process_import(
    task_id: str,
    local_paths: list[str],
    original_names: list[str],
    tenant_id: str,
    visibility: Visibility,
    task_type: str,
    source_files_meta: list[dict] | None = None,
    owner_id: int | None = None,
):
    """后台执行真实 P1 导入管道，并回写双写层（MySQL + Redis）。

    W2-S5：新增 ``owner_id``（发起者 user_id，三入口均传）——与 visibility 一起
    供给 ImportState 安全元数据正式字段（W2-S4 parse_node fail-closed 依赖）。
    """
    await task_store.update_task(
        task_id=task_id, status="running", started_at=datetime.now()
    )
    try:
        # 1) 提前建 Milvus collection / partition（后续 load 节点会再 ensure，幂等）
        try:
            ensure_collection_exists()
            ensure_partition_exists(tenant_id)
        except Exception as exc:
            logger.warning(f"Milvus ensure 前置失败（load_node 仍会重试）：{exc}")

        # 2) 构建 ImportState
        state = ImportState(
            task_id=task_id,
            source_files=local_paths,
            tenant_id=tenant_id,
            task_type=task_type,
        )
        # 把 visibility / 默认元数据塞进 state.extra（解析/切分/入库节点按需取）
        state.__dict__.setdefault("extra", {})
        state.extra["visibility"] = visibility.value
        state.extra["original_names"] = original_names
        if source_files_meta:
            state.extra["source_files_meta"] = source_files_meta
        # W2-S4/S5：安全元数据正式字段同步供给（parse_node 双读依赖：正式字段
        # 优先，extra["visibility"] hack 过渡期保留，删除归 S5 后续清理或 W7）。
        # security_scope 保持模型默认 "default"（W2 无多安全域输入，正式字段已带）。
        state.visibility = visibility.value
        state.owner_id = owner_id

        # 3) 同步跑管道（封装到 anyio.to_thread 避免阻塞事件循环）
        def _run_pipe_sync() -> ImportState:
            return run_import_pipeline(state)

        result: ImportState = await anyio.to_thread.run_sync(_run_pipe_sync)

        # 4) 回写任务状态（done → 表词汇 succeeded）
        total = max(len(result.chunks), 0)
        imported = int(result.imported_count or 0)
        if result.error:
            await task_store.update_task(
                task_id=task_id,
                status="failed",
                error=result.error,
                total_chunks=total,
                imported_chunks=imported,
                finished_at=datetime.now(),
            )
        else:
            await task_store.update_task(
                task_id=task_id,
                status="done",  # 映射为 succeeded
                total_chunks=total,
                imported_chunks=imported,
                finished_at=datetime.now(),
            )

        logger.info(
            f"任务 {task_id} 完成: "
            f"导入 {imported}/{total} chunks "
            f"→ tenant={tenant_id}, visibility={visibility.value}, files={len(original_names)}"
        )
    except Exception as e:
        await task_store.update_task(
            task_id=task_id,
            status="failed",
            error=f"{e.__class__.__name__}: {e}",
            finished_at=datetime.now(),
        )
        logger.exception(f"任务 {task_id} 失败")
    finally:
        # 5) 清理本地临时文件（失败/成功都清，不想本地无限膨胀；MinIO 留存不动）
        _cleanup_paths(local_paths)


def _cleanup_paths(paths: list[str]) -> None:
    # 只允许删除落在 knowledge_uploads 根内的本地临时文件（纵深防御，防任意文件删除）；
    # 根外路径跳过，绝不对用户可控路径执行 os.remove
    allowed_root = (Path(settings.DATA_DIR) / "knowledge_uploads").resolve()
    for p in paths:
        try:
            if not p:
                continue
            resolved = Path(p).resolve()
            if not resolved.is_relative_to(allowed_root):
                continue
            if resolved.exists():
                os.remove(resolved)
        except Exception as exc:
            logger.debug(f"清理上传临时文件失败（忽略）：{p} -> {exc}")


# ============================================================
# 路由 1：用户上传私有知识（已登录学生/老师都可用）
# ============================================================
@router.post("/upload")
async def upload_knowledge(
    files: list[UploadFile] = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: CurrentUser = Depends(get_current_user),
):
    """用户上传私有知识。

    数据将存入 user_{user_id} Partition，仅该用户可见。
    大小限制：单文件 ≤ 200MB，仅接受 .md / .txt / .markdown / .pdf / .docx。
    """
    if not settings.KNOWLEDGE_UPLOADS_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="知识上传尚未开放；需等待 M0-B 生产化验收通过。",
        )
    _ensure_lifecycle_once()
    if not files:
        raise HTTPException(status_code=400, detail="请至少上传 1 个文件")
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="单次最多上传 20 个文件")

    # 1) 先校验后缀
    for f in files:
        suffix = Path(f.filename or "").suffix.lower()
        if suffix not in _ALLOWED_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型：{f.filename}，仅允许 {sorted(_ALLOWED_SUFFIXES)}",
            )

    # 2) 落本地临时文件 + 留存 MinIO edu-upload（30 天）+ 构建源文件元数据
    # G0-HARDENING CMD-H1：shadow 态挂 request-scoped recorder，真实捕获 storage 副作用
    from app.config import settings as _cmd_settings
    from app.knowledge.import_command import StorageCallRecorder
    _recorder = StorageCallRecorder(entry="upload_user") \
        if getattr(_cmd_settings, "IMPORT_COMMAND_MODE", "legacy") == "shadow" else None
    local_paths: list[str] = []
    original_names: list[str] = []
    source_files_meta: list[dict] = []
    try:
        for f in files:
            path, size, sha256 = await _write_upload_to_disk(f, current_user.user_id)
            local_paths.append(path)
            safe_name = _sanitize_filename(f.filename)
            original_names.append(safe_name)
            content_type = f.content_type or "application/octet-stream"
            meta = await _upload_to_minio(path, safe_name, content_type, sha256,
                                          recorder=_recorder)
            meta["file_size"] = meta.get("file_size") or size
            # W2-S5：sha256 随源文件元数据透传（primary 态 Command 据此落 asset 行）
            meta["sha256"] = sha256
            source_files_meta.append(meta)
    except ValueError as exc:
        _cleanup_paths(local_paths)
        raise HTTPException(status_code=413, detail=str(exc))
    except Exception as exc:
        _cleanup_paths(local_paths)
        raise HTTPException(status_code=500, detail=f"文件落盘失败：{exc}")

    # 3) 创建任务（双写：MySQL 真相源 + Redis 热缓存）
    # W2-S5 四态机 primary 切换：primary 走 ImportCommand 真实执行体
    # （task+asset+document_id 统一收敛，异常上抛 → HTTP 500 正式路径语义）；
    # legacy/shadow 保留入口直调 fallback（W7 cleanup 删）。
    task_id = f"task_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    tenant_id = _user_tenant_id(current_user.user_id)
    visibility = Visibility.PRIVATE
    configured_mode = getattr(settings, "IMPORT_COMMAND_MODE", "legacy")
    use_w3_workers = await _w3_worker_path_ready(source_files_meta)
    command_mode = "primary" if use_w3_workers else ("shadow" if configured_mode == "shadow" else "legacy")
    from app.knowledge.import_command import ImportCommand
    task = await ImportCommand(mode=command_mode).create_import_task(
        task_id=task_id,
        task_type="user_upload",
        tenant_id=tenant_id,
        visibility=visibility.value,
        source_files_meta=source_files_meta,
        total_chunks=len(files) * 20,  # 粗估，跑完管道会回写真实值
        user_id=current_user.user_id,
    )
    _write_task_names_cache(task_id, original_names)

    # G0-CMD shadow hook (v2.5 §1.1)：legacy 态零开销直返；shadow 态 dry-run diff 落报告
    # G0-HARDENING CMD-H1：old_capture=recorder 真实捕获（含 MinIO 成功/降级事实）
    from app.knowledge.import_command import shadow_hook
    shadow_hook({
        "entry": "upload_user", "role": "user", "user_id": current_user.user_id,
        "legacy_task": task, "task_id": task_id, "task_type": "user_upload",
        "tenant_id": tenant_id, "visibility": visibility.value,
        "source_files_meta": source_files_meta, "total_chunks": len(files) * 20,
        "old_capture": ({"storage_effects": _recorder.snapshot(),
                         "metadata_effects": {},
                         "event_effects": {"known_trigger_points": 0, "fired": []},
                         "permission_effects": {}}
                        if _recorder is not None else None),
    })

    # W3 primary: MySQL asset rows + parser/ingest workers are the only write path.
    # Fallback: retain the existing local pipeline when storage/Redis/workers are unavailable.
    if use_w3_workers:
        dispatched = await _dispatch_w3_task(task_id)
        _cleanup_paths(local_paths)
        message = ("文件已进入 Parser→Ingest Worker 队列" if dispatched else
                   "源文件已保存在 MinIO；队列投递待 Reconciler 重试")
    else:
        background_tasks.add_task(
            _process_import,
            task_id=task_id,
            local_paths=local_paths,
            original_names=original_names,
            tenant_id=tenant_id,
            visibility=visibility,
            task_type="user_upload",
            source_files_meta=source_files_meta,
            owner_id=current_user.user_id,
        )
        message = "文件已接收，正在后台执行本地导入管道"

    logger.info(f"用户 {current_user.user_id} 上传 {len(files)} 个私有文件，任务 ID: {task_id}")

    return ok(data={
        "task_id": task_id,
        "status": "pending",
        "message": message,
        "tenant_id": tenant_id,
        "visibility": visibility.value,
    })


# ============================================================
# 路由 2：管理员上传公共知识（RBAC 强校验）
# ============================================================
@router.post("/admin/upload")
async def admin_upload_knowledge(
    files: list[UploadFile] = File(...),
    parser_backend: Annotated[str, Form()] = "auto",
    ocr_mode: Annotated[str, Form()] = "auto",
    background_tasks: BackgroundTasks = BackgroundTasks(),
    _admin: CurrentUser = Depends(require_role([UserRole.ADMIN, UserRole.MANAGER])),
):
    """管理员上传公共知识（仅 admin / manager）。

    数据将存入 `_default` Partition，所有登录用户在 RAG 中可见。
    """
    if not settings.KNOWLEDGE_UPLOADS_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="知识上传尚未开放；Pilot 只消费管理员预装的冻结课程包。",
        )
    _ensure_lifecycle_once()
    if not files:
        raise HTTPException(status_code=400, detail="请至少上传 1 个文件")
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="管理员单次最多上传 50 个文件")
    if parser_backend not in {"auto", "mineru"} or ocr_mode not in {"auto", "txt", "ocr"}:
        raise HTTPException(status_code=400, detail="解析器或 OCR 模式无效")
    if parser_backend == "mineru":
        if not settings.MINERU_ENABLED or not Path(settings.MINERU_EXECUTABLE).is_file():
            raise HTTPException(status_code=503, detail="MinerU 本地运行环境尚未就绪")
        if any(Path(f.filename or "").suffix.lower() != ".pdf" for f in files):
            raise HTTPException(status_code=400, detail="MinerU 当前入口只接受 PDF")
    if parser_backend == 'auto' and any(select_document_parser(f.filename or '',parser_backend)=='mineru' for f in files) and not Path(settings.MINERU_EXECUTABLE).is_file():
        raise HTTPException(status_code=503,detail='PDF 自动选择 MinerU，但本地运行环境不可用')

    for f in files:
        suffix = Path(f.filename or "").suffix.lower()
        if suffix not in _ALLOWED_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型：{f.filename}，仅允许 {sorted(_ALLOWED_SUFFIXES)}",
            )

    local_paths: list[str] = []
    original_names: list[str] = []
    source_files_meta: list[dict] = []
    # G0-HARDENING CMD-H1：shadow 态挂 request-scoped recorder（admin 入口）
    from app.config import settings as _cmd_settings_admin
    from app.knowledge.import_command import StorageCallRecorder
    _recorder_admin = StorageCallRecorder(entry="upload_admin") \
        if getattr(_cmd_settings_admin, "IMPORT_COMMAND_MODE", "legacy") == "shadow" else None
    try:
        for f in files:
            path, size, sha256 = await _write_upload_to_disk(f, _admin.user_id)
            local_paths.append(path)
            safe_name = _sanitize_filename(f.filename)
            original_names.append(safe_name)
            content_type = f.content_type or "application/octet-stream"
            meta = await _upload_to_minio(path, safe_name, content_type, sha256,
                                          recorder=_recorder_admin)
            meta["file_size"] = meta.get("file_size") or size
            # W2-S5：sha256 随源文件元数据透传（primary 态 Command 据此落 asset 行）
            meta["sha256"] = sha256
            selected_parser = select_document_parser(safe_name, parser_backend)
            if selected_parser == "mineru":
                meta["business_metadata"] = {"parser_backend": "mineru", "mineru_ocr_mode": ocr_mode}
            else:
                meta['business_metadata']={'parser_backend':'legacy_str'}
            source_files_meta.append(meta)
    except ValueError as exc:
        _cleanup_paths(local_paths)
        raise HTTPException(status_code=413, detail=str(exc))
    except Exception as exc:
        _cleanup_paths(local_paths)
        raise HTTPException(status_code=500, detail=f"文件落盘失败：{exc}")

    # W2-S5 四态机 primary 切换：primary 走 ImportCommand 真实执行体；
    # legacy/shadow 保留入口直调 fallback（W7 cleanup 删）。
    task_id = f"task_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    tenant_id = "_default"
    visibility = Visibility.PUBLIC
    configured_mode = getattr(settings, "IMPORT_COMMAND_MODE", "legacy")
    use_w3_workers = await _w3_worker_path_ready(source_files_meta)
    if not use_w3_workers:
        _cleanup_paths(local_paths)
        raise HTTPException(status_code=503, detail="资料解析所需 Parser/Ingest/Reconciler 尚未在线；未创建导入任务，请运行一键启动后重试")
    command_mode = "primary" if use_w3_workers else ("shadow" if configured_mode == "shadow" else "legacy")
    from app.knowledge.import_command import ImportCommand
    task = await ImportCommand(mode=command_mode).create_import_task(
        task_id=task_id,
        task_type="system_init",
        tenant_id=tenant_id,
        visibility=visibility.value,
        source_files_meta=source_files_meta,
        total_chunks=len(files) * 20,
        user_id=_admin.user_id,
    )

    # G0-CMD shadow hook (v2.5 §1.1)：legacy 态零开销直返；shadow 态 dry-run diff 落报告
    # G0-HARDENING CMD-H1：old_capture=recorder 真实捕获
    from app.knowledge.import_command import shadow_hook
    shadow_hook({
        "entry": "upload_admin", "role": "admin", "user_id": _admin.user_id,
        "legacy_task": task, "task_id": task_id, "task_type": "system_init",
        "tenant_id": tenant_id, "visibility": visibility.value,
        "source_files_meta": source_files_meta, "total_chunks": len(files) * 20,
        "old_capture": ({"storage_effects": _recorder_admin.snapshot(),
                         "metadata_effects": {},
                         "event_effects": {"known_trigger_points": 0, "fired": []},
                         "permission_effects": {}}
                        if _recorder_admin is not None else None),
    })
    _write_task_names_cache(task_id, original_names)

    if use_w3_workers:
        dispatched = await _dispatch_w3_task(task_id)
        _cleanup_paths(local_paths)
        message = ("文件已进入 Parser→Ingest Worker 队列" if dispatched else
                   "源文件已保存在 MinIO；队列投递待 Reconciler 重试")
    else:
        background_tasks.add_task(
            _process_import,
            task_id=task_id,
            local_paths=local_paths,
            original_names=original_names,
            tenant_id=tenant_id,
            visibility=visibility,
            task_type="system_init",
            source_files_meta=source_files_meta,
            owner_id=_admin.user_id,
        )
        message = "公共知识已接收，正在后台执行本地导入管道"

    logger.info(f"管理员 {_admin.user_id} 上传 {len(files)} 个公共文件，任务 ID: {task_id}")

    return ok(data={
        "task_id": task_id,
        "status": "pending",
        "message": message,
        "tenant_id": tenant_id,
        "visibility": visibility.value,
    })


# ============================================================
# 路由 3：分页倒序查询导入任务（task36 新增，契约⑥，管理员）
# ============================================================
@router.get("/tasks")
async def list_knowledge_tasks(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    _admin: CurrentUser = Depends(require_role([UserRole.ADMIN, UserRole.MANAGER])),
):
    """分页倒序查询知识导入任务（管理员）。

    契约⑥（task36 冻结）：
    - query: page(≥1, 默认1) / page_size(1~100, 默认20) / status(可选 pending|running|succeeded|failed)
    - 返回 ok({items, total, page, page_size, total_pages})
    - items 元素字段：task_id, task_type, tenant_id, visibility, status,
      total_chunks, imported_chunks, source_files[], error, created_at, started_at, finished_at
    - RBAC 仅 admin/manager
    - status 词汇统一为表词汇：pending / running / succeeded / failed

    W2-S6 additive（向后兼容，既有键语义不变）：items 每项新增 ``stage``
    （列表轻量投影：批量一次聚合查询；无 asset 行回退 status 映射；不加
    asset_progress 明细）。前端轮询 consumer 对新增键可忽略。
    """
    result = await task_store.list_tasks(
        page=page, page_size=page_size, status=status
    )
    # W2-S6 additive：轻量 stage 投影（聚合失败降级为 status 回退映射，不破坏旧契约）
    items = result.get("items") or []
    stage_map: dict[str, str] = {}
    if items:
        try:
            stage_map = await task_store.get_stage_by_task_ids(
                [it.get("task_id") for it in items]
            )
        except Exception as exc:
            logger.warning(f"[W2-S6] list stage 批量聚合失败（回退 status 映射）：{exc!r}")
    for it in items:
        it["stage"] = stage_map.get(it.get("task_id")) or task_store.stage_from_status(
            it.get("status")
        )
    return ok(data=result)


@router.get("/status/{task_id}")
async def get_task_status(
    task_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """查询导入任务状态。

    W0-① 所有权校验：管理员（admin/manager）可查任意任务；普通用户只能查自己
    发起的任务（user_id 与当前登录用户一致）。非本人且非管理员的查询一律 404
    （不暴露任务存在性）。``user_id`` 为 NULL 的存量遗留任务保持现状可查。

    W2-S6 additive 投影（只增不改，旧四态字段语义不变）：
    - ``stage``：task 级阶段（task_store 附录 §2 冻结映射；无 asset 行回退 status 映射）；
    - ``asset_progress``：仅当 task 有 asset 行（无行省略该键——禁止伪造空进度）；
    - ``artifact_status``：每 asset 的 parse_fingerprint+artifact_ref 摘要
      （null=not-produced，诚实表达不造假值）；
    - ``asset_runtime_status``：每 asset 的 ID/stage/epoch/lease 与 vector/graph 状态，
      供旧任务详情页与 worker 日志按 task_id/asset_id/epoch 关联；
    - ``vector_status`` / ``graph_status``：本 Wave 无真实 producer，固定
      按 asset 真值聚合；没有对应 asset producer 时为 "not-produced"。
    additive 块整体降级：投影查询异常只省略新增键，绝不破坏旧契约。
    """
    # B0-FIX（P1-4 大行地雷排除）：状态面剔除 source_files 大列——uvicorn（Proactor）
    # 读取数百 KB 多包行会触发 asyncmy BufferError；键保留置 null（契约形状不变）。
    task = await task_store.get_task(task_id, include_source_files=False)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    # W0-①（final 裁定收紧为 fail-closed）：非 admin/manager 用户只能查自己发起的任务。
    # NULL user_id 一律 404——不做"legacy 公开例外"（旧口径会让 MCP/历史 NULL 任务
    # 对全体学生永久可查，与 task_store docstring"仅 admin 面"声明直接矛盾）。
    # 存量 NULL 行兼容走一次性 backfill（owner 裁定数据面），不在查询层开口子。
    owner_id = task.get("user_id")
    is_privileged = current_user.role in (UserRole.ADMIN, UserRole.MANAGER)
    if not is_privileged and owner_id != current_user.user_id:
        # 404 而非 403：不向非归属者暴露任务存在性（含 owner_id 为 NULL 的任务）
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    # W2-S6 additive 投影：浅拷贝（get_task 可能命中 Redis 缓存对象，禁止原地改写）
    data = dict(task)
    try:
        assets = await task_store.get_source_assets(task_id)
        data["stage"] = await task_store.get_task_stage(task, assets=assets)
        if assets:
            data["asset_progress"] = task_store.aggregate_progress(assets)
            data["artifact_status"] = task_store.artifact_status_of(assets)
            data["asset_runtime_status"] = task_store.asset_runtime_status_of(assets)
        data["vector_status"] = task_store.aggregate_producer_status(assets, "vector_status")
        data["graph_status"] = task_store.aggregate_producer_status(assets, "graph_status")
    except Exception as exc:
        # additive 失败不影响旧四态 API（投影是纯读，失败仅省略新增键）
        logger.warning(f"[W2-S6] status additive 投影失败（省略新增键）：{task_id} -> {exc!r}")

    return ok(data=data)


@router.get("/partitions")
async def list_partitions(
    _admin: CurrentUser = Depends(require_role([UserRole.ADMIN, UserRole.MANAGER])),
):
    """查询所有 Partition（管理员功能）。

    task04 修正轮 2：list_all_partitions 是同步 Milvus I/O（不可达时连接超时最长
    10s），async 路由直接调用会阻塞整个事件循环 → 移入线程池 + 5s 硬上限。
    """
    try:
        partitions = await asyncio.wait_for(
            anyio.to_thread.run_sync(list_all_partitions),
            timeout=5.0,
        )
        return {
            "total_partitions": len(partitions),
            "partitions": partitions
        }
    except asyncio.TimeoutError:
        # T19-3（reshape-b）：50300「Milvus 不可达」直泄 → 50301 + 用户化 message；
        # 原始异常（含堆栈）仅入日志，HTTP 503 语义不变。
        logger.exception("查询分区超时（Milvus 不可达）——原始异常仅入日志，响应脱敏为 50301")
        raise DependencyUnavailableError(http_status=503) from None
    except Exception as e:
        # T19-3：原 f"查询失败: {e}" 直泄 str(e)（pymilvus 类名/host 等）→ 50301 脱敏；
        # HTTP 500 语义不变，原始异常入日志。
        logger.exception("查询分区失败（Milvus 依赖侧异常）——原始异常仅入日志，响应脱敏为 50301")
        raise DependencyUnavailableError(http_status=500) from e


@router.delete("/partitions/{tenant_id}")
async def delete_partition(
    tenant_id: str,
    _admin: CurrentUser = Depends(require_role([UserRole.ADMIN, UserRole.MANAGER])),
):
    """删除指定 Partition（管理员功能）。"""
    if tenant_id == "_default":
        raise HTTPException(status_code=400, detail="不能删除默认分区")

    try:
        success = drop_partition(tenant_id)
        if success:
            return {"message": f"Partition for tenant '{tenant_id}' 已删除"}
        raise HTTPException(status_code=404, detail=f"Partition for tenant '{tenant_id}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        # T19-3：原 f"删除失败: {e}" 直泄 str(e) → 50301 脱敏；HTTP 500 语义不变。
        logger.exception("删除分区失败（Milvus 依赖侧异常）——原始异常仅入日志，响应脱敏为 50301")
        raise DependencyUnavailableError(http_status=500) from e
