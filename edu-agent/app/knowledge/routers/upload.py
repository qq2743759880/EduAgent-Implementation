"""
知识库上传路由 - 支持多租户文件上传（P1 步骤 9）

API 端点:
- POST /api/knowledge/upload        : 用户上传私有知识 → BackgroundTasks 跑 P1 pipeline(5 节点)
- POST /api/knowledge/admin/upload  : 管理员上传公共知识（RBAC 强制 require_role(admin/manager)）
- GET  /api/knowledge/status/{task_id} : 查询任务状态
- GET  /api/knowledge/partitions    : 查询所有分区（管理员）
- DELETE /api/knowledge/partitions/{tenant_id} : 删除指定分区（管理员）

P1 pipeline 流程：parse → chunk → embed → load(Milvus) → graph_build(Neo4j)
"""

import os
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import anyio
import asyncio
from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks, HTTPException, Header
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
from app.knowledge.models import ImportTask, ImportState, KnowledgeChunk, Visibility

router = APIRouter(prefix="/api/knowledge", tags=["知识库管理"])

# 全局任务状态存储（后续可替换成 Redis / MongoDB）
task_store: dict[str, ImportTask] = {}

# 允许的最大单文件大小：200MB（课件 PDF/课程介绍 Markdown 够了；视频走 MinIO 独立接口）
_MAX_FILE_BYTES = 200 * 1024 * 1024
_ALLOWED_SUFFIXES = {".md", ".txt", ".markdown", ".pdf", ".docx"}


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


async def _process_import(
    task_id: str,
    local_paths: list[str],
    original_names: list[str],
    tenant_id: str,
    visibility: Visibility,
    task_type: str,
    default_metadata: dict | None = None,
):
    """后台执行真实 P1 导入管道。"""
    task = task_store.get(task_id)
    if not task:
        # 任务记录丢失 → 至少清理文件
        _cleanup_paths(local_paths)
        return

    try:
        task.status = "running"
        task.started_at = datetime.now()
        task.source_files = original_names

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
        if default_metadata:
            state.extra["default_metadata"] = default_metadata

        # 3) 同步跑管道（封装到 anyio.to_thread 避免阻塞事件循环）
        def _run_pipe_sync() -> ImportState:
            return run_import_pipeline(state)

        result: ImportState = await anyio.to_thread.run_sync(_run_pipe_sync)

        # 4) 回写任务状态
        task.total_chunks = max(len(result.chunks), task.total_chunks or 0)
        task.imported_chunks = int(result.imported_count or 0)
        if result.error:
            task.status = "failed"
            task.error = result.error
        else:
            task.status = "done"
        task.finished_at = datetime.now()

        logger.info(
            f"任务 {task_id} {task.status}: "
            f"导入 {task.imported_chunks}/{task.total_chunks} chunks "
            f"→ tenant={tenant_id}, visibility={visibility.value}, files={len(original_names)}"
        )
    except Exception as e:
        task.status = "failed"
        task.error = f"{e.__class__.__name__}: {e}"
        task.finished_at = datetime.now()
        logger.exception(f"任务 {task_id} 失败")
    finally:
        # 5) 清理临时文件（失败/成功都清，不想本地无限膨胀）
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

    # 2) 写本地临时文件（后台进程读磁盘更稳，不依赖 UploadFile 生命周期）
    local_paths: list[str] = []
    original_names: list[str] = []
    try:
        for f in files:
            path, size = await _write_upload_to_disk(f)
            local_paths.append(path)
            original_names.append(_sanitize_filename(f.filename))
    except ValueError as exc:
        _cleanup_paths(local_paths)
        raise HTTPException(status_code=413, detail=str(exc))
    except Exception as exc:
        _cleanup_paths(local_paths)
        raise HTTPException(status_code=500, detail=f"文件落盘失败：{exc}")

    # 3) 创建任务
    task_id = f"task_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    tenant_id = _user_tenant_id(current_user.user_id)
    visibility = Visibility.PRIVATE
    task = ImportTask(
        task_id=task_id,
        status="pending",
        total_chunks=len(files) * 20,  # 粗估，跑完管道会回写真实值
        source_files=original_names,
    )
    task_store[task_id] = task

    # 4) 后台执行管道
    background_tasks.add_task(
        _process_import,
        task_id=task_id,
        local_paths=local_paths,
        original_names=original_names,
        tenant_id=tenant_id,
        visibility=visibility,
        task_type="user_upload",
    )

    logger.info(f"用户 {current_user.user_id} 上传 {len(files)} 个私有文件，任务 ID: {task_id}")

    return {
        "task_id": task_id,
        "status": "pending",
        "message": "文件已接收，正在后台执行 parse→chunk→embed→load→graph_build 全流程",
        "tenant_id": tenant_id,
        "visibility": visibility.value,
    }


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
    try:
        for f in files:
            path, size = await _write_upload_to_disk(f)
            local_paths.append(path)
            original_names.append(_sanitize_filename(f.filename))
    except ValueError as exc:
        _cleanup_paths(local_paths)
        raise HTTPException(status_code=413, detail=str(exc))
    except Exception as exc:
        _cleanup_paths(local_paths)
        raise HTTPException(status_code=500, detail=f"文件落盘失败：{exc}")

    task_id = f"task_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    tenant_id = "_default"
    visibility = Visibility.PUBLIC
    task = ImportTask(
        task_id=task_id,
        status="pending",
        total_chunks=len(files) * 20,
        source_files=original_names,
    )
    task_store[task_id] = task

    background_tasks.add_task(
        _process_import,
        task_id=task_id,
        local_paths=local_paths,
        original_names=original_names,
        tenant_id=tenant_id,
        visibility=visibility,
        task_type="system_init",
    )

    logger.info(f"管理员 {_admin.user_id} 上传 {len(files)} 个公共文件，任务 ID: {task_id}")

    return {
        "task_id": task_id,
        "status": "pending",
        "message": "公共知识已接收，正在后台导入",
        "tenant_id": tenant_id,
        "visibility": visibility.value,
    }


@router.get("/status/{task_id}")
async def get_task_status(
    task_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """查询导入任务状态。

    管理员可查任意任务；普通用户只能查自己发起的（task_store 里没有 user_id 字段 → 先放宽可查，生产加字段）。
    """
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    result = {
        "task_id": task.task_id,
        "status": task.status,
        "total_chunks": task.total_chunks,
        "imported_chunks": task.imported_chunks,
        "error": task.error,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "source_files": task.source_files,
    }
    # 管理员多看一点（目前没 owner 字段就先和学生一致）
    return result


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
