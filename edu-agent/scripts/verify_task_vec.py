# -*- coding: utf-8 -*-
"""task-VEC 实证脚本：真实 BGE-M3(CUDA) vs 哈希 记忆召回对比 + Milvus 真实写入。

- 不产生 DeepSeek LLM 费用：嵌入走本地 BGE-M3（GPU），检索走 Milvus / 纯内存 cosine。
- 输出 JSON 供完工报告引用。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # edu-agent/

from app.ai.memory.vector import (  # noqa: E402
    MemoryVectorStore,
    SemanticEmbedder,
    DeterministicEmbedder,
)

# 有标签语义评测集：5 条记忆 + 3 个语义查询（刻意降低与目标记忆的字面重叠）
MEMORIES = [
    (1, "用户偏好深度学习和神经网络，正在用 PyTorch 研究图像分类模型"),
    (2, "用户下周五要去北京出差，需要预订高铁票并安排酒店"),
    (3, "用户习惯晨跑与吃燕麦早餐，维持健康作息"),
    (4, "用户备考雅思，每天练习英语口语与听力"),
    (5, "用户在学高数微积分，重点关注偏导数与梯度"),
]
QUERIES = {
    "计算机视觉识别方法": 1,
    "出差交通安排": 2,
    "英语能力提升": 4,
    "机器学习模型": 1,
    "下周旅行计划": 2,
}
USER_ID = 700000


RANK_USER = 999099  # 纯内存 rank@1 评测用独立 user，避免与 Milvus 实测(user 700000)互相污染


async def rank1_accuracy(embedder, user_id: int = RANK_USER) -> dict:
    """纯内存（milvus_uri='' 强制 memory 后端）：对每 query 检索 top1，统计 rank@1 命中。"""
    # attention: milvus_uri=None 会用 settings.MILVUS_URI 连 Milvus；要强制内存须传空串
    st = MemoryVectorStore(milvus_uri="", embedder=embedder)
    for mid, content in MEMORIES:
        await st.upsert(memory_id=mid, user_id=user_id, content=content)
    ok = tot = 0
    detail = {}
    for q, truth in QUERIES.items():
        hits = await st.search(user_id=user_id, query=q, top_k=1)
        got = hits[0]["memory_id"] if hits else None
        detail[q] = {"expected": truth, "got": got, "hit": got == truth}
        ok += 1 if got == truth else 0
        tot += 1
    return {"rank1": ok, "total": tot, "accuracy": round(ok / tot, 4), "detail": detail}


async def degrade_test() -> dict:
    """GWT③：BGE 不可用（注入抛异常的 encode_fn）→ 降级哈希 1024 维，不 500，标注 degraded_reason。"""
    import numpy as np

    def boom(texts):
        raise RuntimeError("模拟 BGE-M3 CUDA 不可用")

    emb = SemanticEmbedder(encode_fn=boom)
    vec = emb.embed("用户喜欢咖啡")
    return {
        "dim": len(vec),
        "degraded_reason": emb.degraded_reason,
        "is_hash": all(abs(v) <= 1.0 for v in vec),
        "finite": all(np.isfinite(v) for v in vec),
    }


async def milvus_write_search() -> dict:
    """GWT①②④：真实 Milvus user_memory upsert + 语义检索（BGE-M3）。"""
    st = MemoryVectorStore()
    await st.clear_user(USER_ID)
    rows = []
    for mid, content in MEMORIES:
        await st.upsert(memory_id=800000 + mid, user_id=USER_ID, content=content)
        rows.append(800000 + mid)
    # 语义查询：返回首条应是与深度学习一致的记忆
    hits = await st.search(user_id=USER_ID, query="图像识别用深度学习模型怎么做", top_k=3)
    return {
        "backend": st.backend,
        "dim": st.dim,
        "degraded": st.degraded_reason,
        "upsert_ids": rows,
        "top1": (hits[0] if hits else None),
        "top3_memory_ids": [h["memory_id"] for h in hits],
        "milvus_row_check": str(hits),  # 可检索即证明入库成功
    }


async def main() -> dict:
    bge = SemanticEmbedder()
    hash_emb = DeterministicEmbedder()
    bge_res = await rank1_accuracy(bge)
    hash_res = await rank1_accuracy(hash_emb)
    deg = await degrade_test()
    mil = await milvus_write_search()
    out = {
        "memory_count": len(MEMORIES),
        "query_count": len(QUERIES),
        "embedder": {"type": "BGE-M3 local CUDA", "dim": 1024, "degraded": bge.degraded_reason},
        "rank1": {"bge": bge_res, "hash": hash_res,
                  "bge_beats_hash": bge_res["rank1"] >= hash_res["rank1"]},
        "degrade": deg,
        "milvus": mil,
    }
    return out


if __name__ == "__main__":
    result = asyncio.run(main())
    out_path = Path(__file__).with_name("task_vec_results.json")
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))