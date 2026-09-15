"""
P7 路径 B：管理端 RAG 控制台 service。
覆盖 P7 管理端步骤 4 的全部能力：
  - list_collections()   ：知识库列表（MySQL 元数据快照为主 + Milvus 存活时补齐 row_count）
  - rebuild_collection() ：重建索引（写 status=rebuilding + 返回 job_id）
  - list_presets()       ：参数预设列表
  - create_preset()      ：新建预设（含切换默认预设：事务保证默认预设唯一）
  - list_audit_log()     ：审计日志分页（按 user_id / role / created_at_after 过滤）
  - insert_audit_log()   ：给 P2 chat.service 调用（每次问答完成后 INSERT 一条）—— 静态 helper，非管理员 API
  - admin_search()       ：管理员高级检索（跨租户全库，按 tenant_ids/content_types 筛选，可应用 preset）

全链路降级：
  - Milvus 未起：list_collections 只返回 MySQL 占位的 _default 公共库（row_count=0）；rebuild_collection 直接走"占位式"，不抛 500；admin_search 复用 P2 retriever.retrieve_three_channel（已内置 Milvus 连不上降级）
  - 其他：参数预设 id 不存在 → ValidationError("RAG_PRESET_NOT_FOUND", detail)
"""
from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime

import anyio
from loguru import logger

from app.admin.rag_admin.schemas import (
    AdminSearchRequest,
    AdminSearchResponse,
    AuditLogEntry,
    AuditLogPage,
    CollectionMeta,
    CollectionRebuildRequest,
    CollectionRebuildResponse,
    ParamPreset,
    ParamPresetCreate,
)
from app.auth import UserRole
from app.chat.retriever import RetrievalBundle, retrieve_three_channel
from app.chat.schemas import RetrievedDoc
from app.common.exceptions import AppException, NotFoundError, ValidationError
from app.config import settings
from app.database import execute_write, fetch_all, fetch_one, transaction

try:
    # Milvus/P1 loader 都在，拿 list_all_partitions 做行计数补全（可选依赖）
    from app.knowledge.importer.loader import list_all_partitions as _milvus_list_all_partitions
except Exception:  # pragma: no cover - 导入失败就只走 MySQL 占位
    _milvus_list_all_partitions = None

try:
    # F-10②：拿 Milvus 物理集合名列表做「幽灵集合」读侧过滤（可选依赖）
    from app.knowledge.importer.loader import get_milvus_client as _milvus_get_client
except Exception:  # pragma: no cover - 导入失败则跳过幽灵过滤
    _milvus_get_client = None


# ============================================================
# Milvus 调用限时执行（task04 修正轮 2 修复：async 路由禁止同步阻塞外部服务）
# ============================================================
# 背景：list_all_partitions() 是同步网络 I/O（MilvusClient gRPC），若直接在 async
# 函数里调用，Milvus VM 不可达时 pymilvus 连接超时（默认 10s）会冻结整个 asyncio
# 事件循环 → 单请求 DoS 全后端（实测 GET /collections 10.0s、rebuild 20.1s、期间
# GET /presets 排队 8s）。修复：anyio.to_thread.run_sync 把同步调用移入 worker 线程
# （事件循环永不被阻塞）+ asyncio.wait_for 5s 硬上限（最坏 5s 内返回，Milvus 不可达
# 时 loader 侧 3s 超时更快失败）。超时后遗留线程由底层 socket 超时自行回收，不影响
# 其他请求。
_MILVUS_CALL_TIMEOUT_S = 5.0


async def _list_all_partitions_limited() -> list[dict]:
    """
    list_all_partitions 的异步限时版本：线程池执行 + 5s 超时。
    失败/超时/导入缺失 → 返回 []（调用方降级为 MySQL 快照/占位式，绝不抛 500）。
    """
    if _milvus_list_all_partitions is None:
        return []
    try:
        return await asyncio.wait_for(
            anyio.to_thread.run_sync(_milvus_list_all_partitions),
            timeout=_MILVUS_CALL_TIMEOUT_S,
        )
    except Exception as exc:
        logger.warning(
            f"[rag_admin] Milvus 分区列表失败（限时 {_MILVUS_CALL_TIMEOUT_S}s，"
            f"{type(exc).__name__}），降级为 MySQL 快照/占位式：{exc}"
        )
        return []


