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
# Owner(Discovery §8): Task/Asset 状态机 —— 唯一维护方，变更须经 Runtime Manager
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Optional

from loguru import logger

from app.config import settings
from app.core.db_resilience import DependencyUnavailableError, redis_run
from app.database import execute_write, fetch_all, fetch_one, get_redis, transaction
from app.knowledge.models import (
    ASSET_STAGE_FAILED,
    ASSET_STAGE_INGESTED,
    ASSET_STAGE_IR_READY,
    ASSET_STAGE_PARSING,
    ASSET_STAGE_QUEUED_PARSER,
    IMPORT_ASSET_STAGES,
)

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
# W2-S2 additive：document_id 列（task 级主文档标识；多文件任务取首文件 document_id，NULL=存量行）
_COLUMNS = (
    "id, task_id, task_type, tenant_id, visibility, status, user_id, document_id, security_scope, "
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
        # W0-① final：发起者归属（NULL=存量行/无身份上下文调用，学生查询一律 404=仅 admin 可查）
        "user_id": int(row["user_id"]) if row.get("user_id") is not None else None,
        # W2-S2 additive：task 级主文档标识（多文件任务取首文件 document_id；NULL=存量行）
        "document_id": row.get("document_id"),
        "security_scope": row.get("security_scope") or "default",
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
    user_id: Optional[int] = None,
    document_id: Optional[str] = None,
    security_scope: str = "default",
) -> dict:
    """创建导入任务：先落 MySQL（真相源），再写 Redis 缓存。

    source_files_meta 结构：[{object_key, file_name, file_size, content_type}, ...]
    object_key 即 MinIO edu-upload 的 key（30 天生命周期留存）。

    W0-① final（fail-closed 裁定）：``user_id`` 记录发起者归属——upload 两入口与
    MCP 入口均传发起者 user_id；status 端点对普通用户按 owner 严格相等放行，
    NULL（存量行/极少数无身份上下文的调用）一律 404，不做查询层 legacy 例外。
    存量 NULL 行如需对用户可见须走一次性 backfill（数据面），不在查询层开口子。

    W2-S2 additive：``document_id`` 为 task 级主文档标识（多文件任务取首文件的
    document_id）；None=不传（存量行为完全不变，列落 NULL）。
    """
    source_json = json.dumps(source_files_meta or [], ensure_ascii=False)
    status = STATUS_PENDING
    await execute_write(
        f"INSERT INTO {_TABLE} "
        "(task_id, task_type, tenant_id, visibility, status, user_id, document_id, security_scope, total_chunks, source_files, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())",
        (task_id, task_type, tenant_id, visibility, status, user_id, document_id, security_scope, total_chunks, source_json),
    )
    task = {
        "task_id": task_id,
        "task_type": task_type,
        "tenant_id": tenant_id,
        "visibility": visibility,
        "status": status,
        "user_id": user_id,
        "document_id": document_id,
        "security_scope": security_scope,
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
async def record_ingest_chunk_count(task_id: str, asset_id: str, execution_epoch: int, count: int) -> bool:
    """Idempotent per-asset count, recorded only after the fenced ingest completion."""
    if count < 0:
        raise ValueError("chunk count cannot be negative")
    async with transaction() as (_, cur):
        await cur.execute(f"SELECT document_id FROM {_ASSET_TABLE} WHERE task_id=%s AND asset_id=%s "
                          "AND execution_epoch=%s AND stage='ingested'", (task_id, asset_id, execution_epoch))
        asset = await cur.fetchone()
        if not asset:
            return False
        document_id = asset[0]
        await cur.execute(f"SELECT source_files FROM {_TABLE} WHERE task_id=%s FOR UPDATE", (task_id,))
        row = await cur.fetchone()
        if not row:
            return False
        files = json.loads(row[0]) if isinstance(row[0], (str, bytes)) else row[0]
        matches = [item for item in files if item.get("document_id") == document_id]
        if len(matches) != 1:
            return False
        matches[0]["ingested_chunk_count"] = count
        imported = sum(int(item.get("ingested_chunk_count", 0)) for item in files)
        total = imported + sum(20 for item in files if "ingested_chunk_count" not in item)
        await cur.execute(f"UPDATE {_TABLE} SET source_files=%s, imported_chunks=%s, total_chunks=%s WHERE task_id=%s",
                          (json.dumps(files, ensure_ascii=False), imported, total, task_id))
    # Delete only this task's disposable cache; MySQL is the durable authority.
    try:
        await get_redis().delete(_REDIS_KEY_PREFIX + task_id)
    except Exception:
        pass
    return True


async def get_task(task_id: str, *, include_source_files: bool = True) -> Optional[dict]:
    """读单任务：先 Redis 热缓存，miss/解析失败回退 MySQL 并回填。

    B0-FIX（P1-4 大行地雷排除）：``include_source_files=False`` 时 SELECT 剔除
    ``source_files`` 大 JSON 列（batch 级任务可达数百 KB，多包行在 Windows
    ProactorEventLoop + asyncmy 下触发 BufferError 连接坏死——uvicorn 即 Proactor）。
    HTTP 状态面（upload.get_task_status）传 False；worker/恢复 CLI（Selector）
    需要该列时保持默认 True，行为不变。
    """
    raw = await _safe_redis(
        "task_cache_get", lambda: get_redis().get(_cache_key(task_id))
    )
    if raw:
        try:
            task = json.loads(raw)
            if include_source_files or task.get("source_files") is None:
                return task
            # 缓存命中但调用方不要大列：置 None（键保留，契约形状不变）
            task = dict(task)
            task["source_files"] = None
            return task
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"[task_store] 缓存解析失败，回退 MySQL：{task_id}")

    columns = _COLUMNS if include_source_files else ",".join(
        c for c in _COLUMNS.split(",") if c.strip() != "source_files"
    )
    row = await fetch_one(
        f"SELECT {columns} FROM {_TABLE} WHERE task_id = %s", (task_id,)
    )
    if not row:
        return None
    task = _row_to_dict(row)
    if not include_source_files:
        task["source_files"] = None
    await _write_cache(task_id, task)
    return task


