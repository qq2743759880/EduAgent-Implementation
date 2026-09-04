# -*- coding: utf-8 -*-
"""task31 实证：真实 BGE-reranker (CUDA) 接入 + 端到端检索 + course_public 分区。

不烧 DeepSeek：use_hyde=False / enable_graph=False。真实向量化走 BGE-M3 CUDA，重排走 bge-reranker-v2-m3 CUDA。
默认用真实 reranker；设 NO_RERANK=1 可模拟 reranker 不可用观察降级。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.auth import UserRole
from app.config import settings
from app.knowledge.reranker import Reranker


def reranker_probe() -> dict:
    """GWT①：真实 FlagReranker 懒加载（CUDA）+ 打分 + 降级纪实。"""
    from app.chat.retriever import _rerank_docs
    from app.chat.schemas import RetrievedDoc

    docs = [
        RetrievedDoc(doc_id="a", score=0.5, content="特征值与特征向量是线性代数核心概念，用于矩阵对角化"),
        RetrievedDoc(doc_id="b", score=0.5, content="暑期大促 五折抢购 班次安排"),
        RetrievedDoc(doc_id="c", score=0.5, content="如何计算一个矩阵的特征值，则要求解其特征多项式"),
    ]
    if os.environ.get("NO_RERANK") == "1":
        import app.chat.retriever as R
        R.Reranker.get().__dict__["_model"] = None
        R.Reranker.get().__dict__["_load_error"] = "模拟 reranker 不可用"
        docs, degrade = _rerank_docs("线性代数 特征值 特征向量 怎么算", docs)
        return {"mode": "degraded", "degraded_reason": degrade,
                "top1": docs[0].doc_id, "n": len(docs)}

    rk = Reranker.get()
    t0 = __import__("time").perf_counter()
    scores = rk.rerank("线性代数 特征值 特征向量 怎么算", [d.content for d in docs])
    el = round(__import__("time").perf_counter() - t0, 3)
    top = _rerank_docs("线性代数 特征值 特征向量 怎么算", docs)
    out, degrade = top
    return {
        "mode": "real",
        "load_error": rk.load_error,
        "batch_size": settings.RERANKER_BATCH_SIZE,
        "scores": scores,
        "infer_sec": el,
        "degraded_reason": degrade,
        "now_sorted": [d.doc_id for d in out],  # a→a 或 c 语义相关应排前, b 促销应垫底
        "latency_ok": el < 8.0,
    }


async def retrieve_probe() -> dict:
    """GWT②④：真实 retrieve_three_channel（召回150→rerank top20→断崖5），观察排序与降级。"""
    from app.chat.retriever import retrieve_three_channel

    bundle = await retrieve_three_channel(
        "线性代数的特征值和特征向量怎么计算",
        user_id=7, role=UserRole.STUDENT,
        use_hyde=False, enable_graph=False, top_k=5, final_max_k=5, cutoff_drop_ratio=0.4,
    )
    return {
        "docs": [{"doc_id": d.doc_id, "score": round(d.score, 4), "ct": d.content_type, "src": d.source_file}
                 for d in bundle.docs],
        "raw_retrieved_count": bundle.raw_retrieved_count,
        "final_count": len(bundle.docs),
        "degraded_reason": bundle.degraded_reason,
        "sorted_desc": all(
            bundle.docs[i].score >= bundle.docs[i + 1].score
            for i in range(len(bundle.docs) - 1)
        ),
    }


def gpu_probe() -> dict:
    """nvidia-smi 观测 reranker 推理后 GPU 占用（W3 OOM 缓解验证）。"""
    try:
        import subprocess
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        line = out.stdout.strip().splitlines()[0] if out.stdout.strip() else "N/A"
        mem_mb, util = line.split(",") if "," in line else ("N/A", "N/A")
        return {"gpu_memory_mb": mem_mb.strip(), "gpu_util": util.strip()}
    except Exception as exc:
        return {"error": str(exc)}


if __name__ == "__main__":
    res = {
        "reranker": reranker_probe(),
        "retrieve": asyncio.run(retrieve_probe()),
        "gpu": gpu_probe(),
        "config": {"recall": settings.RETRIEVER_RECALL_TOPK,
                   "rerank_top": settings.RETRIEVER_RERANK_TOPK,
                   "batch": settings.RERANKER_BATCH_SIZE,
                   "device": settings.RERANKER_DEVICE},
    }
    out = os.path.join(os.path.dirname(__file__), "task31_results.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))