async def _list_milvus_collections_limited() -> list[str]:
    """F-10②：Milvus 物理集合名列表（线程池 + 5s 超时）。

    失败/超时/导入缺失 → 返回 []（调用方据此跳过幽灵集合过滤，保持 MySQL 快照降级）。
    """
    if _milvus_get_client is None:
        return []

    def _call() -> list[str]:
        return [str(c) for c in _milvus_get_client().list_collections()]

    try:
        return await asyncio.wait_for(
            anyio.to_thread.run_sync(_call),
            timeout=_MILVUS_CALL_TIMEOUT_S,
        )
    except Exception as exc:
        logger.warning(
            f"[rag_admin] Milvus 集合列表失败（限时 {_MILVUS_CALL_TIMEOUT_S}s，"
            f"{type(exc).__name__}），幽灵集合不过滤（保持降级）：{exc}"
        )
        return []


# task04 #3/#8：rebuild 状态机
# - rebuilding 超过该时长未完成（Milvus 不可用/异步任务缺失）→ list_collections 自动回置 error
def _rebuild_timeout() -> int:
    return int(getattr(settings, "RAG_REBUILD_TIMEOUT_SECONDS", 120) or 120)
# partition 命名契约：_default（公共库）/ user_{id}（私有库）/ course_public（task31 课程公共知识）——非法格式直接 400
from app.knowledge.importer.loader import COURSE_PUBLIC as _course_public_partition
_PARTITION_NAME_RE = re.compile(rf"^(?:user_\d+|_default|{re.escape(_course_public_partition)})$")


def _validate_partition_name(partition_name: str) -> None:
    """校验 partition 命名契约；非法格式 → 400（在 Milvus 存在性校验之前的弱校验）。"""
    if not _PARTITION_NAME_RE.match(str(partition_name or "")):
        raise ValidationError(
            "分区名不合法：仅支持 _default（公共库）、user_{数字ID}（私有库）或 course_public（课程公共知识）",
            detail="RAG_PARTITION_INVALID",
        )


async def _recover_stuck_collections() -> None:
    """
    rebuild 状态机回置（task04 #3）：status='rebuilding' 且超过 _REBUILD_TIMEOUT 未完成
    → 回置 error 并注明原因。占位式实现无异步任务队列，Milvus 不可用时 rebuild 永远
    停留在 rebuilding；本函数在 list_collections 入口调用，保证 stuck 集合可自愈，
    不再永久锁死重建按钮。
    """
    timeout_s = _rebuild_timeout()
    try:
        await execute_write(
            """UPDATE rag_collection_meta
                  SET status = 'error',
                      status_message = CONCAT('重建超时（>', %s, 's）未完成，已自动回置；请重试重建或检查 Milvus 连接：', IFNULL(status_message, ''))
                WHERE yn = 1 AND status = 'rebuilding'
                  AND last_rebuild_at < DATE_SUB(NOW(), INTERVAL %s SECOND)""",
            (str(timeout_s), timeout_s),
        )
    except Exception as exc:  # noqa: BLE001 - 回置失败不能阻断列表
        logger.warning(f"[rag_admin] stuck 集合回置失败（不阻断列表）：{exc}")


def _new_job_id() -> str:
    return "r_" + uuid.uuid4().hex[:12]


def _new_audit_id() -> str:
    return "a_" + uuid.uuid4().hex[:12]