async def get_authoritative_task_asset(task_id: str, asset_id: str) -> tuple[dict, dict] | None:
    """Read task security metadata and its related asset directly from MySQL.

    This deliberately bypasses the Redis task cache: parser and ingest decisions about
    tenant, owner, visibility and source identity must use the durable authority.
    """
    async with transaction() as (_, cur):
        await cur.execute(
            "SELECT t.task_id AS t_task_id, t.task_type, t.tenant_id, t.visibility, "
            "t.status, t.user_id, t.document_id AS t_document_id, t.security_scope, "
            "t.total_chunks, t.imported_chunks, t.source_files, t.error AS t_error, "
            "t.created_at, t.started_at, t.finished_at, "
            "a.asset_id, a.task_id AS a_task_id, a.file_index, a.bucket, a.object_key, "
            "a.file_name, a.sha256, a.size_bytes, a.mime, a.document_id AS a_document_id, "
            "a.stage, a.retry_count, a.execution_epoch, a.lease_owner, a.lease_until, "
            "a.parse_fingerprint, a.artifact_ref, a.dispatched_epoch, a.dlq_epoch, a.error AS a_error, "
            "a.vector_status, a.graph_status, a.graph_retry_needed, "
            "a.created_at AS asset_created_at "
            "FROM knowledge_import_task t JOIN import_source_asset a ON a.task_id = t.task_id "
            "WHERE t.task_id = %s AND a.task_id = %s AND a.asset_id = %s",
            (task_id, task_id, asset_id),
        )
        columns = [d[0] for d in cur.description]
        raw = await cur.fetchone()
    if raw is None:
        return None
    row = dict(zip(columns, raw))
    task_row = {
        "task_id": row["t_task_id"], "task_type": row["task_type"],
        "tenant_id": row["tenant_id"], "visibility": row["visibility"],
        "status": row["status"], "user_id": row["user_id"],
        "document_id": row["t_document_id"], "security_scope": row["security_scope"],
        "total_chunks": row["total_chunks"], "imported_chunks": row["imported_chunks"],
        "source_files": row["source_files"], "error": row["t_error"],
        "created_at": row["created_at"], "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }
    asset_row = {
        "asset_id": row["asset_id"], "task_id": row["a_task_id"],
        "file_index": row["file_index"], "bucket": row["bucket"],
        "object_key": row["object_key"], "file_name": row["file_name"],
        "sha256": row["sha256"], "size_bytes": row["size_bytes"], "mime": row["mime"],
        "document_id": row["a_document_id"], "stage": row["stage"],
        "retry_count": row["retry_count"], "execution_epoch": row["execution_epoch"],
        "lease_owner": row["lease_owner"], "lease_until": row["lease_until"],
        "parse_fingerprint": row["parse_fingerprint"], "artifact_ref": row["artifact_ref"],
        "dispatched_epoch": row["dispatched_epoch"], "dlq_epoch": row["dlq_epoch"],
        "vector_status": row["vector_status"], "graph_status": row["graph_status"],
        "graph_retry_needed": bool(row["graph_retry_needed"]),
        "error": row["a_error"],
        "created_at": row["asset_created_at"],
    }
    return _row_to_dict(task_row), _asset_row_to_dict(asset_row)


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
    # B0-FIX（P1-4 大行地雷排除续）：列表视图剔除 source_files 大 JSON 列
    # （batch 级任务可达数百 KB 多包行，ProactorEventLoop + asyncmy 读取触发
    # BufferError → 2013 → 50301；管理端列表只需要状态/计数投影）。
    list_columns = ",".join(
        c for c in _COLUMNS.split(",") if c.strip() != "source_files"
    )
    rows = await fetch_all(
        f"SELECT {list_columns} FROM {_TABLE}{where_sql} "
        f"ORDER BY created_at DESC LIMIT %s OFFSET %s",
        tuple(list_args),
    )
    items = [_row_to_dict(r) for r in rows]
    for it in items:
        it["source_files"] = None

    # B0-FIX（资产明细）：列表视图附每任务紧凑资产行（来自 import_source_asset，
    # 不含大 JSON 列）——管理端"文件名/文件数/资产明细"展示的数据源。
    ids = [it.get("task_id") for it in items if it.get("task_id")]
    if ids:
        placeholders = ", ".join(["%s"] * len(ids))
        asset_rows = await fetch_all(
            f"SELECT task_id, asset_id, file_index, file_name, document_id, stage, "
            f"parse_fingerprint, execution_epoch, error "
            f"FROM {_ASSET_TABLE} WHERE task_id IN ({placeholders}) "
            f"ORDER BY task_id, file_index",
            tuple(ids),
        )
        by_task: dict[str, list[dict]] = {}
        for r in asset_rows:
            by_task.setdefault(r["task_id"], []).append({
                "asset_id": r["asset_id"], "file_index": r["file_index"],
                "file_name": r["file_name"], "document_id": r["document_id"],
                "stage": r["stage"], "parse_fingerprint": r["parse_fingerprint"],
                "execution_epoch": r["execution_epoch"], "error": r["error"],
            })
        for it in items:
            it["assets"] = by_task.get(it.get("task_id"), [])

    # legacy 上传任务无 asset 行 → 从上传时刻写的 Redis 名字缓存补文件名（P1-4 续）。
    missing = [it["task_id"] for it in items if not it.get("assets")]
    if missing:
        try:
            keys = [f"kb:task_names:{t}" for t in missing]
            cached = await _safe_redis(
                "task_names_mget", lambda: get_redis().mget(keys)
            ) or []
            for tid, raw in zip(missing, cached):
                if not raw:
                    continue
                try:
                    names = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
                    it_by_id = next(x for x in items if x["task_id"] == tid)
                    it_by_id["assets"] = [
                        {"file_name": n.get("file_name"), "file_index": i}
                        for i, n in enumerate(names if isinstance(names, list) else [])
                        if isinstance(n, dict)
                    ]
                except (json.JSONDecodeError, TypeError, StopIteration):
                    continue
        except Exception as exc:  # noqa: BLE001 — 名字补全属锦上添花
            logger.warning(f"[task_store] legacy 任务文件名补全失败：{exc!r}")
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if page_size else 0,
    }


