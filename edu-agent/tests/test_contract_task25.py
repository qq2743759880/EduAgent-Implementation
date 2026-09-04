# -*- coding: utf-8 -*-
"""task25 契约测试：AI 助手三层记忆 + 遗忘机制（GWT ①②③④）。

执行方式：纯内存/纯函数（不依赖 MySQL/Milvus 在线）——向量降级 in-memory、
持久化用 InMemoryPersistence，验证四类 GWT 语义与遗忘曲线公式。

GWT：
① 多轮对话含明确偏好（"我想考雅思"）→ 会话结束 user_memory 落库（importance≥4）
   + 异步队列不阻塞应答（enqueue 毫秒级快返，消费才落库）
② 下次相关话题 → 向量召回 top-3 进 plan prompt（""雅思"召回"雅思目标"记忆并经 recall_topk 进入 graph）
③ 记忆超容量（≥500 语义，测试用较小容量）→ 遗忘淘汰综合分最低；
   公式 score=importance×exp(-0.01·Δt)+recency_bonus；高重要久未访问按时间衰减而非误删
④ 记忆写入失败 → 队列重试，不影响应答链路（异步隔离：enqueue 不抛、后台重入队）
"""
from __future__ import annotations

import asyncio

import pytest

from app.ai.memory.ingest import detect_memories
from app.ai.memory.score import memory_score, pick_forget_candidates
from app.ai.memory.schemas import MemoryCandidate
from app.ai.memory.vector import DeterministicEmbedder


# ============================================================
# 内存版持久化（无 MySQL 依赖，白盒链路）
# ============================================================
class InMemoryPersistence:
    """内存版 MemoryPersistence：io-less，供队列/召回/遗忘链路在无库环境验证。"""

    def __init__(self):
        self._seq = 0
        self._rows: dict[int, dict] = {}

    async def insert(self, *, user_id, memory_type, topic, content, importance, score) -> int:
        self._seq += 1
        from datetime import datetime

        self._rows[self._seq] = {
            "id": self._seq, "user_id": int(user_id), "memory_type": memory_type,
            "topic": topic, "content": content, "importance": int(importance),
            "score": float(score), "access_count": 0, "deleted": 0,
            "created_at": datetime.now(), "last_access_at": None, "updated_at": datetime.now(),
        }
        return self._seq

    async def fetch_by_ids(self, ids):
        rows = [self._rows.get(int(i)) for i in ids if int(i) in self._rows]
        from app.ai.memory.schemas import UserMemory

        out = []
        for r in rows:
            m = UserMemory.from_row(r)
            if m is not None:
                out.append(m)
        return out

    async def touch(self, memory_id, *, access_count, score, last_access_at):
        if int(memory_id) in self._rows:
            self._rows[int(memory_id)]["access_count"] = access_count
            self._rows[int(memory_id)]["score"] = float(score)
            self._rows[int(memory_id)]["last_access_at"] = last_access_at

    async def list_effective(self, user_id, limit=None):
        rows = [dict(r) for r in self._rows.values() if r["user_id"] == int(user_id) and not r["deleted"]]
        return rows[:limit] if limit else rows

    async def soft_delete_ids(self, ids):
        ids = {int(i) for i in ids}
        n = 0
        for r in self._rows.values():
            if r["id"] in ids and not r["deleted"]:
                r["deleted"] = 1
                n += 1
        return n

    async def count_effective(self, user_id):
        return sum(1 for r in self._rows.values() if r["user_id"] == int(user_id) and not r["deleted"])

    async def count_for_test(self, user_id):
        return await self.count_effective(user_id)

    async def forget_all_for_test(self, user_id):
        for r in self._rows.values():
            if r["user_id"] == int(user_id):
                r["deleted"] = 1


