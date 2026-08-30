"""
RAG 导入任务双写层（task36）。

双写策略（tech-source-audit.md §四 + task36 验收标准）：
- MySQL `knowledge_import_task` 表：持久真相源 + 对账 + 分页列表（重启不丢）
- Redis `edu:knowledge:task:{task_id}`：TTL 24h 热缓存（进程重启恢复 + 快读）

降级语义：
- Redis 不可用时（熔断 / 连接失败 / 未初始化）经 `redis_run` 抛
  `DependencyUnavailableError`（或 get_redis() 抛 RuntimeError），本层**吞掉**并仅落
  MySQL，绝不阻断上传主链路。MySQL 是真相源，Redis 仅为加速层。
- 读取时 get_task 先查 Redis，miss / 解析失败 / 异常一律回退 MySQL，并回填缓存。

状态词汇（统一为表词汇，避免 done/succeeded 混淆）：
- 表/API 状态：pending / running / succeeded / failed
- 旧 ImportTask 模型用 done，本层提供 _MODEL_TO_DB_STATUS / _DB_TO_MODEL_STATUS 映射
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from loguru import logger

from app.config import settings
from app.core.db_resilience import DependencyUnavailableError, redis_run
from app.database import execute_write, fetch_all, fetch_one, get_redis

# ============================ 常量 ============================
_REDIS_KEY_PREFIX = "edu:knowledge:task:"
_REDIS_TTL_SECONDS = 24 * 3600  # 24h（GWT②）

# 表状态词汇（持久化 / API 统一）
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"

# 旧模型 status（done）↔ 表 status（succeeded）映射
_MODEL_TO_DB_STATUS = {
    "pending": "pending",
    "running": "running",
    "done": "succeeded",
    "succeeded": "succeeded",
    "failed": "failed",
}
_DB_TO_MODEL_STATUS = {
    "pending": "pending",
    "running": "running",
    "succeeded": "done",
    "failed": "failed",
}

_TABLE = "knowledge_import_task"
_COLUMNS = (
    "id, task_id, task_type, tenant_id, visibility, status, "
    "total_chunks, imported_chunks, source_files, error, "
    "created_at, started_at, finished_at"
)


# ============================ 工具 ============================
def _serialize_dt(dt: Any) -> Optional[str]:
    """datetime → ISO 字符串（秒精度）；None/非法值安全处理。"""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat(timespec="seconds")
    if isinstance(dt, str):
        return dt
    return str(dt)


def _to_db_status(status: Optional[str]) -> Optional[str]:
    """把任意模型/表状态归一为表词汇。"""
    if not status:
        return None
    return _MODEL_TO_DB_STATUS.get(status, status)


def _row_to_dict(row: dict) -> dict:
    """把 MySQL 行（dict）归一化为对外任务 dict（JSON 安全、状态用表词汇）。"""
    raw_source = row.get("source_files")
    if isinstance(raw_source, str):
        try:
            source_files = json.loads(raw_source) or []
        except (json.JSONDecodeError, TypeError):
            source_files = []
    elif isinstance(raw_source, list):
        source_files = raw_source
    else:
        source_files = []

    return {
        "task_id": row.get("task_id"),
        "task_type": row.get("task_type"),
        "tenant_id": row.get("tenant_id"),
        "visibility": row.get("visibility"),
        "status": row.get("status"),  # 已是表词汇
        "total_chunks": int(row.get("total_chunks") or 0),
        "imported_chunks": int(row.get("imported_chunks") or 0),
        "source_files": source_files,
        "error": row.get("error"),
        "created_at": _serialize_dt(row.get("created_at")),
        "started_at": _serialize_dt(row.get("started_at")),
        "finished_at": _serialize_dt(row.get("finished_at")),
    }


async def _safe_redis(op_name: str, coro_fn):
    """带降级的 Redis 操作包装：任何 Redis 故障都不影响主链路，仅返回 None。"""
    try:
        return await redis_run(op_name, coro_fn)
    except DependencyUnavailableError:
        # 熔断 / 不可用 → 直接降级
        logger.debug(f"[task_store] Redis 降级（{op_name}）：依赖不可用，仅用 MySQL")
        return None
    except Exception as exc:  # get_redis() 未初始化 RuntimeError / 连接异常等
        logger.warning(f"[task_store] Redis 操作 {op_name} 失败（降级 MySQL）：{exc!r}")
        return None


def _cache_key(task_id: str) -> str:
    return f"{_REDIS_KEY_PREFIX}{task_id}"


async def _write_cache(task_id: str, task: dict) -> None:
    payload = json.dumps(task, ensure_ascii=False)
    await _safe_redis(
        "task_cache_set",
        lambda: get_redis().set(_cache_key(task_id), payload, ex=_REDIS_TTL_SECONDS),
    )


async def _delete_cache(task_id: str) -> None:
    await _safe_redis("task_cache_del", lambda: get_redis().delete(_cache_key(task_id)))


async def _refresh_cache(task_id: str) -> None:
    """从 MySQL 重读并回写 Redis 缓存（保证缓存与真相源一致）。"""
    row = await fetch_one(
        f"SELECT {_COLUMNS} FROM {_TABLE} WHERE task_id = %s", (task_id,)
    )
    if not row:
        await _delete_cache(task_id)
        return
    await _write_cache(task_id, _row_to_dict(row))


# ============================ 写操作 ============================
async def create_task(
    *,
    task_id: str,
    task_type: str,
    tenant_id: str,
    visibility: str,
    source_files_meta: list[dict],
    total_chunks: int = 0,
) -> dict:
    """创建导入任务：先落 MySQL（真相源），再写 Redis 缓存。

    source_files_meta 结构：[{object_key, file_name, file_size, content_type}, ...]
    object_key 即 MinIO edu-upload 的 key（30 天生命周期留存）。
    """
    source_json = json.dumps(source_files_meta or [], ensure_ascii=False)
    status = STATUS_PENDING
    await execute_write(
        f"INSERT INTO {_TABLE} "
        "(task_id, task_type, tenant_id, visibility, status, total_chunks, source_files, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())",
        (task_id, task_type, tenant_id, visibility, status, total_chunks, source_json),
    )
    task = {
        "task_id": task_id,
        "task_type": task_type,
        "tenant_id": tenant_id,
        "visibility": visibility,
        "status": status,
        "total_chunks": total_chunks,
        "imported_chunks": 0,
        "source_files": source_files_meta or [],
        "error": None,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "started_at": None,
        "finished_at": None,
    }
    await _write_cache(task_id, task)
    return task


async def update_task(
    *,
    task_id: str,
    status: Optional[str] = None,
    imported_chunks: Optional[int] = None,
    total_chunks: Optional[int] = None,
    error: Optional[str] = None,
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
) -> None:
    """更新导入任务：MySQL UPDATE + 重写 Redis 缓存。

    status 接受模型词汇（done）或表词汇（succeeded），内部统一为表词汇。
    """
    db_status = _to_db_status(status)
    sets: list[str] = []
    args: list[Any] = []
    if db_status is not None:
        sets.append("status = %s")
        args.append(db_status)
    if imported_chunks is not None:
        sets.append("imported_chunks = %s")
        args.append(imported_chunks)
    if total_chunks is not None:
        sets.append("total_chunks = %s")
        args.append(total_chunks)
    if error is not None:
        sets.append("error = %s")
        args.append(error)
    if started_at is not None:
        sets.append("started_at = %s")
        args.append(started_at)
    if finished_at is not None:
        sets.append("finished_at = %s")
        args.append(finished_at)
    if not sets:
        return

    args.append(task_id)
    await execute_write(
        f"UPDATE {_TABLE} SET {', '.join(sets)} WHERE task_id = %s",
        tuple(args),
    )
    # 重写缓存（直接以真相源为准，保证一致）
    await _refresh_cache(task_id)


# ============================ 读操作 ============================
async def get_task(task_id: str) -> Optional[dict]:
    """读单任务：先 Redis 热缓存，miss/解析失败回退 MySQL 并回填。"""
    raw = await _safe_redis(
        "task_cache_get", lambda: get_redis().get(_cache_key(task_id))
    )
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"[task_store] 缓存解析失败，回退 MySQL：{task_id}")

    row = await fetch_one(
        f"SELECT {_COLUMNS} FROM {_TABLE} WHERE task_id = %s", (task_id,)
    )
    if not row:
        return None
    task = _row_to_dict(row)
    await _write_cache(task_id, task)
    return task


async def list_tasks(
    *,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> dict:
    """分页倒序列出任务（ORDER BY created_at DESC）。走只读池，减轻主库压力。

    返回 {items, total, page, page_size, total_pages}。
    status 接受模型/表词汇，内部统一为表词汇。
    """
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size

    where: list[str] = []
    args: list[Any] = []
    if status:
        db_status = _to_db_status(status)
        where.append("status = %s")
        args.append(db_status)
    if tenant_id:
        where.append("tenant_id = %s")
        args.append(tenant_id)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    count_row = await fetch_one(
        f"SELECT COUNT(*) AS cnt FROM {_TABLE}{where_sql}", tuple(args)
    )
    total = int(count_row["cnt"]) if count_row else 0

    list_args = list(args)
    list_args.append(page_size)
    list_args.append(offset)
    rows = await fetch_all(
        f"SELECT {_COLUMNS} FROM {_TABLE}{where_sql} "
        f"ORDER BY created_at DESC LIMIT %s OFFSET %s",
        tuple(list_args),
    )
    items = [_row_to_dict(r) for r in rows]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if page_size else 0,
    }