# ==================== W2-S2：import_source_asset（源资产细化表） ====================
# 职责边界（ADR-W2-01 + PRD v2.2 §2）：
# - asset = task 1:N 细化（每个源文件一行），parser job 的 claim/retry/lease 全部在此表；
#   task 级 status 四态机不动、不建第二套 task 状态机。
# - 本表是 asset 的唯一写入口（S5 起 Command 收敛调用；真实消费在 S4）。
# - stage 为冻结词汇（models.IMPORT_ASSET_STAGES）；W2 只走 queued_parser→ir_ready 两态。
_ASSET_TABLE = "import_source_asset"
_ASSET_COLUMNS = (
    "asset_id, task_id, file_index, bucket, object_key, file_name, sha256, "
    "size_bytes, mime, document_id, stage, retry_count, execution_epoch, "
    "lease_owner, lease_until, parse_fingerprint, artifact_ref, dispatched_epoch, dlq_epoch, "
    "vector_status, graph_status, graph_retry_needed, error, created_at"
)


def _new_asset_id() -> str:
    """asset_id：uuid 短 id（32 hex 足够 VARCHAR(40)，无碰撞业务语义）。"""
    return uuid.uuid4().hex


def _new_document_id() -> str:
    """document_id：资产创建时为每个文件生成（PRD v2.2 §5——身份随 asset 持久化）。"""
    return uuid.uuid4().hex


def _asset_row_to_dict(row: dict) -> dict:
    """import_source_asset 行 → JSON 安全 dict（datetime → ISO 字符串）。"""
    return {
        "asset_id": row.get("asset_id"),
        "task_id": row.get("task_id"),
        "file_index": int(row.get("file_index") or 0),
        "bucket": row.get("bucket"),
        "object_key": row.get("object_key"),
        "file_name": row.get("file_name"),
        "sha256": row.get("sha256"),
        "size_bytes": int(row["size_bytes"]) if row.get("size_bytes") is not None else None,
        "mime": row.get("mime"),
        "document_id": row.get("document_id"),
        "stage": row.get("stage"),
        "retry_count": int(row.get("retry_count") or 0),
        "execution_epoch": int(row.get("execution_epoch") or 0),
        "lease_owner": row.get("lease_owner"),
        "lease_until": _serialize_dt(row.get("lease_until")),
        "parse_fingerprint": row.get("parse_fingerprint"),
        "artifact_ref": row.get("artifact_ref"),
        "dispatched_epoch": int(row["dispatched_epoch"]) if row.get("dispatched_epoch") is not None else None,
        "dlq_epoch": int(row["dlq_epoch"]) if row.get("dlq_epoch") is not None else None,
        "vector_status": row.get("vector_status") or "not-produced",
        "graph_status": row.get("graph_status") or "not-produced",
        "graph_retry_needed": bool(row.get("graph_retry_needed")),
        "error": row.get("error"),
        "created_at": _serialize_dt(row.get("created_at")),
    }