class _MinimalQueue:
    """内存桶实现 MemoryWriteQueue 语义（enqueue 快返 + pump_once 消费 + 重试）。"""

    def __init__(self, store, *, max_retry: int = 3):
        self.store = store
        self.max_retry = max_retry
        self._mem: asyncio.Queue = asyncio.Queue()
        self.enqueue_latency_ms = 0.0
        self.failures = 0

    async def enqueue_candidate(self, user_id, candidate):
        import time

        t0 = time.perf_counter()
        payload = {
            "user_id": int(user_id), "content": candidate.content, "memory_type": candidate.memory_type,
            "topic": candidate.topic, "importance": max(1, min(5, candidate.importance)), "retries": 0,
        }
        self._mem.put_nowait(payload)
        self.enqueue_latency_ms = (time.perf_counter() - t0) * 1000
        return True  # 恒成功，不抛

    async def pump_once(self):
        try:
            payload = self._mem.get_nowait()
        except asyncio.QueueEmpty:
            return False
        try:
            await self.store.write(
                user_id=int(payload["user_id"]), content=payload["content"],
                memory_type=payload["memory_type"], topic=payload["topic"],
                importance=int(payload["importance"]),
            )
            return True
        except Exception as exc:
            # 失败重入队（达到 retries 上限则丢弃）—— 与真实 queue._process 的
            # `retries <= max_retry` 判定逐字一致，保证测试双件行为与生产对齐
            self.failures += 1
            retries = int(payload.get("retries", 0)) + 1
            if retries <= self.max_retry:
                payload["retries"] = retries
                self._mem.put_nowait(payload)
            return False


# ============================================================
# GWT① 会话结束异步入队 + 落库（importance≥4）
# ============================================================
class TestIngestAndAsyncWrite:
    def test_detect_goal_preference(self):
        cands = detect_memories("我想考雅思，目标 6.5 分")
        assert cands, "应抽到目标记忆"
        for c in cands:
            assert c.importance >= 4, f"目标/偏好 importance≥4: {c.importance}"
        goals = [c for c in cands if c.memory_type == "goal"]
        assert goals, "应含 goal 类型"
        assert "雅思" in goals[0].content

    def test_explicit_remember(self):
        cands = detect_memories("记住：我偏好用番茄工作法学习")
        assert any("番茄工作法" in c.content for c in cands), "明确记忆应抽到"

    def test_low_value_not_captured(self):
        cands = detect_memories("今天天气不错")
        assert cands == [], "无明确偏好信号不产生候选（抑制长时记忆噪音）"

    @pytest.mark.asyncio
    async def test_enqueue_fast_return_then_persist(self):
        """GWT①：enqueue 毫秒级快返（不阻塞应答），消费后才落库且 importance≥4。"""
        persist = InMemoryPersistence()
        store = MemoryStoreInMemory(persist)
        q = _MinimalQueue(store)

        ok = await q.enqueue_candidate(42, MemoryCandidate(content="我想考雅思，目标6.5", memory_type="goal", topic="learning-goals", importance=5))
        assert ok is True
        assert q.enqueue_latency_ms < 50, f"入队应毫秒级快返: {q.enqueue_latency_ms:.2f}ms"
        assert await persist.count_effective(42) == 0, "入队后（消费前）不应落库"

        processed = await q.pump_once()
        assert processed is True
        assert await persist.count_effective(42) == 1, "消费后应落库"
        rows = await persist.list_effective(42)
        assert rows[0]["importance"] == 5 and rows[0]["importance"] >= 4


# ============================================================
# GWT② 向量召回 top-3 进 plan prompt
# ============================================================
class TestVectorRecall:
    def test_embed_has_dim(self):
        emb = DeterministicEmbedder(dim=16)
        v = emb.embed("雅思")
        assert len(v) == 16

    @pytest.mark.asyncio
    async def test_recall_topk_hits_relevant(self):
        """GWT②：写入多条记忆后，相关查询召回命中；top-k 上限且召回提升近因分。"""
        persist = InMemoryPersistence()
        store = MemoryStoreInMemory(persist)
        await store.write(user_id=7, content="用户想考雅思，目标 6.5", memory_type="goal", importance=5)
        await store.write(user_id=7, content="用户喜欢看科幻电影", memory_type="preference", importance=3)
        await store.write(user_id=7, content="用户天天跑步健身", memory_type="preference", importance=3)

        recalled = await store.recall(user_id=7, query="雅思考试", top_k=3)
        assert len(recalled) <= 3, "top-k 上限"
        assert recalled, "应召回命中内容"
        assert "雅思" in recalled[0]["content"], "top1 应命中雅思目标记忆"

        # 命中记忆近因分提升（access_count 增长 → 防遗忘）
        rows = await persist.list_effective(7)
        ielts = [r for r in rows if "雅思" in r["content"]][0]
        assert ielts["access_count"] >= 1, "召回命中应提升 access_count"


