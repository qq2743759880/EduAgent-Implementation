"""三层记忆 - 门面 service（task25 R7；R01/R01-b 升级）。

对外统一入口，供 chat service / graph 工具 / 管理接口调用：
- `get_memory_store()` / `get_memory_queue()`：单例
- `start_memory_worker()` / `stop_memory_worker()`：应用 lifespan 启停后台消费
- `enqueue_turn(user_id, text, *, messages=, assistant_reply=)`：R01-b 起收**对话窗**；
  R08 起目标态=完整对话窗（历史轮+本轮用户/AI 成对，`build_turn_window` 拼装），
  旧单 query 调用兼容保留（半窗显式告警）
- `recall_topk(user_id, query, top_k)`：GWT② 向量召回 top-3（返回体**不含内部 id**，
  防原始记忆 ID 泄入 LLM prompt）
- `format_memories_for_prompt()` / `recall_topk_mapped()`：R01 防幻觉 ID→序号映射（mem0 同款）

线程/协程安全：单例惰性初始化 + asyncio 单事件循环场景（与 FastAPI 一致）。
"""
from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from app.config import settings
from app.ai.memory.ingest import normalize_window
from app.ai.memory.queue import MemoryWriteQueue
from app.ai.memory.store import MemoryStore

# R01 防幻觉：记忆以 [M1]/[M2] 序号注入 prompt，真实 memory_id 只留在代码侧映射表，
# 禁止把内部 id 交给 LLM（mem0 同款）。本指令随映射文本一起注入，防止模型臆造未列出的序号。
MEMORY_REF_INSTRUCTION = "（引用用户记忆时只能使用上述 [M序号]，禁止臆造未列出的记忆或序号）"


# ---------------------------------------------------------------------------
# 单例（惰性）
# ---------------------------------------------------------------------------
_store: MemoryStore | None = None
_queue: MemoryWriteQueue | None = None
_init_lock = asyncio.Lock()
_worker_started = False


async def _ensure_instances() -> tuple[MemoryStore, MemoryWriteQueue]:
    """惰性构建 store + queue（幂等，并发安全）。"""
    global _store, _queue
    if _store is not None and _queue is not None:
        return _store, _queue
    async with _init_lock:
        if _store is not None and _queue is not None:
            return _store, _queue
        from app.ai.memory import persistence as _persistence

        persistence = _persistence.build_persistence()
        store = MemoryStore(persistence)
        queue = MemoryWriteQueue(store)
        _store, _queue = store, queue
        return store, queue


async def get_memory_store() -> MemoryStore:
    store, _ = await _ensure_instances()
    return store


async def get_memory_queue() -> MemoryWriteQueue:
    _, queue = await _ensure_instances()
    return queue


def memory_store_sync() -> MemoryStore:
    """同步取 store（图/工具在非 async 上下文构造时用；未构建则建内存降级实例）。"""
    from app.ai.memory import persistence as _p
    from app.ai.memory.event_persistence import MemEventMemoryPersistence
    from app.ai.memory.vector import MemoryVectorStore

    global _store
    if _store is None:
        _store = MemoryStore(MemEventMemoryPersistence(), MemoryVectorStore())
    return _store


# ---------------------------------------------------------------------------
# 生命周期
# ---------------------------------------------------------------------------
async def start_memory_worker() -> None:
    """后台消费者（配合阻塞 BRPOP + 内存兜底）。由 Tests/主应用 lifespan 调用一次。"""
    global _worker_started, _dream_scheduler_task, _hitl_sweep_task
    if _worker_started:
        return
    queue = await get_memory_queue()
    queue.start_consumer()
    _worker_started = True
    # task-M1：启动 Dream 巩固后台调度（轻量、非阻塞，失败不影响主链路）
    try:
        _dream_scheduler_task = asyncio.create_task(_dream_scheduler_loop())
    except Exception as exc:
        logger.warning(f"[Memory] Dream 调度启动失败（忽略）: {exc}")
    # task-S1-③：启动 HITL 过期 pending 后台扫描（pending 超 TTL → 自动拒绝，AC3 后台路径）
    try:
        if getattr(settings, "HITL_ESCALATION_AUTO", True):
            _hitl_sweep_task = asyncio.create_task(_hitl_sweep_loop())
    except Exception as exc:
        logger.warning(f"[Memory] HITL sweep 调度启动失败（忽略）: {exc}")
    logger.info("[Memory] 记忆写队列消费者已启动")