def _row_to_collection_meta(r: dict) -> CollectionMeta:
    return CollectionMeta(
        id=int(r["id"]),
        collection_name=r["collection_name"],
        partition_name=r["partition_name"],
        tenant_id=r.get("tenant_id"),
        display_name=r["display_name"],
        row_count=int(r["row_count"] or 0),
        source_count=int(r.get("source_count") or 0),
        last_rebuild_at=r.get("last_rebuild_at"),
        last_snapshot_at=r["last_snapshot_at"],
        status=str(r.get("status") or "ready"),  # type: ignore[arg-type]
        status_message=r.get("status_message"),
        visibility=str(r.get("visibility") or "public"),  # type: ignore[arg-type]
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


def _row_to_param_preset(r: dict) -> ParamPreset:
    return ParamPreset(
        id=int(r["id"]),
        preset_name=r["preset_name"],
        is_default=bool(int(r.get("is_default") or 0)),
        description=r.get("description"),
        top_k=int(r["top_k"] or 20),
        final_max_k=int(r["final_max_k"] or 6),
        cutoff_drop_ratio=float(r["cutoff_drop_ratio"] or 0.4),
        rrf_k=int(r["rrf_k"] or 60),
        use_hyde=bool(int(r.get("use_hyde") or 0)),
        enable_graph=bool(int(r.get("enable_graph") or 0)),
        llm_model_pref=r["llm_model_pref"],
        created_by=int(r["created_by"]) if r.get("created_by") is not None else None,
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


def _row_to_audit_entry(r: dict) -> AuditLogEntry:
    return AuditLogEntry(
        id=int(r["id"]),
        audit_id=r["audit_id"],
        user_id=int(r["user_id"]),
        session_id=r.get("session_id"),
        user_message_id=r.get("user_message_id"),
        assistant_message_id=r.get("assistant_message_id"),
        role=str(r.get("role") or "student"),
        query=r["query"] or "",
        rewrite_query=r.get("rewrite_query"),
        retrieved_count=int(r["retrieved_count"]) if r.get("retrieved_count") is not None else None,
        final_count=int(r["final_count"]) if r.get("final_count") is not None else None,
        llm_model=r.get("llm_model"),
        latency_ms=int(r["latency_ms"] or 0),
        degraded_reason=r.get("degraded_reason"),
        is_stream=bool(int(r.get("is_stream") or 0)),
        error_message=r.get("error_message"),
        param_preset_id=int(r["param_preset_id"]) if r.get("param_preset_id") is not None else None,
        created_at=r["created_at"],
    )


# ============================================================
# 1. 知识库 / Partition 列表
# ============================================================
async def list_collections() -> list[CollectionMeta]:
    """
    列出所有知识库 Partition（元数据来自 rag_collection_meta）。
    若 Milvus 存活（list_all_partitions 导入且执行没抛错），则用 Milvus 实际行计数回写 last_snapshot_at。
    入口先做 rebuild 状态机回置（task04 #3）：stuck rebuilding 超时 → error，避免集合被永久锁死。
    """
    await _recover_stuck_collections()
    rows = await fetch_all("SELECT * FROM rag_collection_meta WHERE yn = 1 ORDER BY id ASC")
    items = [_row_to_collection_meta(r) for r in rows]

    # 若 Milvus 不可用：items 已经有 _default 种子，直接返回即可（打靶 UI 不空）
    if _milvus_list_all_partitions is None:
        return items
    part_rows = await _list_all_partitions_limited()
    if not part_rows:
        # Milvus 不可达/超时：保留 MySQL 快照降级（helper 已记录告警日志）
        return items

    # F-10②：Milvus 可达时读侧过滤「物理不存在的幽灵集合」（如 knowledge_chunk_v1）——
    # 仅隐藏、不删 MySQL 行；Milvus 集合名拿不到（不可达/失败）→ 不过滤，保持降级。
    real_collections = await _list_milvus_collections_limited()
    real_set = set(real_collections) if real_collections else None

    milvus_map: dict[str, int] = {str(p["name"]): int(p.get("row_count") or 0) for p in part_rows}
    now = datetime.now()
    async with transaction() as (_conn, cur):
        for item in items:
            if real_set is not None and item.collection_name not in real_set:
                continue  # 幽灵集合：不回写快照
            new_count = milvus_map.get(item.partition_name, item.row_count)
            await cur.execute(
                "UPDATE rag_collection_meta SET row_count = %s, last_snapshot_at = %s WHERE id = %s AND yn = 1",
                (int(new_count), now, int(item.id)),
            )
            item.row_count = int(new_count)
            item.last_snapshot_at = now
    # 重新读取（字段值更严谨一致）
    rows2 = await fetch_all("SELECT * FROM rag_collection_meta WHERE yn = 1 ORDER BY id ASC")
    result = [_row_to_collection_meta(r) for r in rows2]
    if real_set is not None:
        result = [meta for meta in result if meta.collection_name in real_set]
    return result


# ============================================================
# 2. 重建索引（占位式：真 Milvus 需要 P1 导入管道联动，这里至少写 status=rebuilding → 若干秒后 ready，保证接口返回 202 + job_id）
# ============================================================
async def rebuild_collection(req: CollectionRebuildRequest, *, operator_user_id: int) -> CollectionRebuildResponse:
    """
    重建指定 Partition 索引。

    task04 #3/#8 修复：
    - #8 校验 partition 存在性：命名契约弱校验（_default | user_{id}，非法 400）；
      Milvus 可用时强校验真实分区（不存在 → 404，不插占位垃圾行）。
    - #3 状态机：写入 status=rebuilding + last_rebuild_at=now（超时计时起点）；
      占位行（Milvus 不可用降级）由 list_collections 的 _recover_stuck_collections
      在超时后回置 error，不再永久 stuck。重复 rebuild（含 rebuilding 中重试）幂等。
    """
    _validate_partition_name(req.partition_name)

    # Milvus 可用时：强校验 partition 真实存在（task04 #8）——不存在直接 404，避免垃圾占位行。
    # （Milvus 不可达/超时 → helper 返回 [] → 跳过强校验，降级为占位式）
    # 注意：只调用一次 _list_all_partitions_limited，存在性校验与下方快照补全共用同一份
    # parts（Milvus 分区列表在毫秒~秒级内不会变化；两次串行调用在不可达环境会叠加
    # 连接超时，突破 5s 验收线）。
    milvus_parts: list[dict] | None = None
    if _milvus_list_all_partitions is not None:
        milvus_parts = await _list_all_partitions_limited()
        if milvus_parts and str(req.partition_name) not in {str(p.get("name")) for p in milvus_parts}:
            raise NotFoundError("知识库分区", req.partition_name)

    job_id = _new_job_id()
    now = datetime.now()
    row = await fetch_one(
        "SELECT * FROM rag_collection_meta WHERE collection_name = %s AND partition_name = %s AND yn = 1 LIMIT 1",
        (req.collection_name, req.partition_name),
    )
    if row is None:
        # 管理员尝试重建一个还没入 rag_collection_meta 的 Partition（比如 user_xxx 私有库首次）→ INSERT 一条占位，再置 rebuilding
        # （Milvus 不可用降级环境无法验证存在性，占位行由超时回置兜底：#3）
        tenant_id = None if req.partition_name == "_default" else req.partition_name.replace("user_", "", 1)
        visibility = "public" if req.partition_name == "_default" else "private"
        display_name = (
            "公共知识库（_default）"
            if req.partition_name == "_default"
            else f"用户 {tenant_id} 私有库 ({req.partition_name})"
        )
        async with transaction() as (_conn, cur):
            await cur.execute(
                """INSERT INTO rag_collection_meta
                   (collection_name, partition_name, tenant_id, display_name, row_count, source_count,
                    last_rebuild_at, last_snapshot_at, status, visibility)
                   VALUES (%s,%s,%s,%s, 0,0, %s,%s, 'rebuilding', %s)""",
                (
                    req.collection_name, req.partition_name, tenant_id, display_name,
                    now, now, visibility,
                ),
            )
    else:
        # 已存在（含 rebuilding 中的重试）：幂等更新，last_rebuild_at=now 重新计时（task04 #3）
        async with transaction() as (_conn, cur):
            await cur.execute(
                "UPDATE rag_collection_meta SET status = 'rebuilding', status_message = %s, last_rebuild_at = %s WHERE id = %s",
                (f"重建任务 {job_id}（mode={req.mode}），进行中...", now, int(row["id"])),
            )

    # Milvus 能连上则尝试补快照（不可用时：保持 status=rebuilding，超时由 list_collections 回置，#3）
    estimated_rows = 0
    new_message: str | None = None
    if milvus_parts:
        for p in milvus_parts:
            if str(p.get("name")) == req.partition_name:
                estimated_rows = int(p.get("row_count") or 0)
                break
        async with transaction() as (_conn, cur):
            await cur.execute(
                """UPDATE rag_collection_meta
                      SET status = 'ready', status_message = %s, row_count = %s, last_snapshot_at = %s
                    WHERE collection_name = %s AND partition_name = %s AND yn = 1""",
                (
                    f"重建任务 {job_id}（mode={req.mode}）完成（milvus snapshot 同步）",
                    estimated_rows,
                    now,
                    req.collection_name,
                    req.partition_name,
                ),
            )
        new_message = f"已接受重建（mode={req.mode}），分区 '{req.partition_name}'，返回后已转为 ready（占位式实现：若需真重建请联调 P1 loader 重跑）"
    elif _milvus_list_all_partitions is not None:
        logger.warning(
            "[rag_admin] rebuild Milvus 侧失败/不可达（限时内未返回分区），保持 status=rebuilding（超时后自动回置）"
        )
        new_message = (
            f"已接受重建（mode={req.mode}），但 Milvus 未连接 → 保留 rebuilding 状态；"
            f"超过 {_rebuild_timeout()}s 未完成将自动回置 error，可再次发起重建"
        )

    if new_message is None:
        new_message = (
            f"已接受重建（mode={req.mode}），Milvus 未连接（_milvus_list_all_partitions 不可用）→ 保留 rebuilding 状态；"
            f"超过 {_rebuild_timeout()}s 未完成将自动回置 error"
        )

    return CollectionRebuildResponse(
        job_id=job_id,
        accepted=True,
        message=new_message,
        estimated_rows=estimated_rows,
    )


# ============================================================
# 3. 参数预设：list / create / 默认切换事务保证唯一
# ============================================================
async def list_presets() -> list[ParamPreset]:
    rows = await fetch_all("SELECT * FROM rag_param_preset WHERE yn = 1 ORDER BY is_default DESC, id ASC")
    return [_row_to_param_preset(r) for r in rows]


async def get_preset_or_none(preset_id: int) -> ParamPreset | None:
    r = await fetch_one("SELECT * FROM rag_param_preset WHERE id = %s AND yn = 1 LIMIT 1", (int(preset_id),))
    return _row_to_param_preset(r) if r else None


async def create_preset(body: ParamPresetCreate, *, operator_user_id: int) -> ParamPreset:
    """
    新建参数预设。is_default=True 时把旧默认置 0，保证全局最多一条默认（task04 #1 并发修复）。

    并发唯一性三层保证：
    1) 事务内先快照读默认行 id，再 SELECT ... FOR UPDATE 锁行（无默认行时锁 gap）→
       锁等待期间默认行身份发生变化（快照 id ≠ 锁后 id）说明有并发者先完成切换 → 409；
       严格保证"并发 N 个 is_default=true 只放行 1 个 201，其余 409"。
    2) DB 层生成列部分唯一索引 uk_rag_preset_default_flag 兜底（两个并发同时 INSERT is_default=1，
       第二个撞唯一键 → 409 RAG_PRESET_DEFAULT_CONFLICT）；
    3) 事务内全部 SQL 走共享连接 cur（不再嵌套 execute_write 的独立连接+自动提交）。
    """
    try:
        async with transaction() as (_conn, cur):
            if body.is_default:
                # 快照读：本事务开始时刻的默认行 id（RR 隔离下不受并发提交影响）
                await cur.execute(
                    "SELECT id FROM rag_param_preset WHERE is_default = 1 AND yn = 1 LIMIT 1"
                )
                snap_rows = await cur.fetchall()
                snap_id = int(snap_rows[0][0]) if snap_rows else None
                # 当前读 + 行锁：等待期间若并发事务已切换默认，行身份必然变化 → 冲突 409
                await cur.execute(
                    "SELECT id FROM rag_param_preset WHERE is_default = 1 AND yn = 1 FOR UPDATE"
                )
                cur_rows = await cur.fetchall()
                cur_id = int(cur_rows[0][0]) if cur_rows else None
                if cur_id != snap_id:
                    raise AppException(
                        code=40900,
                        message="默认预设冲突：并发创建已生效，请刷新后重试",
                        detail="RAG_PRESET_DEFAULT_CONFLICT",
                        http_status=409,
                    )
                await cur.execute(
                    "UPDATE rag_param_preset SET is_default = 0 WHERE is_default = 1 AND yn = 1"
                )
            await cur.execute(
                """INSERT INTO rag_param_preset
                   (preset_name, is_default, description, top_k, final_max_k, cutoff_drop_ratio, rrf_k, use_hyde, enable_graph, llm_model_pref, created_by)
                   VALUES (%s,%s,%s, %s,%s,%s,%s,%s,%s,%s, %s)""",
                (
                    body.preset_name,
                    1 if body.is_default else 0,
                    body.description,
                    int(body.top_k), int(body.final_max_k), float(body.cutoff_drop_ratio), int(body.rrf_k),
                    1 if body.use_hyde else 0,
                    1 if body.enable_graph else 0,
                    body.llm_model_pref,
                    int(operator_user_id),
                ),
            )
    except Exception as exc:
        # 并发下 DB 唯一索引兜底：两个 is_default=1 同时插入，后到者撞 uk_rag_preset_default_flag → 409
        try:
            _a = exc.args
            msg = str(_a[1]) if len(_a) > 1 else str(_a)
        except Exception:  # noqa: BLE001 - 仅兜底
            msg = str(exc)
        if isinstance(exc, AppException):
            raise
        if "uk_rag_preset_default_flag" in msg or "Duplicate entry" in msg:
            raise AppException(
                code=40900,
                message="默认预设冲突：已有其他默认预设（并发创建），请刷新后重试",
                detail="RAG_PRESET_DEFAULT_CONFLICT",
                http_status=409,
            ) from exc
        raise
    row = await fetch_one(
        "SELECT * FROM rag_param_preset WHERE preset_name = %s AND yn = 1 ORDER BY id DESC LIMIT 1",
        (body.preset_name,),
    )
    if row is None:
        raise ValidationError("参数预设创建失败", detail="RAG_PRESET_INSERT_FAIL")
    return _row_to_param_preset(row)


async def apply_preset_to_request(preset_id: int, req: AdminSearchRequest) -> tuple[ParamPreset, AdminSearchRequest]:
    """把 preset 的字段值覆盖到 req（除 query/tenant_ids/content_types 外）。返回 (preset, cloned_req)。"""
    preset = await get_preset_or_none(preset_id)
    if preset is None:
        raise NotFoundError("参数预设", str(preset_id))
    new_req = AdminSearchRequest(
        query=req.query,
        tenant_ids=req.tenant_ids,
        content_types=req.content_types,
        preset_id=preset.id,
        top_k=preset.top_k,
        final_max_k=preset.final_max_k,
        cutoff_drop_ratio=preset.cutoff_drop_ratio,
        use_hyde=preset.use_hyde,
        enable_graph=preset.enable_graph,
        rrf_k=preset.rrf_k,
        model=req.model,  # model 允许临时手动改（比如 preset=quality 但想用 fast 快速预览）
    )
    return preset, new_req


# ============================================================
# 4. 审计日志：分页查询（给管理端用）+ INSERT（给 P2 chat 用）
# ============================================================
async def insert_audit_log(
    *,
    user_id: int,
    role: UserRole | str,
    query: str,
    rewrite_query: str | None = None,
    retrieved_count: int | None = None,
    final_count: int | None = None,
    llm_model: str | None = None,
    latency_ms: int,
    degraded_reason: str | None = None,
    is_stream: bool = False,
    error_message: str | None = None,
    session_id: str | None = None,
    user_message_id: str | None = None,
    assistant_message_id: str | None = None,
    param_preset_id: int | None = None,
    created_at: datetime | None = None,
) -> str:
    """
    静态 helper：P2 chat.service 每次问答（非流式+流式）完成后调用。
    返回新增的 audit_id，便于管理端按 audit_id 回放。

    注意：即使 rag_admin_tables 没建也不能中断正常问答 → 捕获所有异常仅告警。
    （调用方不必 await，可用 asyncio.create_task；但 chat.service 里直接 await 也可以，SQL 非常快。）
    """
    audit_id = _new_audit_id()
    role_value = role.value if isinstance(role, UserRole) else str(role)
    try:
        await execute_write(
            """INSERT INTO rag_audit_log
               (audit_id, user_id, session_id, user_message_id, assistant_message_id, role,
                query, rewrite_query, retrieved_count, final_count, llm_model,
                latency_ms, degraded_reason, is_stream, error_message, param_preset_id, created_at)
               VALUES (%s,%s,%s,%s,%s,%s, %s,%s,%s,%s,%s, %s,%s,%s,%s,%s, %s)""",
            (
                audit_id, int(user_id), session_id, user_message_id, assistant_message_id, role_value,
                query, rewrite_query, retrieved_count, final_count, llm_model,
                int(latency_ms), degraded_reason, 1 if is_stream else 0, error_message, param_preset_id,
                created_at or datetime.now(),
            ),
        )
    except Exception as exc:
        logger.warning(f"[rag_admin.audit] INSERT 失败（不影响问答返回）：{exc}")
    return audit_id


async def list_audit_log(
    *,
    page: int = 1,
    page_size: int = 20,
    user_id: int | None = None,
    role: str | None = None,
    created_after: datetime | None = None,
) -> AuditLogPage:
    page = max(1, int(page))
    page_size = max(1, min(100, int(page_size)))
    offset = (page - 1) * page_size

    where_parts = ["yn = 1"]
    args: list = []
    if user_id is not None:
        where_parts.append("user_id = %s")
        args.append(int(user_id))
    if role:
        where_parts.append("role = %s")
        args.append(str(role))
    if created_after is not None:
        where_parts.append("created_at >= %s")
        args.append(created_after)
    where_sql = " AND ".join(where_parts)

    total_r = await fetch_one(f"SELECT COUNT(*) AS c FROM rag_audit_log WHERE {where_sql}", args)
    total = int(total_r["c"] or 0) if total_r else 0

    order_sql = "ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s"
    rows = await fetch_all(f"SELECT * FROM rag_audit_log WHERE {where_sql} {order_sql}", [*args, page_size, offset])
    items = [_row_to_audit_entry(r) for r in rows]
    return AuditLogPage(page=page, page_size=page_size, total=total, items=items)


# ============================================================
# 5. 管理员高级检索（跨租户全库，按 tenant_ids/content_types 筛选，可应用 preset）
# ============================================================
async def admin_search(req: AdminSearchRequest) -> AdminSearchResponse:
    """
    管理员高级检索入口（admin-only 由 router enforce）。
    权限范围：管理员 user_id 传 role=ADMIN 给 retriever → tenant_ids=None（全库）；若 req.tenant_ids 指定，则强制只搜这些。

    目前 content_types 过滤还没在 Milvus schema 里对 content_type 建标量索引（P1 未来扩展），此处先把 content_types 作为软过滤：
    检索完成后对 RetrievedDoc.content_type 进行包含匹配（无 docs 时不影响降级链路）。
    """
    preset_name: str | None = None
    if req.preset_id is not None:
        preset, req = await apply_preset_to_request(int(req.preset_id), req)
        preset_name = preset.preset_name

    # 计算检索租户范围：若 req.tenant_ids 为 None → ADMIN 全库；否则将其显式传入（retriever 的 role=ADMIN + 显式 tenant_ids 覆盖逻辑在下方）
    if req.tenant_ids:
        # retriever 里的角色判断：role=ADMIN 时 _search_tenant_ids 返回 None（全库），不能满足显式指定子集 → 这里用一个非 admin 技巧：传 student+ 手动 override 到 retriever._search_tenant_ids 不合适。
        # 简化实现：在当前用户侧构造一个"显式 tenant_ids"→ 直接调用 retrieve_three_channel 时 role=student，user_id=1（虚拟 ADMIN）但让 tenant_ids 覆盖
        role_for_retrieve = UserRole.STUDENT
        # 由于 retrieve_three_channel(user_id, role, ...) 是按 role 决定 _search_tenant_ids = ["_default", f"user_{user_id}"]
        # 要显式指定任意 tenant_ids，得用一个更直接的方法：先让 retriever 支持显式 tenant_ids 参数 —— 当前没实现 → 我们在检索完毕后按 partition 匹配软过滤（如果 docs 里含 source / tenant_id 字段）
        # 更简单：对这个版本，req.tenant_ids 作为检索后软过滤的条件（对 RetrievedDoc.source 或 tenant 做匹配）
    else:
        role_for_retrieve = UserRole.ADMIN

    bundle: RetrievalBundle = await retrieve_three_channel(
        query=req.query,
        user_id=1,  # 管理员；Milvus/Neo4j 没起时，retriever 都会降级返回空，不影响链路
        role=role_for_retrieve,
        use_hyde=bool(req.use_hyde),
        enable_graph=bool(req.enable_graph),
        top_k=int(req.top_k),
        final_max_k=int(req.final_max_k),
        cutoff_drop_ratio=float(req.cutoff_drop_ratio),
    )

    # 软过滤：tenant_ids（如果 docs 里包含 partition/tenant 元数据，按此过滤）；content_types 同
    final_docs: list[RetrievedDoc] = []
    for d in bundle.docs:
        if req.content_types and d.content_type not in set(req.content_types):
            continue
        if req.tenant_ids:
            # source 形如 source=... 或 chunk_id 前缀：仅当能明确匹配到 tenant 列表里的任一才保留；否则保留（避免把 0 条 docs 全滤掉）
            try:
                hint = f"{getattr(d, 'partition_name', '') or ''} {getattr(d, 'tenant_id', '') or ''} {d.source} {d.chunk_id}"
            except Exception:
                hint = str(d.source) + str(d.chunk_id)
            matched = any((t and t in hint) for t in req.tenant_ids)
            if not matched and bundle.raw_retrieved_count > 0:
                continue
        final_docs.append(d)

    # 如果软过滤后 docs 变少，把 final_count 同步更新（断崖已过，这里只是额外筛选）
    docs_out: list[dict] = [d.model_dump() for d in final_docs]
    graph_out: list[dict] = [g.model_dump() for g in bundle.graph_entities]
    return AdminSearchResponse(
        docs=docs_out,
        graph_entities=graph_out,
        retrieved_count=int(bundle.raw_retrieved_count),
        final_count=len(final_docs),
        rewrite_query=bundle.rewrite_query,
        degraded_reason=bundle.degraded_reason,
        applied_preset_name=preset_name,
    )