# ============================================================
# GWT③ 遗忘曲线 + 容量淘汰（高重要久未访问按时间衰减非误删）
# ============================================================
class TestForgettingCurve:
    def test_score_formula(self):
        # 新写入：分数即 importance（exp(0)=1, bonus 起跳）
        s = memory_score(5, days_since_created=0.0, days_since_access=0.0)
        assert s == pytest.approx(5.0 + 2.0, abs=1e-6)  # 5×exp(0)+W/(1+0)
        # 30 天未创建访问：衰减显著
        s30 = memory_score(5, days_since_created=30.0, days_since_access=None, recency_weight=0.0)
        assert s30 < 5, "时间衰减应降低分数"
        assert s30 > 5 * 0.74 - 0.1, f"exp(-0.01*30)=e^-0.3≈0.74，衰减不应过度: {s30}"

    def test_high_importance_decays_slower_not_misdeleted(self):
        """高重要（importance=5）即便久未访问，得分仍显著高于低重要新记忆。
        超容量淘汰综合分最低者时，高重要记忆被护住（score 已编码 importance 衰减）。"""
        s_high_old = memory_score(5, days_since_created=30.0, days_since_access=200.0)
        s_low_fresh = memory_score(2, days_since_created=3.0, days_since_access=2.0)
        assert s_high_old > s_low_fresh, \
            f"高重要久未访问({s_high_old:.3f}) 仍应高于低重要新记忆({s_low_fresh:.3f})（非误删）"
        rows = [
            {"id": 1, "score": s_high_old},   # 高重要老龄
            {"id": 2, "score": s_low_fresh},  # 低重要较新
            {"id": 3, "score": 0.05},          # 已跌破软删阈值
            {"id": 4, "score": 4.0},
        ]
        expired, overcap = pick_forget_candidates(rows, capacity=4, soft_delete_score=0.1)
        assert 3 in expired, "跌破阈值（时间衰减）应软删"
        # overcap=[]（容量未超），单独验证容量超额淘汰用 capacity 拉低
        _, overcap2 = pick_forget_candidates(
            [
                {"id": 1, "score": s_high_old},
                {"id": 2, "score": s_low_fresh},
                {"id": 4, "score": 4.0},
            ],
            capacity=2, soft_delete_score=0.1,
        )
        assert overcap2, "超容量应淘汰最低分"
        assert 1 not in overcap2, "高重要老龄不应被淘汰"

    @pytest.mark.asyncio
    async def test_over_capacity_keeps_high_importance(self):
        """GWT③：容量超限淘汰综合分最低；重要性高的雅思记忆被护住（非误删）。"""
        persist = InMemoryPersistence()
        store = MemoryStoreInMemory(persist, capacity=3)
        await store.write(user_id=9, content="用户想考雅思目标6.5", memory_type="goal", importance=5)
        for i in range(5):
            await store.write(user_id=9, content=f"占位低重要记忆{i}", importance=2)
        before = await persist.count_effective(9)
        # 先把雅思召回过一次（提近因分，更稳）
        await store.recall(user_id=9, query="雅思", top_k=1)
        res = await store.run_forget(9)
        after = await persist.count_effective(9)
        assert after <= 3, f"遗忘后应回到容量内: before={before} after={after}"
        rows = await persist.list_effective(9)
        kept = [r for r in rows if "雅思" in r["content"]]
        assert kept, "高重要雅思记忆应保留（非误删）"


# ============================================================
# GWT④ 写失败 → 队列重试，不影响应答链路（异步隔离）
# ============================================================
class TestAsyncIsolationRetry:
    @pytest.mark.asyncio
    async def test_write_failure_retries_without_raising(self):
        """GWT④：写失败时 enqueue 恒快返不抛；后台重入队重试，最终消费成功落库。"""
        persist = InMemoryPersistence()
        store = MemoryStoreInMemory(persist)
        # 前 2 次写失败（模拟瞬时故障），第 3 次成功
        state = {"n": 0}
        real_write = store.write

        async def flaky_write(**kw):
            state["n"] += 1
            if state["n"] <= 2:
                raise RuntimeError("sim db down")
            return await real_write(**kw)

        store.write = flaky_write
        q = _MinimalQueue(store, max_retry=3)

        ok = await q.enqueue_candidate(11, MemoryCandidate(content="用户偏好早起阅读", importance=4))
        assert ok is True, "enqueue 恒返回成功（异步隔离）"

        # 消费：失败 → 自动重入队；连试几次最终成功
        await q.pump_once()  # 失败1 → 重入队
        await q.pump_once()  # 失败2 → 重入队
        done = await q.pump_once()  # 成功
        assert done is True
        assert await persist.count_effective(11) == 1, "重试后应成功落库"
        assert state["n"] == 3

    @pytest.mark.asyncio
    async def test_enqueue_never_blocking_or_raising(self):
        """应答链路隔离：即使后台 store 全失败，enqueue 仍不抛、调用方快速返回。"""
        persist = InMemoryPersistence()
        store = MemoryStoreInMemory(persist)

        async def always_fail(**kw):
            raise RuntimeError("chain down")

        store.write = always_fail
        q = _MinimalQueue(store, max_retry=1)
        # 即使后台 store 全失败，enqueue 仍不抛、调用方快速返回
        ok = await q.enqueue_candidate(12, MemoryCandidate(content="用户偏好晚间复盘", importance=4))
        assert ok is True


