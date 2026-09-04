# -*- coding: utf-8 -*-
"""
task32 · 记忆召回评估集扩充实证（VEC批判③ 落地）

对象   ：三层记忆向量召回（MemoryVectorStore.search，Milvus user_memory + BGE-M3 CUDA 1024 维）
范围   ：既有记忆召回评估集仅 5 条 → 扩充至 30 条金标 query（语义类别：偏好/进度/错误/目标）
口径   ：对每个 gold query，用 `MemoryVectorStore.search` 返回 cosine 降序 top-k，
         计算 expected_memory_id 是否落在 top-1（rank@1）/ top-3（recall@3）/ MRR。
对比   ：同一份 30 条 query 分别跑「真实 BGE-M3」（Milvus 后端） vs 「确定性哈希」（in-memory 后端），
         展示语义召回相对字面召回的增益（recall 差）。
Milvus ：一切经 MemoryVectorStore → loader.get_milvus_client()（唯一入口，不旁路 pymilvus）。
不调 LLM；真实 BGE-M3 本地 GPU embedding。

用法：
  .venv\\Scripts\\python.exe scripts\\eval\\eval_task32_memory_recall.py
输出：
  scripts/eval/data/task32_memory_recall_result.json
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.ai.memory.vector import (  # noqa: E402
    DeterministicEmbedder,
    MemoryVectorStore,
    SemanticEmbedder,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "scripts", "eval", "data")
SET_PATH = os.path.join(DATA_DIR, "task32_memory_recall_set.json")
OUT_PATH = os.path.join(DATA_DIR, "task32_memory_recall_result.json")

TEST_USER_REAL = 66661   # 真实 BGE pass 用（Milvus user_memory），结束后 clear_user
TEST_USER_HASH = 66662   # 哈希 pass 用（in-memory）


def _rank_of(expected: int, hits: list[dict]) -> int | None:
    """expected memory 在 hits 中的 1-based rank；不在则 None。"""
    for i, h in enumerate(hits, start=1):
        if int(h.get("memory_id")) == int(expected):
            return i
    return None


async def _run_pass(store: MemoryVectorStore, user_id: int, memories, queries) -> dict:
    await store.clear_user(user_id)
    for mem in memories:
        await store.upsert(memory_id=int(mem["memory_id"]), user_id=user_id, content=mem["content"])

    n = len(queries)
    hits1 = hits3 = 0
    mrr = 0.0
    detail: list[dict] = []
    for q in queries:
        qid = q["id"]
        exp = int(q["expected_memory_id"])
        res = await store.search(user_id=user_id, query=q["query"], top_k=5)
        rk = _rank_of(exp, res)
        d = {
            "id": qid,
            "category": q["category"],
            "query": q["query"],
            "expected_memory_id": exp,
            "rank": rk,
            "hit@1": (rk == 1),
            "recall@3": (rk is not None and rk <= 3),
            "top1_memory_id": int(res[0]["memory_id"]) if res else None,
            "top1_score": round(float(res[0]["score"]), 4) if res else None,
        }
        detail.append(d)
        if rk == 1:
            hits1 += 1
        if rk is not None and rk <= 3:
            hits3 += 1
        if rk:
            mrr += 1.0 / rk

    await store.clear_user(user_id)
    return {
        "n": n,
        "rank@1": round(hits1 / n, 4) if n else 0.0,
        "recall@3": round(hits3 / n, 4) if n else 0.0,
        "mrr": round(mrr / n, 4) if n else 0.0,
        "rank1_abs": hits1,
        "recall3_abs": hits3,
        "degraded_reason": getattr(store, "degraded_reason", None),
        "detail": detail,
    }


async def main_async() -> None:
    data = json.load(open(SET_PATH, encoding="utf-8"))
    memories = data["memories"]
    queries = data["queries"]
    assert len(memories) == data["meta"]["n_memories"]
    assert len(queries) >= 30, f"评估集 query 数不足 30: {len(queries)}"

    # Pass A：真实 BGE-M3 + Milvus（MemoryVectorStore 默认 SemanticEmbedder / Milvus 后端）
    store_real = MemoryVectorStore()  # backend=milvus, SemanticEmbedder(BGE-M3)
    print(f"[task32] backend(real) = {store_real.backend}, dim = {store_real.dim}")
    real = await _run_pass(store_real, TEST_USER_REAL, memories, queries)
    print(f"[task32][BGE] rank@1={real['rank@1']}  recall@3={real['recall@3']}  "
          f"mrr={real['mrr']}  degraded={real['degraded_reason']}")

    # Pass B：确定性哈希 embedder（in-memory，不扰 Milvus）
    store_hash = MemoryVectorStore(milvus_uri="", embedder=DeterministicEmbedder())
    print(f"[task32] backend(hash) = {store_hash.backend}, dim = {store_hash.dim}")
    hsh = await _run_pass(store_hash, TEST_USER_HASH, memories, queries)
    print(f"[task32][HASH] rank@1={hsh['rank@1']}  recall@3={hsh['recall@3']}  mrr={hsh['mrr']}")

    result = {
        "task": "task32-memory-recall",
        "meta": data["meta"],
        "target": {"bge_rank1_ge": 0.9},
        "bge_milvus": real,
        "hash_inmemory": hsh,
        "recall_gap_bge_over_hash": {
            "rank@1": round(real["rank@1"] - hsh["rank@1"], 4),
            "recall@3": round(real["recall@3"] - hsh["recall@3"], 4),
        },
        "target_met": real["rank@1"] >= 0.9,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[task32] 已写出 {OUT_PATH}")
    print(f"[task32] 达标(BGE rank@1>=0.9) = {result['target_met']}")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()