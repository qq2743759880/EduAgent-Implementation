"""三层记忆 - 向量召回（task25 R7 + task-VEC 真实向量化）。

- `SemanticEmbedder`：对记忆/查询文本编码稠密向量。
    * **真实语义**：复用 `app.knowledge.importer.embedder.encode_dense_batch`
      （本地 BGE-M3，EMBED_DEVICE=cuda，1024 维），不伪造。
    * **降级链**：BGE-M3 不可用 / encode 抛异常 → 回落 `DeterministicEmbedder`
      （char 2-gram 哈希，1024 维）并置 `degraded_reason`，不 500（GWT③）。
      ※ 降级维度统一 1024（=EMBEDDING_DIM / Milvus user_memory schema），
        避免旧 MEMORY_VECTOR_DIM=512 与 Milvus 1024 混用导致 upsert 维度不匹配。
- `MemoryVectorStore`：vector recall 存储。
    * backend=milvus：`user_memory` collection，按 user_id 过滤，写入真实 Milvus
      （client 经 `loader.get_milvus_client()` 全局单例，唯一 Milvus 入口，不旁路 pymilvus）；
    * backend=redis：跨实例共享向量（HSET 向量 + ZSET 索引 + owner 反向映射），多实例召回一致；
    * backend=memory：in-process dict（Milvus 与 Redis 均不可达时最后兜底）。
降级链：`milvus → redis → memory`（任一不可达自动落到下一档，不 500）。
两种 backend 对外统一 `upsert/search/delete` 接口，调用方无感知。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
from typing import Any

from app.monitoring.metrics import record_degraded as _record_degraded
from app.core.db_resilience import DependencyUnavailableError, redis_run  # task-P1C Redis 断连熔断

from loguru import logger

from app.config import settings


def _dim() -> int:
    """向量维度：统一 1024（=EMBEDDING_DIM / Milvus user_memory schema）。

    task-VEC 修复：不再用 MEMORY_VECTOR_DIM(512)。BGE-M3 实际输出 1024 维，
    若降级哈希用 512 维，Milvus(1024) upsert 会维度不匹配失败——这正是以前
    user_memory 写不进去的根因之一。统一 1024 保证真实/降级向量始终可入库可检索。
    """
    return int(getattr(settings, "EMBEDDING_DIM", 1024) or 1024)


class DeterministicEmbedder:
    """离线确定性向量编码（无外部依赖，降级/无 CUDA 环境兜底）。

    对文本做字符 2-gram，每个 gram 经 md5 散列到 [0, DIM) 桶，按哈希字节符号写入桶再做 L2 归一化，
    得到稳定、同分布、可比较余弦相似度的向量。不要求语义粒度，只保证「相似文本→更高余弦」。
    """

    def __init__(self, dim: int | None = None) -> None:
        self.dim = dim if dim is not None else _dim()

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        text = (text or "").strip()
        if not text:
            vec[0] = 1.0
            return vec
        grams: list[str] = []
        # unigram（含空白归一）
        for ch in text.lower():
            grams.append(ch)
        # char bigram
        for i in range(len(text) - 1):
            grams.append(text[i : i + 2].lower())
        for g in grams:
            h = hashlib.md5(g.encode("utf-8")).digest()[:8]
            bucket = int.from_bytes(h, "little") % self.dim
            sign = 1.0 if h[0] % 2 == 0 else -1.0
            vec[bucket] += sign
        # L2 归一化
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 1e-9:
            vec = [v / norm for v in vec]
        return vec

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class SemanticEmbedder:
    """真实语义 embedder：优先 BGE-M3（CUDA 1024 维），失败降级哈希并标注。

    - 复用 `app.knowledge.importer.embedder.encode_dense_batch`（BGE 模型全局缓存复用，
      二次调用不重复加载 2.2GB 权重；BGE 可用时走本地 GPU，不产生 DeepSeek LLM 费用）。
    - `degraded_reason`：非 None 表示本次嵌入走了降级哈希，如实标注原因（GWT③）。
    - 任意时刻 BGE 不可用 → 返回 1024 维哈希向量，抛不异常、不 500。
    """

    def __init__(self, dim: int | None = None, encode_fn=None) -> None:
        self.dim = dim if dim is not None else _dim()
        self._fallback = DeterministicEmbedder(dim=self.dim)
        self._encode_fn = encode_fn  # 供契约测试注入可控函数
        self.degraded_reason: str | None = None

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            if self._encode_fn is not None:
                vecs = self._encode_fn(texts)
            else:
                from app.knowledge.importer import embedder as _emb

                # 先探测本地 BGE-M3 可用性（GWT③ 关键修复）：
                # encode_dense_batch 内部会吞掉异常并自行降级到 Embedding API / 伪向量，
                # 永不 raise，因此本类的 except 分支在"真实 BGE 不可用"时不会触发，
                # degraded_reason 会形同虚设、且可能非预期消耗付费 Embedding API。
                # 故在调用前主动探测（_get_bge_model 全局缓存复用，不重复加载 2.2GB）：
                # 模型缺失/加载失败 → 直接降级哈希并如实标注，不 500（R-独立审查 P1）。
                if _emb._get_bge_model() is None:
                    raise RuntimeError(
                        f"BGE-M3 不可用（模型缺失/加载失败 {getattr(settings, 'BGE_M3_PATH', '')}）"
                    )
                vecs = _emb.encode_dense_batch(texts)
            # 归一为 python float，并校验维度与 Milvus 对齐
            out = [[float(x) for x in v] for v in vecs]
            if all(len(v) == self.dim for v in out):
                self.degraded_reason = None
                return out
            self.degraded_reason = f"真实 embedding 维度不为 {self.dim}（{sorted(set(map(len, out)))})，降级哈希"
            logger.warning(f"[Memory:semantic] {self.degraded_reason}")
        except Exception as exc:
            self.degraded_reason = f"BGE-M3 不可用: {type(exc).__name__}: {exc}"
            logger.warning(f"[Memory:semantic] {self.degraded_reason} → 降级哈希（dim={self.dim}）")
        return self._fallback.embed_batch(texts)


class MemoryVectorStore:
    """记忆向量库：统一 upsert/search/delete；backend='milvus'|'memory' 自动选择。"""

    def __init__(
        self,
        *,
        milvus_uri: str | None = None,
        dim: int | None = None,
        embedder=None,
        redis: Any = None,
    ) -> None:
        self.dim = dim if dim is not None else _dim()
        # 默认注入真实语义 embedder；测试可传自定义 embedder（如强制降级的 mock）
        self.embedder = embedder if embedder is not None else SemanticEmbedder(dim=self.dim)
        self._mem: dict[int, dict[str, Any]] = {}            # memory_id -> {user_id, content, vec}
        self._mem_lock = asyncio.Lock()
        self.backend: str = "memory"
        self._milvus: Any = None
        self._redis: Any = redis  # 可注入（测试用共享 fake；生产走 app.database.get_redis）
        self._collection: str = str(
            getattr(settings, "MILVUS_MEMORY_COLLECTION", "user_memory")
        )
        self.key_prefix: str = str(
            getattr(settings, "MEMORY_REDIS_VEC_KEY_PREFIX", "memory:vec")
        )
        self.scan_limit: int = int(getattr(settings, "MEMORY_REDIS_SCAN_LIMIT", 2000))
        self.degraded_reason: str | None = None  # 最近一次 upsert/search 的降级标注（GWT③）
        self._try_init_milvus(milvus_uri)
        # 降级链：milvus 不可达才尝试 redis；redis 也不可达则 memory
        if self.backend != "milvus":
            self._try_init_redis()

    def _resolve_embed(self, texts: list[str]) -> list[list[float]]:
        """统一向量入口：嵌入并同步降级标注到 store 级（GWT③ 可观测）。"""
        vecs = self.embedder.embed_batch(texts)
        self.degraded_reason = getattr(self.embedder, "degraded_reason", None)
        return vecs

    def _try_init_milvus(self, milvus_uri: str | None) -> None:
        # 显式传 "" = 禁用 Milvus（强制 in-memory）；None = 采用 settings.MILVUS_URI 默认值
        if milvus_uri is None:
            milvus_uri = getattr(settings, "MILVUS_URI", "") or ""
        uri = (milvus_uri or "").strip()
        if not uri:
            logger.info("[Memory:vector] 无 Milvus URI，降级 in-memory 向量")
            return
        try:
            # 复用 loader 唯一 Milvus 入口（全局单例 + 3s 超时兜底），不旁路 pymilvus
            from app.knowledge.importer.loader import get_milvus_client

            client = get_milvus_client()
            client.list_collections()  # 轻量连通探测
            self._milvus = client
            _ensure_milvus_collection(client, self._collection, self.dim)
            # 校验现有 schema 维度是否对齐，避免维度不匹配静默失败
            _verify_collection_dim(client, self._collection, self.dim)
            self.backend = "milvus"
            logger.info(f"[Memory:vector] 已连接 Milvus（backend=milvus, dim={self.dim}）")
        except Exception as exc:
            self._milvus = None
            self.backend = "memory"
            logger.warning(
                f"[Memory:vector] Milvus 不可达/维度不符，降级 in-memory 向量：{type(exc).__name__}: {exc}"
            )

    # --- Redis 共享向量（降级链第 2 档）---
    def _try_init_redis(self) -> None:
        """milvus 不可达时，尝试接入 Redis 共享向量；拿不到客户端则标记 memory 兜底。

        ponytail：sync __init__ 内不 await ping（redis ping 是协程），可达性延迟到首次
        IO 时由 `_redis_ok` 探测；此处仅按"客户端是否可取"决定 backend 档位。
        """
        if self._redis is None:
            try:
                from app.database import get_redis

                self._redis = get_redis()
            except Exception as exc:  # 未 init_redis() 等 → 无客户端
                self._redis = None
        if self._redis is not None:
            self.backend = "redis"
        else:
            self.backend = "memory"
            self.degraded_reason = "redis_unreachable"
            logger.warning("[Memory:vector] 无 Redis 客户端，降级 in-memory 向量（degraded_reason=redis_unreachable）")
            _record_degraded("redis", "memory_vector_no_client")

    async def _redis_ok(self) -> bool:
        """运行时可达性探测：不可达则降级 memory 并标注（ponytail: 真实 ping 在 async 路径）。

        task-P1C：ping 经 redis_run 熔断保护——Redis 断连连续失败 → OPEN 后毫秒级返回 False，
        不再傻等 socket 超时（task39 实测 AI 问答 22s→52.4s 的部分根因）。
        """
        if self._redis is None:
            return False
        try:
            await redis_run("memory_vector_ping", lambda: self._redis.ping())
            return True
        except DependencyUnavailableError:
            # 熔断中：快速判定不可达，走降级（不触达 Redis）
            self._redis = None
            self.backend = "memory"
            self.degraded_reason = "redis_unreachable"
            _record_degraded("redis", "memory_vector_breaker_open")
            return False
        except Exception as exc:
            logger.warning(f"[Memory:vector] Redis 心跳失败，降级 in-memory 向量：{type(exc).__name__}: {exc}")
            self._redis = None
            self.backend = "memory"
            self.degraded_reason = "redis_unreachable"
            # task39 GWT②：Redis 断连 → 记忆向量落 in-process（§6.4 Redis 行）
            _record_degraded("redis", f"memory_vector_ping_failed:{type(exc).__name__}")
            return False

    def _vec_key(self, user_id: int) -> str:
        return f"{self.key_prefix}:{int(user_id)}"

    def _idx_key(self, user_id: int) -> str:
        return f"{self.key_prefix}:idx:{int(user_id)}"

    def _owner_key(self) -> str:
        # owner 反向映射：memory_id -> user_id（删除时无需已知 user_id）
        return f"{self.key_prefix}:owner"

    async def _redis_upsert(
        self, *, memory_id: int, user_id: int, vector: list[float], importance: float = 1.0
    ) -> None:
        async def _do():
            r = self._redis
            await r.hset(self._vec_key(user_id), str(int(memory_id)), json.dumps(vector))
            await r.zadd(self._idx_key(user_id), {str(int(memory_id)): float(importance)})
            await r.hset(self._owner_key(), str(int(memory_id)), str(int(user_id)))
        # task-P1C：熔断中快速失败，由上层 upsert 的 except 接管降级 in-memory
        await redis_run("memory_vector_upsert", _do)

    async def _redis_delete(self, memory_id: int) -> None:
        async def _do():
            r = self._redis
            mid = str(int(memory_id))
            owner = await r.hget(self._owner_key(), mid)
            if owner is not None:
                uid = int(owner)
                await r.hdel(self._vec_key(uid), mid)
                await r.zrem(self._idx_key(uid), mid)
            await r.hdel(self._owner_key(), mid)
        await redis_run("memory_vector_delete", _do)

    async def _redis_search(
        self, *, user_id: int, query_vec: list[float], top_k: int
    ) -> list[dict[str, Any]]:
        async def _do() -> list[dict[str, Any]]:
            r = self._redis
            members = await r.zrange(self._idx_key(user_id), 0, -1)
            members = members[: self.scan_limit]  # 防大 key（MEMORY_REDIS_SCAN_LIMIT）
            if not members:
                return []
            vals = await r.hmget(self._vec_key(user_id), members)
            result: list[dict[str, Any]] = []
            for mb, vb in zip(members, vals):
                if vb is None:
                    continue
                vec = json.loads(vb)
                dot = float(sum(a * b for a, b in zip(vec, query_vec, strict=False)))
                result.append({"memory_id": int(mb), "content": "", "score": round(dot, 4)})
            result.sort(key=lambda x: x["score"], reverse=True)
            return result[: int(top_k)] if top_k > 0 else result
        # task-P1C：熔断中快速失败，由上层 search 的 except 接管降级 in-memory
        return await redis_run("memory_vector_search", _do)

    # --- 统一接口 ---
    async def upsert(
        self,
        *,
        memory_id: int,
        user_id: int,
        content: str,
        vector: list[float] | None = None,
        importance: float = 1.0,
    ) -> None:
        if vector is None:
            vector = self._resolve_embed([content])[0]
        if self.backend == "milvus" and self._milvus is not None:
            try:
                self._milvus.upsert(
                    collection_name=self._collection,
                    data=[
                        {
                            "id": int(memory_id),
                            "user_id": int(user_id),
                            "content": content,
                            "vector": vector,
                        }
                    ],
                )
                return
            except Exception as exc:
                logger.warning(f"[Memory:vector] Milvus upsert 失败，转下一档：{exc}")
        if self.backend == "redis" and await self._redis_ok():
            try:
                await self._redis_upsert(
                    memory_id=int(memory_id), user_id=int(user_id),
                    vector=list(vector), importance=float(importance),
                )
                return
            except Exception as exc:
                logger.warning(f"[Memory:vector] Redis upsert 失败，转 in-memory：{exc}")
        async with self._mem_lock:
            self._mem[int(memory_id)] = {"user_id": int(user_id), "content": content, "vec": list(vector)}

    async def delete(self, memory_id: int) -> None:
        if self.backend == "milvus" and self._milvus is not None:
            try:
                self._milvus.delete(collection_name=self._collection, ids=[int(memory_id)])
                return
            except Exception as exc:
                logger.warning(f"[Memory:vector] Milvus delete 失败，转下一档：{exc}")
        if self.backend == "redis" and await self._redis_ok():
            try:
                await self._redis_delete(int(memory_id))
                return
            except Exception as exc:
                logger.warning(f"[Memory:vector] Redis delete 失败，转 in-memory delete：{exc}")
        async with self._mem_lock:
            self._mem.pop(int(memory_id), None)

    async def invalidate(self, memory_id: int) -> None:
        """task-M2 AC3：valid_to 盖章 / 删除联动 → 从所有后端移除该 memory_id 向量。"""
        await self.delete(int(memory_id))

    async def search(
        self, *, user_id: int, query: str, top_k: int = 3
    ) -> list[dict[str, Any]]:
        """返回向量召回结果 [{memory_id, content, score}]（cosine 降序，取 top_k）。"""
        qv = self._resolve_embed([query])[0]
        if self.backend == "milvus" and self._milvus is not None:
            try:
                res = self._milvus.search(
                    collection_name=self._collection,
                    data=[qv],
                    limit=int(top_k),
                    filter=f"user_id == {int(user_id)}",
                    output_fields=["content"],
                )
                hits = res[0] if res else []
                return [
                    {
                        # Milvus 主键 id 即 user_memory.id（memory_id）
                        "memory_id": int(hit.get("id", 0)),
                        "content": hit.get("entity", {}).get("content", ""),
                        "score": float(hit.get("distance", 0.0)),
                    }
                    for hit in hits
                ]
            except Exception as exc:
                logger.warning(f"[Memory:vector] Milvus search 失败，转下一档：{exc}")
        if self.backend == "redis" and await self._redis_ok():
            try:
                return await self._redis_search(
                    user_id=int(user_id), query_vec=qv, top_k=int(top_k)
                )
            except Exception as exc:
                logger.warning(f"[Memory:vector] Redis search 失败，转 in-memory retrieval：{exc}")
        # in-memory cosine
        async with self._mem_lock:
            items = {mid: m for mid, m in self._mem.items() if m["user_id"] == int(user_id)}
        if not items:
            return []
        result: list[dict[str, Any]] = []
        for mid, m in items.items():
            v = m["vec"]
            # cosine（向量已归一化 → 点积即余弦）
            dot = float(sum(a * b for a, b in zip(v, qv, strict=False)))
            result.append({"memory_id": int(mid), "content": m["content"], "score": round(dot, 4)})
        result.sort(key=lambda r: r["score"], reverse=True)
        return result[: int(top_k)] if top_k > 0 else result

    async def clear_user(self, user_id: int) -> None:
        """测试/管理用：清空某用户向量。"""
        if self.backend == "milvus" and self._milvus is not None:
            try:
                self._milvus.delete(collection_name=self._collection, filter=f"user_id == {int(user_id)}")
                return
            except Exception:
                pass
        if self.backend == "redis" and await self._redis_ok():
            try:
                r = self._redis
                members = await r.zrange(self._idx_key(user_id), 0, -1)
                for mb in members:
                    await r.hdel(self._owner_key(), str(mb))
                await r.delete(self._vec_key(user_id))
                await r.delete(self._idx_key(user_id))
                return
            except Exception as exc:
                logger.warning(f"[Memory:vector] Redis clear_user 失败，转 in-memory：{exc}")
        async with self._mem_lock:
            self._mem = {mid: m for mid, m in self._mem.items() if m["user_id"] != int(user_id)}


def _ensure_milvus_collection(client: Any, collection_name: str, dim: int) -> None:
    """惰性建 user_memory collection（幂等；已存在则跳过，配合 _verify_collection_dim 校验）。"""
    cols = client.list_collections()
    if collection_name in cols:
        return
    from pymilvus import DataType

    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("id", DataType.INT64, is_primary=True)
    schema.add_field("user_id", DataType.INT64)
    schema.add_field("content", DataType.VARCHAR, max_length=2000)
    schema.add_field("vector", DataType.FLOAT_VECTOR, dim=int(dim))
    index_params = client.prepare_index_params()
    index_params.add_index(field_name="vector", index_type="AUTOINDEX", metric_type="COSINE")
    client.create_collection(collection_name, schema=schema, index_params=index_params, timeout=float(getattr(settings, "MILVUS_SEARCH_TIMEOUT", 8.0)))
    # 新建集合后须显式 load，否则 search 会报 "collection not loaded"（R-独立审查 P2）
    client.load_collection(collection_name)


def _verify_collection_dim(client: Any, collection_name: str, expected_dim: int) -> None:
    """校验现有 collection 的 vector 字段维度与期望一致；不一致抛错 → 上层降级内存。

    task-VEC：user_memory schema 若仍为旧 512 维，需重建 1024。此处不做破坏性 drop，
    仅检测并如实抛错，由调用方记录"维度不符需重建"。当前实证 schema 已是 1024，通常不会触发。
    """
    desc = client.describe_collection(collection_name)
    for f in desc.get("fields", []):
        if f.get("name") == "vector":
            params = f.get("params") or {}
            dim = int(params.get("dim") or 0)
            if dim != int(expected_dim):
                raise RuntimeError(
                    f"[Memory:vector] user_memory.vector 维度 {dim} ≠ 期望 {expected_dim}，需重建集合为 {expected_dim} 维"
                )
            return