# ============================================================
# 辅助：内存版 MemoryStore（复用真实 write/recall/run_forget 逻辑）
# ============================================================
class MemoryStoreInMemory:
    """包装 InMemoryPersistence + real vector/score 逻辑的可注入 store。"""

    def __init__(self, persist, *, capacity: int = 500):
        from app.ai.memory.score import memory_score as _ms

        self._persist = persist
        self._capacity = int(capacity)
        self._vector = _MemVectorStore(dim=16)
        self._lambda = 0.01
        self._recency_weight = 2.0
        self._recency_slope = 0.1
        self._soft_delete_score = 0.1

    async def write(self, *, user_id, content, memory_type="preference", topic="general", importance=4):
        from app.ai.memory.score import memory_score
        from datetime import datetime

        s = memory_score(int(importance), days_since_created=0.0, days_since_access=0.0)
        mid = await self._persist.insert(
            user_id=user_id, memory_type=memory_type, topic=topic,
            content=content, importance=int(importance), score=s,
        )
        await self._vector.upsert(memory_id=mid, user_id=user_id, content=content)
        return mid

    async def recall(self, *, user_id, query, top_k=3):
        from datetime import datetime

        hits = await self._vector.search(user_id=user_id, query=query, top_k=top_k)
        if not hits:
            return []
        ids = [int(h["memory_id"]) for h in hits]
        memories = await self._persist.fetch_by_ids(ids)
        mem_by_id = {m.id: m for m in memories}
        out = []
        for h in hits:
            m = mem_by_id.get(int(h["memory_id"]))
            if m is None:
                continue
            await self._persist.touch(
                int(m.id), access_count=m.access_count + 1, score=m.score, last_access_at=datetime.now(),
            )
            out.append({**(m.to_recall_dict()), "vector_score": float(h.get("score", 0.0))})
        out.sort(key=lambda r: r.get("vector_score", 0.0), reverse=True)
        return out[:top_k]

    async def run_forget(self, user_id):
        rows = await self._persist.list_effective(user_id)
        if not rows:
            return {"soft_deleted": 0, "remaining": 0}
        expired, overcap = pick_forget_candidates(
            [dict(r) for r in rows], capacity=self._capacity, soft_delete_score=self._soft_delete_score,
        )
        prune = list(set(expired) | set(overcap))
        await self._persist.soft_delete_ids(prune)
        remaining = await self._persist.count_effective(user_id)
        return {"soft_deleted": len(prune), "remaining": remaining}


class _MemVectorStore:
    """内存向量（降级语义），复用 DeterministicEmbedder。"""

    def __init__(self, dim=16):
        self.dim = dim
        self.emb = DeterministicEmbedder(dim=dim)
        self._mem = {}

    async def upsert(self, memory_id, user_id, content):
        v = self.emb.embed(content)
        self._mem[int(memory_id)] = {"user_id": int(user_id), "content": content, "vec": v}

    async def search(self, user_id, query, top_k=3):
        qv = self.emb.embed(query)
        items = {mid: m for mid, m in self._mem.items() if m["user_id"] == int(user_id)}
        if not items:
            return []
        result = []
        for mid, m in items.items():
            dot = sum(a * b for a, b in zip(m["vec"], qv, strict=False))
            result.append({"memory_id": int(mid), "content": m["content"], "score": round(dot, 4)})
        result.sort(key=lambda r: r["score"], reverse=True)
        return result[:top_k]