async def create_source_assets(
    task_id: str,
    assets: list[dict],
) -> int:
    """批量创建源资产（唯一写入口）：MySQL 批量 INSERT，每文件一条。

    每个元素支持字段（缺省安全）：file_index / bucket / object_key / file_name /
    sha256 / size_bytes / mime / document_id / error。
    - **document_id 裁定**：asset 创建时为每个文件生成 uuid 短 id（调用方已传则
      尊重调用方——S5 Command 的幂等重放需要稳定 id）；随后本函数把**首个 asset**
      的 document_id 回填 task 行（PRD v2.2 §5：task.document_id = 首文件标识）。
    - stage 一律从 ASSET_STAGE_QUEUED_PARSER 起步（冻结词汇，不接受调用方指定）。
    - error（W2-S5 additive）：创建期 degrade 留痕（Command 对无 MinIO 对象的
      资产行落 "no-minio-object(legacy-local-path)"），非失败语义、不阻断导入。
    返回插入行数（= len(assets)）。
    """
    if not assets:
        return 0

    rows: list[tuple] = []
    for i, a in enumerate(assets):
        document_id = a.get("document_id") or _new_document_id()
        rows.append((
            a.get("asset_id") or _new_asset_id(),
            task_id,
            int(a.get("file_index", i)),
            a.get("bucket"),
            a.get("object_key"),
            a.get("file_name"),
            a.get("sha256"),
            a.get("size_bytes"),
            a.get("mime"),
            document_id,
            ASSET_STAGE_QUEUED_PARSER,  # 冻结起点，不接受外部指定
            a.get("error"),
        ))

    for row in rows:  # execute_write 仅接受单语句 tuple；逐条插入（每文件一行，语义等价）
        await execute_write(
            f"INSERT INTO {_ASSET_TABLE} "
            "(asset_id, task_id, file_index, bucket, object_key, file_name, sha256, "
            "size_bytes, mime, document_id, stage, error) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            row,
        )

    # task 级主文档标识 = 首文件 document_id（additive 回填；失败不阻断资产创建）
    first_document_id = rows[0][9]
    try:
        await execute_write(
            f"UPDATE {_TABLE} SET document_id = %s WHERE task_id = %s "
            "AND document_id IS NULL",
            (first_document_id, task_id),
        )
    except Exception as exc:  # 回填失败仅告警：asset 已落库，S5 Command 可重试
        logger.warning(f"[task_store] task.document_id 回填失败（task={task_id}）：{exc!r}")
    return len(rows)


async def get_source_assets(task_id: str) -> list[dict]:
    """读任务全部源资产（按 file_index 升序；走只读语义的单条查询）。"""
    rows = await fetch_all(
        f"SELECT {_ASSET_COLUMNS} FROM {_ASSET_TABLE} "
        "WHERE task_id = %s ORDER BY file_index ASC",
        (task_id,),
    )
    return [_asset_row_to_dict(r) for r in rows]


async def update_asset_stage(
    asset_id: str,
    stage: str,
    *,
    expected_stage: str,
    error: Optional[str] = None,
) -> int:
    """CAS 推进 asset 阶段（PRD v2.2 §2 统一形态）：

        UPDATE import_source_asset
        SET stage=:stage, execution_epoch=execution_epoch+1, error=:error
        WHERE asset_id=:id AND stage=:expected_stage

    - 仅当当前 stage == expected_stage 才推进（影响行数=1），否则 0 行（并发竞争
      者落败，由调用方决定重读/重试/放弃）；成功即 execution_epoch +1。
    - ``error`` 只在进入 failed 时由调用方传（其余传 None 即清空，本单调用方仅
      验 queued_parser→ir_ready 路径）。
    返回受影响行数（0 或 1）。
    """
    return await execute_write(
        f"UPDATE {_ASSET_TABLE} "
        "SET stage = %s, execution_epoch = execution_epoch + 1, error = %s "
        "WHERE asset_id = %s AND stage = %s",
        (stage, error, asset_id, expected_stage),
    )


async def claim_asset(
    asset_id: str,
    *,
    task_id: str,
    source_stage: str,
    target_stage: str,
    execution_epoch: int,
    owner: str,
    lease_seconds: int = 120,
) -> bool:
    """Claim one queued asset using the DB epoch and a unique owner fence."""
    if source_stage not in (ASSET_STAGE_QUEUED_PARSER, ASSET_STAGE_IR_READY):
        raise ValueError(f"unsupported claim source stage: {source_stage}")
    if target_stage not in (ASSET_STAGE_PARSING, "ingesting"):
        raise ValueError(f"unsupported claim target stage: {target_stage}")
    changed = await execute_write(
        f"UPDATE {_ASSET_TABLE} SET stage = %s, lease_owner = %s, "
        "lease_until = DATE_ADD(UTC_TIMESTAMP(), INTERVAL %s SECOND), error = NULL, "
        "vector_status = IF(%s = 'ingesting', 'pending', vector_status), "
        "graph_status = IF(%s = 'ingesting', 'pending', graph_status) "
        "WHERE asset_id = %s AND task_id = %s AND stage = %s AND execution_epoch = %s "
        "AND (lease_until IS NULL OR lease_until < UTC_TIMESTAMP())",
        (target_stage, owner, max(5, int(lease_seconds)), target_stage, target_stage,
         asset_id, task_id, source_stage, execution_epoch),
    )
    return changed == 1


