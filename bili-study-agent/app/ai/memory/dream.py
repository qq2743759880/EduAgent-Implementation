"""Dream 巩固子代理（task-M1 P3，对齐 Claude AutoDream / VikingMem LLM_MERGE）。

- 触发：每 DREAM_SESSION_INTERVAL 会话 + DREAM_MIN_AGE_HOURS 间隔（会话计数存 Redis）。
- 执行：fork 子代理（复用 task92 `runner._default_llm` 客户端 + 独立上下文），4 阶段
  orient/gather/consolidate/prune 把分散记忆升维为结构化条目；
  写回 `event_type=consolidate` 新行 + 源 HEAD 盖章废弃（supports 引用源 entity_id）。
- 分布式锁：Redis SET NX EX 防多实例并发巩固（task-M1 AC7）。
- LLM 调用受测试窗口纪律约束（12:00-14:00 / 18:00-9:00）；契约测试注入 mock llm 验证升维逻辑。

对外主入口：`run_dream(user_id, *, llm=None, redis=None)`。
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any, Callable

from loguru import logger

from app.config import settings
from app.ai.memory.dream_lock import DreamLock

_dream_lock = DreamLock(ttl_s=settings.DREAM_LOCK_TTL_S)

DREAM_SYSTEM_PROMPT = """你是一个记忆巩固（Dream Consolidation）子代理。你的任务是把用户分散的多条长时记忆，升级（consolidate）为更少、更结构化的高价值条目，避免"喜欢 Python""喜欢 FastAPI""讨厌 Java"三条各自独立导致召回只中一条的推荐乌龙。

请严格按 4 阶段处理提供的记忆清单：
1) orient：判断这些记忆是否属于同一用户画像维度（技术栈 / 目标 / 偏好 / 纠偏）。
2) gather：把同类、可合并的记忆聚到一起。
3) consolidate：为每组生成一条结构化升维条目，明确"是什么 / 适合什么 / 不适合什么"。
4) prune：丢弃重复与过期细节，只保留可行动的画像结论。

输出要求：仅输出一个 JSON 数组，数组元素形如：
[{"content": "结构化升维结论", "memory_type": "preference|goal|profile|correction|fact", "topic": "分组", "importance": 1-5, "source_entity_ids": [对应记忆的 entity_id]}
不要输出任何解释或 markdown 代码块围栏，直接输出 JSON 数组。"""

_SESSION_KEY = "memory:session_count:{uid}"
_LAST_KEY = "memory:dream_last:{uid}"


def _extract_json_array(text: str) -> list[dict]:
    """从 LLM 输出中稳健抽取 JSON 数组（容忍 ```json 围栏 / 前后噪声）。"""
    if text is None:
        return []
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(\[.*\])\s*```", t, re.S)
    if m:
        t = m.group(1)
    else:
        a, b = t.find("["), t.rfind("]")
        if a >= 0 and b > a:
            t = t[a:b + 1]
    try:
        obj = json.loads(t)
    except Exception:
        return []
    return obj if isinstance(obj, list) else []


async def _dream_llm_call(messages: list[dict], model: str, *, llm: Callable | None = None) -> str:
    """复用 task92 子代理 LLM 客户端（隔离上下文）；测试可注入 fake llm。"""
    if llm is not None:
        return await llm(messages, model=model)
    from app.ai.subagents.runner import _default_llm
    return await _default_llm(messages, model=model)


async def record_session(user_id: int) -> dict:
    """会话结束调用：累计会话计数；达标且过间隔则触发 Dream（fire-and-forget）。"""
    try:
        from app.database import get_redis
        r = get_redis()
        key = _SESSION_KEY.format(uid=int(user_id))
        cnt = await r.incr(key)
        last = await r.get(_LAST_KEY.format(uid=int(user_id)))
        age_h = float("inf")
        if last:
            try:
                age_h = (asyncio.get_event_loop().time() - float(last)) / 3600.0
            except Exception:
                age_h = float("inf")
        if cnt >= settings.DREAM_SESSION_INTERVAL and age_h >= settings.DREAM_MIN_AGE_HOURS:
            await r.set(_LAST_KEY.format(uid=int(user_id)), str(asyncio.get_event_loop().time()))
            await r.delete(key)
            asyncio.create_task(run_dream(int(user_id)))
            return {"triggered": True}
    except Exception as exc:
        logger.warning(f"[Dream] record_session 跳过（Redis 不可用）: {exc}")
    return {"triggered": False}


async def run_dream(user_id: int, *, llm: Callable | None = None, redis: Any = None,
                    dry_run: bool = False, store: Any = None) -> dict[str, Any]:
    """执行一次 Dream 巩固。

    Returns:
        {"acquired": bool, "consolidated": int, "entities": int, "dream_run_id": str, ...}
    """
    user_id = int(user_id)
    dream_run_id = f"dream-{uuid.uuid4().hex[:12]}"
    acquired = await _dream_lock.acquire(user_id, redis=redis)
    if not acquired:
        logger.info(f"[Dream] user={user_id} 未获锁，跳过（另一实例正在巩固）")
        return {"acquired": False, "consolidated": 0, "entities": 0, "dream_run_id": dream_run_id}

    try:
        from app.ai.memory.service import get_memory_store
        store = store or await get_memory_store()
        effective = await store._persistence.list_effective(user_id)
        if not effective:
            return {"acquired": True, "consolidated": 0, "entities": 0, "dream_run_id": dream_run_id,
                    "note": "no_effective_memories"}

        # 限制单次处理实体数，防长尾阻塞
        effective = effective[: settings.DREAM_MAX_ENTITIES_PER_RUN]
        mem_lines = "\n".join(
            f"- entity_id={m.id} [{m.memory_type}/{m.topic}] (importance={m.importance}): {m.content}"
            for m in effective
        )
        messages = [
            {"role": "system", "content": DREAM_SYSTEM_PROMPT},
            {"role": "user", "content": f"以下是用户 {user_id} 的当前有效长时记忆，请巩固升维：\n{mem_lines}"},
        ]
        raw = await _dream_llm_call(messages, settings.DREAM_MODEL, llm=llm)
        entries = _extract_json_array(raw)

        consolidated = 0
        entity_ids: list[int] = []
        for e in entries:
            try:
                content = (e.get("content") or "").strip()
                src = [int(x) for x in (e.get("source_entity_ids") or [])]
                if not content or not src:
                    continue
                # 仅合并本用户实际存在的有效实体
                valid_src = [s for s in src if any(m.id == s for m in effective)]
                if not valid_src:
                    continue
                new_eid = await store.consolidate(
                    source_entity_ids=valid_src,
                    summary_content=content,
                    memory_type=str(e.get("memory_type") or "profile"),
                    topic=str(e.get("topic") or "general"),
                    importance=int(e.get("importance") or 4),
                    operator="dream",
                    trace_id=dream_run_id,
                )
                consolidated += 1
                entity_ids.append(int(new_eid))
            except Exception as exc:
                logger.warning(f"[Dream] 单条巩固失败（跳过）: {exc}")

        logger.info(f"[Dream] user={user_id} 巩固完成：{consolidated} 条合并，run={dream_run_id}")
        return {
            "acquired": True, "consolidated": consolidated, "entities": len(entity_ids),
            "consolidated_ids": entity_ids, "dream_run_id": dream_run_id,
        }
    finally:
        await _dream_lock.release(user_id, redis=redis)