async def stop_memory_worker(timeout: float = 8.0) -> None:
    """W-NEXT-LIFECYCLE-001：优雅停止后台消费者 + Dream/HITL sweep。

    全部异常捕 BaseException（不仅 Exception），防止 lifespan 阶段 asyncio.CancelledError
    透传到 uvicorn 导致 "Application shutdown failed" + 完整 traceback（uvicorn 0.52 已知问题）。

    Args:
        timeout: queue.stop_consumer 整体超时（默认 8s；lifespan stop_memory_worker 阶段目标 10s 内完成）。
    """
    global _worker_started, _dream_scheduler_task, _hitl_sweep_task
    if not _worker_started:
        return
    queue = await get_memory_queue()
    try:
        # queue.stop_consumer 内部已捕 BaseException + timeout shield，这里再裹一层防 cancel 直击
        await asyncio.wait_for(asyncio.shield(queue.stop_consumer(timeout=timeout)), timeout=timeout + 1.0)
    except asyncio.CancelledError:
        # lifespan shutdown 阶段被外层（uvicorn Server.handle_exit）cancel → 吞掉
        logger.info("[Memory] stop_consumer 收到 lifespan cancel（已吞，无 traceback）")
    except asyncio.TimeoutError:
        logger.warning("[Memory] stop_consumer 超时未结束（视为完成，继续清理后续任务）")
    except Exception as exc:
        logger.warning(f"[Memory] stop_consumer 异常（忽略继续清理）：{type(exc).__name__}: {exc}")
    if _dream_scheduler_task is not None:
        try:
            _dream_scheduler_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(_dream_scheduler_task), timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
        finally:
            _dream_scheduler_task = None
    if _hitl_sweep_task is not None:
        try:
            _hitl_sweep_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(_hitl_sweep_task), timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
        finally:
            _hitl_sweep_task = None
    _worker_started = False
    logger.info("[Memory] 记忆写队列消费者已停止")


# ---------------------------------------------------------------------------
# 对上层接口（chat service / graph 工具调用）
# ---------------------------------------------------------------------------
def build_turn_window(
    history_turns: list[tuple[str, str]] | list[dict] | None,
    *,
    query: str,
    answer: str | None,
) -> list[dict[str, str]]:
    """R08：拼装「完整对话窗」= 会话历史轮（正序 [(role, content)] 或 [{role, content}]）
    + 本轮 (query, answer) 成对收尾——防止记忆窗缺 assistant 半边上下文。

    纯函数零 I/O；非法角色/空内容由 normalize_window 二次过滤。answer 为空串/None 时
    只拼到本轮 user 消息（T9-C3 语义：空 answer 轮不入窗）。
    """
    msgs: list[dict[str, str]] = []
    for t in history_turns or []:
        if isinstance(t, dict):
            msgs.append({"role": str(t.get("role") or ""), "content": str(t.get("content") or "")})
        elif isinstance(t, (tuple, list)) and len(t) >= 2:
            msgs.append({"role": str(t[0]), "content": str(t[1])})
    if query and str(query).strip():
        msgs.append({"role": "user", "content": str(query)})
    if answer and str(answer).strip():
        msgs.append({"role": "assistant", "content": str(answer)})
    return msgs