async def renew_asset_lease(
    asset_id: str, *, execution_epoch: int, owner: str, lease_seconds: int = 120,
) -> bool:
    changed = await execute_write(
        f"UPDATE {_ASSET_TABLE} SET lease_until = DATE_ADD(UTC_TIMESTAMP(), INTERVAL %s SECOND) "
        "WHERE asset_id = %s AND execution_epoch = %s AND lease_owner = %s "
        "AND stage IN ('parsing', 'ingesting') AND lease_until >= UTC_TIMESTAMP()",
        (max(5, int(lease_seconds)), asset_id, execution_epoch, owner),
    )
    if changed == 1:
        return True
    # MySQL reports zero changed rows when a rapid renewal lands in the same
    # DATETIME second and writes the already-current lease_until value. Confirm
    # the fence still belongs to this owner before treating that no-op as alive.
    async with transaction() as (_, cur):
        await cur.execute(
            f"SELECT 1 FROM {_ASSET_TABLE} WHERE asset_id = %s AND execution_epoch = %s "
            "AND lease_owner = %s AND stage IN ('parsing', 'ingesting') "
            "AND lease_until >= UTC_TIMESTAMP() LIMIT 1",
            (asset_id, execution_epoch, owner),
        )
        return bool(await cur.fetchone())


async def transition_claimed_asset(
    asset_id: str,
    *,
    execution_epoch: int,
    owner: str,
    expected_stage: str,
    stage: str,
    error: str | None = None,
    parse_fingerprint: str | None = None,
    artifact_ref: str | None = None,
    vector_status: str | None = None,
    graph_status: str | None = None,
    graph_retry_needed: bool | None = None,
) -> bool:
    """Complete a claim only while its lease owner and epoch still match."""
    sets = ["stage = %s", "error = %s", "lease_owner = NULL", "lease_until = NULL"]
    args: list[Any] = [stage, error]
    if parse_fingerprint is not None:
        sets.append("parse_fingerprint = %s")
        args.append(parse_fingerprint)
    if artifact_ref is not None:
        sets.append("artifact_ref = %s")
        args.append(artifact_ref)
    if vector_status is not None:
        sets.append("vector_status = %s")
        args.append(vector_status)
    if graph_status is not None:
        sets.append("graph_status = %s")
        args.append(graph_status)
    if graph_retry_needed is not None:
        sets.append("graph_retry_needed = %s")
        args.append(1 if graph_retry_needed else 0)
    sets.append("dispatched_epoch = NULL")
    args.extend([asset_id, execution_epoch, owner, expected_stage])
    changed = await execute_write(
        f"UPDATE {_ASSET_TABLE} SET {', '.join(sets)} "
        "WHERE asset_id = %s AND execution_epoch = %s AND lease_owner = %s "
        "AND stage = %s AND lease_until >= UTC_TIMESTAMP()",
        tuple(args),
    )
    return changed == 1


async def retry_claimed_asset(
    asset_id: str,
    *,
    execution_epoch: int,
    owner: str,
    expected_stage: str,
    retry_stage: str,
    max_retries: int,
    reason: str,
) -> tuple[str, int, int] | None:
    """Fenced retry transition. Returns (stage, epoch, retry_count), or None if stale."""
    if retry_stage not in (ASSET_STAGE_QUEUED_PARSER, ASSET_STAGE_IR_READY):
        raise ValueError(f"unsupported retry stage: {retry_stage}")
    changed = await execute_write(
        f"UPDATE {_ASSET_TABLE} SET stage = IF(retry_count + 1 >= %s, 'failed', %s), "
        "vector_status = IF(%s = 'ir_ready', IF(stage = 'failed', 'failed', 'pending'), vector_status), "
        "graph_status = IF(%s = 'ir_ready', IF(stage = 'failed', 'failed', 'pending'), graph_status), "
        "graph_retry_needed = IF(%s = 'ir_ready', 0, graph_retry_needed), "
        "retry_count = retry_count + 1, "
        "execution_epoch = execution_epoch + 1, dispatched_epoch = NULL, "
        "lease_owner = NULL, lease_until = NULL, error = %s "
        "WHERE asset_id = %s AND execution_epoch = %s AND lease_owner = %s "
        "AND stage = %s AND lease_until >= UTC_TIMESTAMP()",
        (max(1, int(max_retries)), retry_stage, retry_stage, retry_stage, retry_stage,
         reason[:500], asset_id, execution_epoch, owner, expected_stage),
    )
    if changed != 1:
        return None
    async with transaction() as (_, cur):
        await cur.execute(
            f"SELECT stage, execution_epoch, retry_count FROM {_ASSET_TABLE} WHERE asset_id = %s",
            (asset_id,),
        )
        names = [d[0] for d in cur.description]
        values = await cur.fetchone()
    row = dict(zip(names, values)) if values else None
    if not row:
        return None
    return str(row["stage"]), int(row["execution_epoch"]), int(row["retry_count"])


