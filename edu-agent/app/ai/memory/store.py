"""三层记忆 - 核心服务 MemoryStore（task25 R7）。

职责（GWT ①②③ 全覆盖）：
- `write`：写长时记忆（importance≥4 由 ingest 把关，此处落 user_memory + 向量）。GWT①。
- `recall`：向量召回 top-k 进 plan prompt（GWT②），并提升 access_count/last_access_at/score（近因）。
- `run_forget`：每用户超容量 → 淘汰综合分最低（score 升序补容量）；score<阈值 → 时间衰减软删（GWT③）。
- `prune_if_over`：写入后便捷守卫（单写即触发检查，防长时积压）。

降级：向量 store 不可达 → in-memory；持久化不可达 → in-memory。三者均保证在无外部存储机上可用。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from loguru import logger

from app.ai.memory.schemas import UserMemory
from app.ai.memory.score import days_since, memory_score, prune_ids_for_user
from app.ai.memory.vector import MemoryVectorStore


class MemoryStore:
    """记忆逻辑编排（持久化 + 向量 + 评分）。可用依赖注入做无外部环境测试。"""

    def __init__(
        self,
        persistence: Any,
        vector_store: MemoryVectorStore | None = None,
        *,
        capacity: int | None = None,
        soft_delete_score: float | None = None,
        decay_lambda: float | None = None,
        recency_weight: float | None = None,
        recency_slope: float | None = None,
    ) -> None:
        from app.config import settings

        self._persistence = persistence
        self._vector = vector_store or MemoryVectorStore()
        self._capacity = int(capacity if capacity is not None else settings.MEMORY_CAPACITY_PER_USER)
        self._soft_delete_score = float(soft_delete_score if soft_delete_score is not None else settings.MEMORY_SOFT_DELETE_SCORE)
        self._lambda = float(decay_lambda if decay_lambda is not None else settings.MEMORY_DECAY_LAMBDA)
        self._recency_weight = float(recency_weight if recency_weight is not None else settings.MEMORY_RECENCY_WEIGHT)
        self._recency_slope = float(recency_slope if recency_slope is not None else settings.MEMORY_RECENCY_SLOPE)

    # ------------------------------------------------------------------
    async def write(
        self,
        *,
        user_id: int,
        content: str,
        memory_type: str = "preference",
        topic: str = "general",
        importance: int = 4,
    ) -> int:
        """写入一条长时记忆（事实源 + 向量）。返回 memory_id。"""
        if not (content or "").strip():
            logger.warning("[Memory] 拒绝写空 content")
            return -1
        importance = max(1, min(5, int(importance)))
        initial_score = memory_score(
            importance, days_since_created=0.0, days_since_access=0.0,
            lambda_=self._lambda, recency_weight=self._recency_weight,
            recency_slope=self._recency_slope,
        )
        memory_id = await self._persistence.insert(
            user_id=int(user_id), memory_type=memory_type[:32], topic=topic[:64],
            content=(content or "")[:2000], importance=importance, score=initial_score,
        )
        # 向量 upsert（失败不影响事实源落库——向量纯为召回加速）
        try:
            await self._vector.upsert(
                memory_id=int(memory_id), user_id=int(user_id), content=content[:2000]
            )
        except Exception as exc:
            logger.warning(f"[Memory] 向量 upsert 失败（仍已落库）: {exc}")
        logger.info(f"[Memory] 写入记忆 user={user_id} id={memory_id} type={memory_type} imp={importance}")
        return int(memory_id)

    # ------------------------------------------------------------------
    async def recall(self, *, user_id: int, query: str, top_k: int = 3,
                     valid_only: bool = True) -> list[dict[str, Any]]:
        """向量召回 top-k 记忆，并提升命中记忆的近因分/访问次数（GWT②：命中记忆进 plan prompt）。

        task-M1：检索恒经 `user_memory_event WHERE valid_to IS NULL AND event_type<>'delete'` 过滤
        （`fetch_by_ids` 内部强制），即 valid_only=True 为不可关闭的硬约束（对应 AC2：废弃版本永不召回）。
        """
        k = max(1, int(top_k if top_k is not None else 3))
        hits = await self._vector.search(user_id=int(user_id), query=query, top_k=k)
        if not hits:
            return []
        ids = [int(h["memory_id"]) for h in hits if h.get("memory_id")]
        memories = await self._persistence.fetch_by_ids(ids)
        # 按向量排序复原
        mem_by_id = {m.id: m for m in memories}
        now = datetime.now()
        out: list[dict[str, Any]] = []
        for h in hits:
            m = mem_by_id.get(int(h["memory_id"]))
            if m is None:
                continue
            # 近因提升：更新访问痕迹 + 重算综合分（时间越近分越高，防被遗忘）
            new_count = m.access_count + 1
            d_created = days_since(now, m.created_at)
            d_access = days_since(now, m.last_access_at if m.last_access_at is not None else m.created_at)
            new_score = memory_score(
                m.importance, days_since_created=d_created, days_since_access=d_access,
                lambda_=self._lambda, recency_weight=self._recency_weight,
                recency_slope=self._recency_slope,
            )
            try:
                await self._persistence.touch(
                    int(m.id), access_count=new_count, score=new_score, last_access_at=now
                )
            except Exception:
                pass
            m.access_count = new_count
            m.last_access_at = now
            m.score = new_score
            out.append({**(m.to_recall_dict()), "vector_score": float(h.get("score", 0.0))})
        out.sort(key=lambda r: r.get("vector_score", 0.0), reverse=True)
        return out[:k]

    # ------------------------------------------------------------------
    async def run_forget(self, user_id: int) -> dict[str, int]:
        """遗忘任务（GWT③）：软删 score<阈值 的时间衰减记忆；仍超容量则淘汰综合分最低补容量。

        Returns:
            {"soft_deleted_by_decay":n, "soft_deleted_over_cap":n, "remaining":n}
        """
        rows = await self._persistence.list_effective(int(user_id), limit=None)
        if not rows:
            return {"soft_deleted_by_decay": 0, "soft_deleted_over_cap": 0, "remaining": 0}
        now = datetime.now()
        row_dicts = [
            {
                "id": r.id,
                "importance": r.importance,
                "score": r.score,
                # 传入真实已衰减分：持久化 score 在 touch 时已更新；此处以库值为主、兜底重算
                "created_at": r.created_at,
                "last_access_at": r.last_access_at,
            }
            for r in rows
        ]
        # 若库中 score 未刷新，按当前时间重算兜底（保证遗忘选择基于最新衰减）
        for rd in row_dicts:
            d_created = days_since(now, rd["created_at"])
            d_access = days_since(now, rd["last_access_at"] if rd["last_access_at"] is not None else rd["created_at"])
            computed = memory_score(
                rd["importance"], days_since_created=d_created, days_since_access=d_access,
                lambda_=self._lambda, recency_weight=self._recency_weight,
                recency_slope=self._recency_slope,
            )
            rd["score"] = min(rd["score"], computed)  # 取更保守（更易被遗忘）的衰减值

        prune_ids = prune_ids_for_user(
            row_dicts, capacity=self._capacity, soft_delete_score=self._soft_delete_score
        )
        try:
            await self._persistence.soft_delete_ids(prune_ids)
        except Exception as exc:
            logger.warning(f"[Memory] 遗忘软删失败: {exc}")
        remaining = await self._persistence.count_effective(int(user_id))
        return {
            "soft_deleted": len(prune_ids),
            "remaining": remaining,
        }

    async def prune_if_over(self, user_id: int) -> dict[str, int] | None:
        """一次性守卫：仅当超容量才跑遗忘；否则快速返回。"""
        cnt = await self._persistence.count_effective(int(user_id))
        if cnt <= self._capacity:
            return None
        logger.info(f"[Memory] user={user_id} 记忆 {cnt} 超容量 {self._capacity}，触发遗忘")
        return await self.run_forget(user_id)

    # ==================================================================
    # 事件溯源操作（task-M1：append-only / 版本盖章 / 回滚 / 巩固）
    # ==================================================================
    async def _sync_vector(self, entity_id: int, content: str | None) -> None:
        """向量与事件 HEAD 同步：content=None → 删向量；否则 upsert（主键=entity_id）。"""
        try:
            if content is None:
                await self._vector.delete(int(entity_id))
            else:
                head = await self._persistence.fetch_entity(int(entity_id))
                uid = int(head.user_id) if head else 0
                await self._vector.upsert(memory_id=int(entity_id), user_id=uid, content=content[:2000])
        except Exception as exc:
            logger.warning(f"[Memory] 向量同步失败（事实源已落库）: {exc}")

    async def update_memory(
        self, *, entity_id: int, content: str,
        memory_type: str | None = None, topic: str | None = None,
        importance: int | None = None, operator: str = "user", trace_id: str | None = None,
    ) -> int:
        """更新某记忆实体：新行 + 旧行 valid_to 盖章（不 UPDATE 内容）。返回 entity_id。"""
        new_eid = await self._persistence.update_memory(
            int(entity_id), content=content, memory_type=memory_type, topic=topic,
            importance=importance, operator=operator, trace_id=trace_id,
        )
        await self._sync_vector(int(entity_id), content)
        return int(new_eid)

    async def rewind(self, *, entity_id: int, target_event_id: int,
                     operator: str = "user", trace_id: str | None = None) -> int:
        """回滚到 target_event_id 版本：追加 rewind 事件，HEAD 指向目标内容（ChronoMem 语义）。"""
        new_eid = await self._persistence.rewind(
            int(entity_id), int(target_event_id), operator=operator, trace_id=trace_id,
        )
        head = await self._persistence.fetch_entity(int(entity_id))
        await self._sync_vector(int(entity_id), head.content if head else None)
        return int(new_eid)

    async def delete_memory(self, *, entity_id: int,
                            operator: str = "user", trace_id: str | None = None) -> None:
        """软删某记忆实体（事件溯源：盖章 + 追加 delete 事件）。"""
        await self._persistence.invalidate(int(entity_id), operator=operator, trace_id=trace_id)
        await self._sync_vector(int(entity_id), None)

    async def consolidate(
        self, *, source_entity_ids: list[int], summary_content: str,
        memory_type: str = "profile", topic: str = "general",
        importance: int = 4, operator: str = "dream", trace_id: str | None = None,
    ) -> int:
        """Dream 巩固：把若干源实体合并为一条 consolidate 事件，源 HEAD 盖章废弃。返回新 entity_id。"""
        # 取首个源实体的 user_id（同一用户巩固；如为空则 0 兜底）
        user_id = 0
        for sid in source_entity_ids:
            head = await self._persistence.fetch_entity(int(sid))
            if head is not None:
                user_id = int(head.user_id)
                break
        new_eid = await self._persistence.consolidate(
            [int(i) for i in source_entity_ids], user_id=user_id, summary_content=summary_content,
            memory_type=memory_type, topic=topic, importance=int(importance),
            operator=operator, trace_id=trace_id, supports=[int(i) for i in source_entity_ids],
        )
        await self._sync_vector(int(new_eid), summary_content)
        # task-M2 AC3：源实体已盖章废弃（valid_to 已置），同步移除其向量索引，
        # 使 search 永不返回已被 Dream 合并掉的旧记忆（无论后端是 milvus/redis/memory）。
        for sid in source_entity_ids:
            try:
                await self._vector.invalidate(int(sid))
            except Exception as exc:
                logger.warning(f"[Memory] 巩固源向量失效失败（忽略）: {exc}")
        return int(new_eid)

    async def history(self, *, entity_id: int, limit: int = 50, offset: int = 0) -> list[dict]:
        """事件流历史（审计/回滚 UI 用）。"""
        return await self._persistence.history(int(entity_id), limit=int(limit), offset=int(offset))

    # ------------------------------------------------------------------
    async def count(self, user_id: int) -> int:
        return await self._persistence.count_effective(int(user_id))

    async def forget_all_for_test(self, user_id: int) -> None:
        """仅供测试：清空该用户记忆（物理非破坏，全部软删）。"""
        rows = await self._persistence.list_effective(int(user_id))
        await self._persistence.soft_delete_ids([r.id for r in rows])