async def enqueue_turn(
    user_id: int,
    text: str | None = None,
    *,
    messages: list[dict] | None = None,
    assistant_reply: str | None = None,
    threshold: int | None = None,
) -> int:
    """单轮对话结束触发记忆（R01-b 起收**对话窗**，R08 起首选完整对话窗含 assistant 回复）。

    入参三选一/组合：
    - `messages`：完整对话窗（[{role, content}]，历史轮+本轮成对，取最近
      MEMORY_INGEST_WINDOW=10 条）——R08 目标态，chat 两侧调用点已对齐；
    - `text`（+可选 `assistant_reply`）：合成「用户问→助手答」最小窗口（旧调用兼容）；
    整窗作为 turn 载荷异步入队（毫秒级快返），规则+LLM 抽取均在 worker 内完成；
    载荷带 v=2 版本字段，消费端按形状探测兼容 v1/v2/旧 candidate 载荷。
    importance < threshold 的候选在 worker 侧过滤（默认 MEMORY_IMPORTANCE_THRESHOLD=4）。
    全程不阻塞/不抛错到应答链路（GWT①④）。

    Returns:
        成功入队返回 1；空窗 / 助手回复为空串（T9-C3 跳过不入窗）/ 入队失败返回 0。
    """
    try:
        # T9-C3：助手回复为空串（LLM 空响应，sixnode.answer/generator 只对异常兜底、不兜空串）
        # → 本轮对话不完整，跳过入记忆窗，避免空 answer 轮触发抽取污染长期记忆。
        if assistant_reply is not None and not str(assistant_reply).strip():
            logger.warning("[Memory] 本轮助手回复为空串，跳过入记忆窗（T9-C3，防记忆污染）")
            return 0
        window = normalize_window(
            messages, text=text, assistant_reply=assistant_reply,
            limit=int(getattr(settings, "MEMORY_INGEST_WINDOW", 10)),
        )
        if not window:
            return 0
        # R08：半窗守卫——有 user 发言但整窗零 assistant 回复 = 上下文缺半边。
        # 兼容旧「单 query」调用不硬拒（保持旧契约可入队），但显式告警暴露调用点缺口。
        has_user = any(m["role"] == "user" for m in window)
        has_assistant = any(m["role"] == "assistant" for m in window)
        if has_user and not has_assistant:
            logger.warning(
                "[Memory] 记忆窗缺 assistant 半边（仅 user 发言）——R08 完整对话窗目标态未对齐的调用点请改为传 messages 完整窗"
            )
        queue = await get_memory_queue()
        return 1 if await queue.enqueue_turn_window(
            int(user_id), window, threshold=threshold
        ) else 0
    except Exception as exc:  # 记忆链路任何异常都不允许波及应答链路
        logger.warning(f"[Memory] enqueue_turn 失败（本轮不入队，不影响应答）: {exc}")
        return 0