async def list_assets_for_dispatch(limit: int = 100) -> list[dict]:
    """Find durable queued work without a successful Redis enqueue marker."""
    async with transaction() as (_, cur):
        await cur.execute(
            f"SELECT {_ASSET_COLUMNS} FROM {_ASSET_TABLE} "
            "AS a WHERE a.stage IN (%s, %s) "
            "AND (a.dispatched_epoch IS NULL OR a.dispatched_epoch <> a.execution_epoch) "
            "AND (a.stage = %s OR NOT EXISTS ("
            f"SELECT 1 FROM {_ASSET_TABLE} peer WHERE peer.task_id = a.task_id "
            "AND peer.stage NOT IN (%s, %s, %s))) "
            "ORDER BY a.created_at ASC LIMIT %s",
            (ASSET_STAGE_QUEUED_PARSER, ASSET_STAGE_IR_READY, ASSET_STAGE_QUEUED_PARSER,
             ASSET_STAGE_IR_READY, ASSET_STAGE_FAILED, ASSET_STAGE_INGESTED,
             max(1, min(1000, int(limit)))),
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in await cur.fetchall()]
    return [_asset_row_to_dict(row) for row in rows]


async def mark_asset_dispatched(asset_id: str, *, stage: str, execution_epoch: int) -> bool:
    changed = await execute_write(
        f"UPDATE {_ASSET_TABLE} SET dispatched_epoch = %s "
        "WHERE asset_id = %s AND stage = %s AND execution_epoch = %s",
        (execution_epoch, asset_id, stage, execution_epoch),
    )
    return changed == 1


async def dispatch_asset(asset: dict, *, force: bool = False) -> bool:
    """Publish one queued asset; force republishes for a reclaimed PEL entry."""
    from app.core import job_stream as js

    stage = asset.get("stage")
    if stage not in (ASSET_STAGE_QUEUED_PARSER, ASSET_STAGE_IR_READY):
        return False
    epoch = int(asset.get("execution_epoch") or 0)
    if not force and asset.get("dispatched_epoch") == epoch:
        return True
    stream = js.PARSER_JOBS_STREAM if stage == ASSET_STAGE_QUEUED_PARSER else js.INGEST_JOBS_STREAM
    msg = js.make_message(
        job_id=f"{stream[:3]}_{uuid.uuid4().hex[:12]}",
        task_id=str(asset["task_id"]), asset_id=str(asset["asset_id"]),
        attempt_snapshot=max(1, int(asset.get("retry_count") or 0) + 1),
        execution_epoch=epoch,
    )
    if not await js.enqueue(stream, msg):
        return False
    await mark_asset_dispatched(str(asset["asset_id"]), stage=stage, execution_epoch=epoch)
    current = await get_authoritative_task_asset(str(asset["task_id"]), str(asset["asset_id"]))
    return bool(
        current and current[1].get("stage") == stage
        and int(current[1].get("execution_epoch") or 0) == epoch
        and current[1].get("dispatched_epoch") == epoch
    )


async def dispatch_pending_assets(limit: int = 100) -> dict[str, int]:
    """Publish DB-pending assets to their stage stream; MySQL remains dispatch truth."""
    stats = {"queued": 0, "failed": 0, "stale": 0}
    for asset in await list_assets_for_dispatch(limit):
        try:
            published = await dispatch_asset(asset)
        except Exception:
            published = False
        if not published:
            stats["failed"] += 1
            continue
        stats["queued"] += 1
    return stats


async def mark_asset_dlq(asset_id: str, *, execution_epoch: int) -> bool:
    changed = await execute_write(
        f"UPDATE {_ASSET_TABLE} SET dlq_epoch = %s "
        "WHERE asset_id = %s AND stage = %s AND execution_epoch = %s",
        (execution_epoch, asset_id, ASSET_STAGE_FAILED, execution_epoch),
    )
    return changed == 1


async def list_expired_assets(limit: int = 100) -> list[dict]:
    """Return in-flight rows whose durable MySQL lease has expired."""
    async with transaction() as (_, cur):
        await cur.execute(
            f"SELECT {_ASSET_COLUMNS} FROM {_ASSET_TABLE} "
            "WHERE stage IN ('parsing', 'ingesting') AND lease_until IS NOT NULL "
            "AND lease_until < UTC_TIMESTAMP() ORDER BY lease_until ASC LIMIT %s",
            (max(1, min(1000, int(limit))),),
        )
        names = [d[0] for d in cur.description]
        rows = [dict(zip(names, row)) for row in await cur.fetchall()]
    return [_asset_row_to_dict(row) for row in rows]


