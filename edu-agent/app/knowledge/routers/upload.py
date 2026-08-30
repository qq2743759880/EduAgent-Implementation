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

import os
import time
import uuid
from datetime import datetime
from pathlib import Path

import anyio
import asyncio
from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks, HTTPException
from loguru import logger

from app.auth import require_role, UserRole, get_current_user
from app.auth.dependencies import CurrentUser
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


def _user_tenant_id(user_id: int | str) -> str:
    return f"user_{user_id}"


async def _write_upload_to_disk(file: UploadFile) -> tuple[str, int]:
    """
    把 UploadFile 同步写磁盘（FastAPI UploadFile 是 SpooledTemporaryFile，需要读出来）。
    返回 (absolute_path, bytes_written)。
    """
    upload_dir = _resolve_upload_dir()
    safe_name = _sanitize_filename(file.filename)
    ext = Path(safe_name).suffix.lower()
    unique = f"{uuid.uuid4().hex[:12]}{ext}"
    dest = upload_dir / unique

    size_written = 0
    # 用 anyio.to_thread 避免阻塞事件循环
    def _sync_write() -> int:
        total = 0
        with open(dest, "wb") as f:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                total += len(chunk)
                if total > _MAX_FILE_BYTES:
                    raise ValueError(f"单文件超过大小限制 {_MAX_FILE_BYTES} 字节")
        return total

    try:
        size_written = await anyio.to_thread.run_sync(_sync_write)
    finally:
        await file.close()
    return str(dest), size_written


async def _upload_to_minio(path: str, original_name: str, content_type: str) -> dict:
    """把本地临时文件留存到 MinIO edu-upload，返回源文件元数据（object_key 等）。

    MinIO 不可用时降级：object_key=None + warn（不阻断上传主链路，但源文件留存不满足 30 天要求）。
    """
    try:
        up = get_uploader().upload_file(path, original_name, content_type=content_type)
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
        return {
            "object_key": None,
            "file_name": original_name,
            "file_size": os.path.getsize(path) if os.path.exists(path) else 0,
            "content_type": content_type,
        }


async def _process_import(
    task_id: str,
    local_paths: list[str],
    original_names: list[str],
    tenant_id: str,
    visibility: Visibility,
    task_type: str,
    source_files_meta: list[dict] | None = None,
):
    """后台执行真实 P1 导入管道，并回写双写层（MySQL + Redis）。"""
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
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
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
    local_paths: list[str] = []
    original_names: list[str] = []
    source_files_meta: list[dict] = []
    try:
        for f in files:
            path, size = await _write_upload_to_disk(f)
            local_paths.append(path)
            safe_name = _sanitize_filename(f.filename)
            original_names.append(safe_name)
            content_type = f.content_type or "application/octet-stream"
            meta = await _upload_to_minio(path, safe_name, content_type)
            meta["file_size"] = meta.get("file_size") or size
            source_files_meta.append(meta)
    except ValueError as exc:
        _cleanup_paths(local_paths)
        raise HTTPException(status_code=413, detail=str(exc))
    except Exception as exc:
        _cleanup_paths(local_paths)
        raise HTTPException(status_code=500, detail=f"文件落盘失败：{exc}")

    # 3) 创建任务（双写：MySQL 真相源 + Redis 热缓存）
    task_id = f"task_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    tenant_id = _user_tenant_id(current_user.user_id)
    visibility = Visibility.PRIVATE
    task = await task_store.create_task(
        task_id=task_id,
        task_type="user_upload",
        tenant_id=tenant_id,
        visibility=visibility.value,
        source_files_meta=source_files_meta,
        total_chunks=len(files) * 20,  # 粗估，跑完管道会回写真实值
    )

    # 4) 后台执行管道
    background_tasks.add_task(
        _process_import,
        task_id=task_id,
        local_paths=local_paths,
        original_names=original_names,
        tenant_id=tenant_id,
        visibility=visibility,
        task_type="user_upload",
        source_files_meta=source_files_meta,
    )

    logger.info(f"用户 {current_user.user_id} 上传 {len(files)} 个私有文件，任务 ID: {task_id}")

    return ok(data={
        "task_id": task_id,
        "status": "pending",
        "message": "文件已接收，正在后台执行 parse→chunk→embed→load→graph_build 全流程",
        "tenant_id": tenant_id,
        "visibility": visibility.value,
    })


# ============================================================
# 路由 2：管理员上传公共知识（RBAC 强校验）
# ============================================================
@router.post("/admin/upload")
async def admin_upload_knowledge(
    files: list[UploadFile] = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    _admin: CurrentUser = Depends(require_role([UserRole.ADMIN, UserRole.MANAGER])),
):
    """管理员上传公共知识（仅 admin / manager）。

    数据将存入 `_default` Partition，所有登录用户在 RAG 中可见。
    """
    _ensure_lifecycle_once()
    if not files:
        raise HTTPException(status_code=400, detail="请至少上传 1 个文件")
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="管理员单次最多上传 50 个文件")

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
    try:
        for f in files:
            path, size = await _write_upload_to_disk(f)
            local_paths.append(path)
            safe_name = _sanitize_filename(f.filename)
            original_names.append(safe_name)
            content_type = f.content_type or "application/octet-stream"
            meta = await _upload_to_minio(path, safe_name, content_type)
            meta["file_size"] = meta.get("file_size") or size
            source_files_meta.append(meta)
    except ValueError as exc:
        _cleanup_paths(local_paths)
        raise HTTPException(status_code=413, detail=str(exc))
    except Exception as exc:
        _cleanup_paths(local_paths)
        raise HTTPException(status_code=500, detail=f"文件落盘失败：{exc}")

    task_id = f"task_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    tenant_id = "_default"
    visibility = Visibility.PUBLIC
    task = await task_store.create_task(
        task_id=task_id,
        task_type="system_init",
        tenant_id=tenant_id,
        visibility=visibility.value,
        source_files_meta=source_files_meta,
        total_chunks=len(files) * 20,
    )

    background_tasks.add_task(
        _process_import,
        task_id=task_id,
        local_paths=local_paths,
        original_names=original_names,
        tenant_id=tenant_id,
        visibility=visibility,
        task_type="system_init",
        source_files_meta=source_files_meta,
    )

    logger.info(f"管理员 {_admin.user_id} 上传 {len(files)} 个公共文件，任务 ID: {task_id}")

    return ok(data={
        "task_id": task_id,
        "status": "pending",
        "message": "公共知识已接收，正在后台导入",
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
    """
    result = await task_store.list_tasks(
        page=page, page_size=page_size, status=status
    )
    return ok(data=result)


@router.get("/status/{task_id}")
async def get_task_status(
    task_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """查询导入任务状态。

    管理员可查任意任务；普通用户只能查自己发起的（task_store 里没有 user_id 字段 → 先放宽可查，生产加字段）。
    """
    task = await task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    return ok(data=task)


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
        logger.error("查询分区超时（Milvus 不可达），返回 503")
        raise HTTPException(status_code=503, detail="Milvus 不可达，查询分区超时")
    except Exception as e:
        logger.error(f"查询分区失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")


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
        logger.error(f"删除分区失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")