def _strip_internal_ids(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """剥离内部 memory_id：召回结果进工具返回/prompt 时不得携带原始 id（R01 防幻觉）。"""
    return [{k: v for k, v in (row or {}).items() if k != "id"} for row in rows]


def format_memories_for_prompt(
    memories: list[dict[str, Any]],
    *,
    header: str = "用户记忆",
    with_instruction: bool = True,
) -> tuple[str, dict[str, int | None]]:
    """R01 防幻觉：召回记忆 → 序号化 prompt 文本 + 代码侧 ID 映射（mem0 同款）。

    - 注入文本只含 `[M1] …；[M2] …` 序号，**真实 memory_id 永不进 prompt**；
    - 返回 `(text, ref_map)`，ref_map={"[M1]": 17, ...}（id 缺失时映射为 None），
      供后续 LLM 驱动的更新/删除操作把序号解析回真实 id 前做存在性校验；
    - 空列表返回 `("", {})`，调用方据此回退「（无历史记忆）」占位。
    """
    lines: list[str] = []
    ref_map: dict[str, int | None] = {}
    serial = 0
    for row in memories or []:
        if not isinstance(row, dict):
            continue
        content = str(row.get("content") or "").replace("\n", " ").strip()
        if not content:
            continue
        serial += 1
        ref = f"[M{serial}]"
        lines.append(f"{ref} {content[:200]}")
        raw_id = row.get("id")
        ref_map[ref] = int(raw_id) if raw_id is not None else None
    if not lines:
        return "", {}
    text = f"{header}：" + "；".join(lines)
    if with_instruction:
        text += "\n" + MEMORY_REF_INSTRUCTION
    return text, ref_map


async def recall_topk(user_id: int, query: str, top_k: int = 3, *,
                       valid_only: bool = True) -> list[dict[str, Any]]:
    """GWT②：向量召回 top-k 记忆（供 graph 的 memory 子代理/lead plan prompt）。

    valid_only 默认 True：仅返回 `valid_to IS NULL` 有效版本（task-M1 AC2）。
    R01：返回体剥离内部 id（原始 id 只经 `recall_topk_mapped` 的映射表暴露给代码侧）。"""
    store = await get_memory_store()
    rows = await store.recall(user_id=int(user_id), query=query, top_k=max(1, top_k),
                              valid_only=valid_only)
    return _strip_internal_ids(rows)


async def recall_topk_mapped(
    user_id: int, query: str, top_k: int = 3, *, header: str = "用户记忆",
) -> tuple[str, dict[str, int | None], list[dict[str, Any]]]:
    """R01：召回 + ID→序号映射一步到位的 prompt 注入入口。

    Returns:
        (prompt_text, ref_map, safe_rows)
        - prompt_text：空召回时为 ""（调用方回退占位文案）；
        - ref_map：序号→真实 memory_id（代码侧持有，不入 prompt）；
        - safe_rows：剥离 id 的召回明细（供日志/结构化透传）。
    """
    store = await get_memory_store()
    rows = await store.recall(user_id=int(user_id), query=query, top_k=max(1, top_k))
    text, ref_map = format_memories_for_prompt(rows, header=header)
    return text, ref_map, _strip_internal_ids(rows)


async def run_forget(user_id: int) -> dict[str, int]:
    """主动遗忘任务（容量卫兵/管理接口）。"""
    store = await get_memory_store()
    return await store.run_forget(int(user_id))


# ===========================================================================
# task-M1：事件溯源 / Dream 巩固 包装（供 API / 管理接口 / 图工具调用）
# ===========================================================================
_dream_scheduler_task: asyncio.Task | None = None
_hitl_sweep_task: asyncio.Task | None = None


async def _hitl_sweep_loop() -> None:
    """后台轻量调度：周期扫描 HITL 过期 pending → 自动拒绝（task-S1-③，AC3 后台路径）。

    对齐 task-M1 `_dream_scheduler_loop` 模式：非阻塞 SCAN/SQL，失败不影响主链路。
    间隔复用 settings.HITL_ESCALATION_INTERVAL；TTL 复用 settings.HITL_PENDING_TTL_S。
    store 惰性取默认（生产 = MysqlHitlStore），避免顶层耦合 hitl_gate。
    """
    from app.ai.hitl_gate import sweep_expired_pending, _default_hitl_store

    interval = max(60, int(getattr(settings, "HITL_ESCALATION_INTERVAL", 1800)))
    ttl_s = int(getattr(settings, "HITL_PENDING_TTL_S", 600))
    store = _default_hitl_store()
    logger.info(f"[HITL] sweep 后台扫描已启动（interval={interval}s, ttl={ttl_s}s）")
    while True:
        try:
            await asyncio.sleep(interval)
            res = await sweep_expired_pending(store=store, ttl_s=ttl_s)
            rejected = int(res.get("rejected") or 0)
            if rejected:
                logger.info(f"[HITL] sweep 自动拒绝过期 pending {res}")
        except Exception as exc:
            logger.warning(f"[HITL] sweep 循环异常（下次重试）: {exc}")


async def rewind_entity(*, user_id: int, entity_id: int, target_event_id: int) -> dict:
    """回滚某记忆实体到目标版本（ChronoMem 语义：追加 rewind 事件，HEAD 指向目标）。"""
    store = await get_memory_store()
    new_eid = await store.rewind(
        entity_id=int(entity_id), target_event_id=int(target_event_id),
        operator=f"user:{int(user_id)}",
    )
    return {"entity_id": int(entity_id), "new_head_entity_id": int(new_eid)}


async def entity_history(*, entity_id: int, limit: int = 50, offset: int = 0) -> list[dict]:
    """分页事件流（审计溯源）。"""
    store = await get_memory_store()
    return await store.history(entity_id=int(entity_id), limit=int(limit), offset=int(offset))


async def trigger_dream(*, user_id: int, **kwargs) -> dict:
    """手动触发 Dream 巩固（受分布式锁保护）。"""
    from app.ai.memory.dream import run_dream

    return await run_dream(int(user_id), **kwargs)


async def compact_user_memory(*, user_id: int, **kwargs) -> dict:
    """手动触发容量压缩（懒合成摘要）。"""
    from app.ai.memory.compactor import compact_user

    store = await get_memory_store()
    return await compact_user(store, int(user_id), **kwargs)


async def _dream_scheduler_loop() -> None:
    """后台轻量调度：扫描会话计数键，达标用户触发 Dream（非阻塞 SCAN，失败不影响主链路）。"""
    scan_interval = max(300, int(getattr(settings, "DREAM_MIN_AGE_HOURS", 24) * 60))
    prefix = "memory:session_count:"
    while True:
        try:
            await asyncio.sleep(scan_interval)
            from app.ai.memory.dream import run_dream
            from app.database import get_redis

            r = get_redis()
            cursor = 0
            while True:
                cursor, keys = await r.scan(cursor, match=f"{prefix}*", count=200)
                for k in keys:
                    try:
                        uid = int(k.decode().split(prefix)[-1])
                        cnt = int(await r.get(k) or 0)
                        if cnt >= settings.DREAM_SESSION_INTERVAL:
                            asyncio.create_task(run_dream(uid))
                            await r.delete(k)
                    except Exception:
                        continue
                if cursor == 0:
                    break
        except Exception as exc:
            logger.warning(f"[Memory] Dream 调度循环异常（下次重试）: {exc}")