async def recover_expired_asset(asset_id: str, *, max_retries: int = 3) -> tuple[str, int, int] | None:
    """Requeue only a DB-confirmed expired claim, advancing the stale-owner fence."""
    changed = await execute_write(
        f"UPDATE {_ASSET_TABLE} SET "
        "vector_status = IF(stage = 'ingesting', IF(retry_count + 1 >= %s, 'failed', 'pending'), vector_status), "
        "graph_status = IF(stage = 'ingesting', IF(retry_count + 1 >= %s, 'failed', 'pending'), graph_status), "
        "graph_retry_needed = IF(stage = 'ingesting', 0, graph_retry_needed), "
        "stage = IF(retry_count + 1 >= %s, 'failed', "
        "IF(stage = 'parsing', %s, %s)), "
        "execution_epoch = execution_epoch + 1, dispatched_epoch = NULL, "
        "lease_owner = NULL, lease_until = NULL, retry_count = retry_count + 1, "
        "error = CONCAT('lease expired; recovered by reconciler: ', COALESCE(error, '')) "
        "WHERE asset_id = %s AND stage IN ('parsing', 'ingesting') "
        "AND lease_until IS NOT NULL AND lease_until < UTC_TIMESTAMP()",
        (max(1, int(max_retries)), max(1, int(max_retries)), max(1, int(max_retries)),
         ASSET_STAGE_QUEUED_PARSER, ASSET_STAGE_IR_READY, asset_id),
    )
    if changed != 1:
        return None
    async with transaction() as (_, cur):
        await cur.execute(
            f"SELECT stage, execution_epoch, retry_count FROM {_ASSET_TABLE} WHERE asset_id = %s", (asset_id,)
        )
        names = [d[0] for d in cur.description]
        values = await cur.fetchone()
    row = dict(zip(names, values)) if values else None
    return (str(row["stage"]), int(row["execution_epoch"]), int(row["retry_count"])) if row else None


# ==================== W2-S6：status additive 投影（纯读，唯一实现点） ====================
# 依据（PRD v2.4 迁移治理附录 §2 冻结一 + owner 终裁 F-019）：
# - 公开 task.status 四态（pending/running/succeeded/failed）冻结不动；
# - 部分失败语义由 additive 字段承载：stage=done_partial + asset_progress；
# - 本 Wave 无 vector/graph 真实 producer——对应字段固定 "not-produced"，禁伪造 succeeded。
# 全部为纯读投影（不改写任何表），revert 即消失；旧四态字段语义不变。

# task 级 stage 冻结词汇（附录 §2；additive，不进公开四态枚举）
TASK_STAGE_QUEUED_PARSER = "queued_parser"
TASK_STAGE_IMPORTING = "importing"
TASK_STAGE_DONE = "done"
TASK_STAGE_DONE_PARTIAL = "done_partial"
TASK_STAGE_FAILED = "failed"

# 无 asset 行（存量任务）的回退映射：按 task 自身 status 投影，保证不空洞
_TASK_STATUS_TO_STAGE = {
    STATUS_PENDING: TASK_STAGE_QUEUED_PARSER,
    STATUS_RUNNING: TASK_STAGE_IMPORTING,
    STATUS_SUCCEEDED: TASK_STAGE_DONE,
    STATUS_FAILED: TASK_STAGE_FAILED,
}

# F-019：无 producer 字段的诚实占位（vector 入库在 W3 接管、graph 在 W3 repair）
STATUS_NOT_PRODUCED = "not-produced"


def stage_from_status(status: Optional[str]) -> str:
    """task.status → task.stage 回退映射（纯函数；无 asset 行的存量任务用）。"""
    return _TASK_STATUS_TO_STAGE.get(_to_db_status(status) or "", TASK_STAGE_QUEUED_PARSER)


def aggregate_progress(assets: list[dict]) -> dict:
    """把 asset 行列表聚合成 asset_progress 投影（纯函数，不做 I/O）。

    形态（附录 §2 冻结）：{total, by_stage: {五态各计数}, ok, failed}
    - ok = ir_ready + ingested 计数（W2 终态 ir_ready 亦计入"成功"侧）；
    - 未知 stage 不崩溃（计数丢弃但不影响 total）——防御脏数据。
    """
    by_stage = {s: 0 for s in IMPORT_ASSET_STAGES}
    for a in assets or []:
        stage = (a or {}).get("stage")
        if stage in by_stage:
            by_stage[stage] += 1
    return {
        "total": len(assets or []),
        "by_stage": by_stage,
        "ok": by_stage[ASSET_STAGE_IR_READY] + by_stage[ASSET_STAGE_INGESTED],
        "failed": by_stage[ASSET_STAGE_FAILED],
    }


def _derive_stage_from_by_stage(by_stage: dict[str, int]) -> str:
    """按附录 §2 冻结表从 by_stage 计数派生 task 级 stage（纯函数）。

    冻结表（唯一实现点在本模块）：
      全部 queued_parser            → queued_parser
      存在 parsing/ingesting        → importing
      全部 ingested（W2 含 ir_ready）→ done
      部分 ok + 部分 failed（全结算） → done_partial
      全部 failed                   → failed
    """
    total = sum(by_stage.values())
    if total <= 0:  # 调用方保证 total>0；防御性回退
        return TASK_STAGE_QUEUED_PARSER
    ok = by_stage.get(ASSET_STAGE_IR_READY, 0) + by_stage.get(ASSET_STAGE_INGESTED, 0)
    failed = by_stage.get(ASSET_STAGE_FAILED, 0)
    queued = by_stage.get(ASSET_STAGE_QUEUED_PARSER, 0)
    parsing = by_stage.get(ASSET_STAGE_PARSING, 0)
    if ok == total:
        return TASK_STAGE_DONE
    if failed == total:
        return TASK_STAGE_FAILED
    if queued == total:
        return TASK_STAGE_QUEUED_PARSER
    if queued + parsing > 0:  # 仍有未结算 asset → 仍在导入中
        return TASK_STAGE_IMPORTING
    return TASK_STAGE_DONE_PARTIAL  # 全结算且 ok/failed 混合 → 部分完成


async def get_asset_progress(task_id: str) -> Optional[dict]:
    """聚合任务全部 asset 行 → asset_progress 投影（纯读）。

    无 asset 行返回 None——调用方（status 端点）据此省略 asset_progress 键，
    禁止伪造空进度（F-019：不造无 producer 的值）。
    """
    assets = await get_source_assets(task_id)
    if not assets:
        return None
    return aggregate_progress(assets)


async def get_task_stage(task: dict, *, assets: Optional[list[dict]] = None) -> str:
    """派生 task 级 stage（附录 §2 冻结映射，additive 不动公开四态）。

    - 有 asset 行：从 asset 聚合派生（queued_parser/importing/done/done_partial/failed）；
    - 无 asset 行（存量任务）：回退 task.status 映射
      （pending→queued_parser、running→importing、succeeded/failed→done/failed），
      保证存量任务投影不空洞。
    ``assets`` 可由调用方预取传入（避免同请求重复查询）。
    """
    if assets is None:
        assets = await get_source_assets((task or {}).get("task_id") or "")
    if assets:
        return _derive_stage_from_by_stage(aggregate_progress(assets)["by_stage"])
    return stage_from_status((task or {}).get("status"))


async def get_stage_by_task_ids(task_ids: list[str]) -> dict[str, str]:
    """批量派生 task 级 stage（管理端列表轻量投影：一次 GROUP BY 聚合）。

    返回 {task_id: stage}，**只含有 asset 行的 task**——调用方对缺失项回退
    stage_from_status(task.status)。聚合 SQL 全绑定参数（附录 §2 禁拼接）。
    """
    ids = [t for t in (task_ids or []) if t]
    if not ids:
        return {}
    placeholders = ", ".join(["%s"] * len(ids))
    rows = await fetch_all(
        f"SELECT task_id, stage, COUNT(*) AS cnt FROM {_ASSET_TABLE} "
        f"WHERE task_id IN ({placeholders}) GROUP BY task_id, stage",
        tuple(ids),
    )
    grouped: dict[str, dict[str, int]] = {}
    for r in rows or []:
        tid = r.get("task_id")
        if not tid:
            continue
        by = grouped.setdefault(tid, {})
        stage = r.get("stage")
        if stage in IMPORT_ASSET_STAGES:  # 未知 stage 计数丢弃（防御脏数据）
            by[stage] = by.get(stage, 0) + int(r.get("cnt") or 0)
    return {tid: _derive_stage_from_by_stage(by) for tid, by in grouped.items()}


def artifact_status_of(assets: list[dict]) -> list[dict]:
    """每个 asset 的 parse_fingerprint + artifact_ref 摘要列表（纯函数）。

    W2 无 artifact producer：artifact_ref=null 即"not-produced"语义（诚实表达，
    不造假值）；fingerprint 同理（S4 真实写入前为 null）。
    """
    return [
        {
            "file_index": (a or {}).get("file_index"),
            "file_name": (a or {}).get("file_name"),
            "parse_fingerprint": (a or {}).get("parse_fingerprint"),
            "artifact_ref": (a or {}).get("artifact_ref"),
        }
        for a in (assets or [])
    ]


def asset_runtime_status_of(assets: list[dict]) -> list[dict]:
    """Return per-asset lease/fence/status fields for task-page correlation."""
    return [
        {
            "task_id": (a or {}).get("task_id"),
            "asset_id": (a or {}).get("asset_id"),
            "file_index": (a or {}).get("file_index"),
            "file_name": (a or {}).get("file_name"),
            "stage": (a or {}).get("stage"),
            "execution_epoch": int((a or {}).get("execution_epoch") or 0),
            "retry_count": int((a or {}).get("retry_count") or 0),
            "lease_owner": (a or {}).get("lease_owner"),
            "lease_until": (a or {}).get("lease_until"),
            "dispatched_epoch": (a or {}).get("dispatched_epoch"),
            "dlq_epoch": (a or {}).get("dlq_epoch"),
            "vector_status": (a or {}).get("vector_status") or STATUS_NOT_PRODUCED,
            "graph_status": (a or {}).get("graph_status") or STATUS_NOT_PRODUCED,
            "graph_retry_needed": bool((a or {}).get("graph_retry_needed")),
            "error": (a or {}).get("error"),
        }
        for a in (assets or [])
    ]


def aggregate_producer_status(assets: list[dict], field: str) -> str:
    """Aggregate per-asset vector/graph status without inventing a success."""
    if field not in ("vector_status", "graph_status"):
        raise ValueError(f"unsupported producer status field: {field}")
    if not assets:
        return STATUS_NOT_PRODUCED
    statuses = [str((item or {}).get(field) or STATUS_NOT_PRODUCED) for item in assets]
    if all(status == STATUS_SUCCEEDED for status in statuses):
        return STATUS_SUCCEEDED
    if any(status == "degraded" for status in statuses):
        return "degraded"
    if any(status == "pending" for status in statuses):
        return "pending"
    if any(status == STATUS_FAILED for status in statuses):
        return STATUS_FAILED
    if all(status == STATUS_NOT_PRODUCED for status in statuses):
        return STATUS_NOT_PRODUCED
    return "pending"
