# -*- coding: utf-8 -*-
"""task30 实证脚本：contextualize 写入步骤（GWT ①②③④）。

默认用确定性 stub 前缀（不烧 DeepSeek）；设 RUN_REAL_LLM=1 会用真实 LLM 生成一次前缀。
真实向量化走 BGE-M3 CUDA（同 task-VEC），Milvus 读写使用 loader 唯一入口。
"""
from __future__ import annotations

import json
import os
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 项目根入 sys.path

from app.knowledge.importer import embedder, loader  # noqa: E402
from app.knowledge.importer.contextualize import Contextualizer, should_contextualize  # noqa: E402
from app.knowledge.models import ContentType, ImportState, ImportTask, KnowledgeChunk  # noqa: E402


def make(cid: str, content: str, ctype: ContentType = ContentType.DOC_CHUNK,
         resource_type: str | None = None, series_name: str = "检索增强课程") -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=cid, content=content, content_type=ctype,
        resource_type=resource_type, series_name=series_name,
        source_file="task30_verify.pdf",
    )


# 模拟讲义切片
RAW = {
    "c1": "上下文注入能在向量化前把片段放到所属文档语境里，显著提升检索召回率。",
    "c2": "Anthropic 实测 contextual embeddings 可将检索失败率降低 35%，代价是略高的存储与调用成本。",
    "q1": "题目：contextual embeddings 的收益主要来自哪个环节？A 切分 B 向量化前置上下文 C 重排",
    "code1": "def embed(text):\n    return model.encode(text)",
}


def run() -> dict:
    llm_caller = None
    if os.environ.get("RUN_REAL_LLM") == "1":
        from app.knowledge.importer.contextualize import _default_llm_caller as llm_caller
        mode = "real-LLM"
    else:
        # 确定性 stub：返回与文档语境相关的固定前缀
        llm_caller = lambda doc, chunk: "【上下文】本段属于检索增强课程，介绍 contextual retrieval 思想，用于提升语义召回。"
        mode = "deterministic-stub"

    chunks = [
        make("c1", RAW["c1"]),
        make("c2", RAW["c2"]),
        make("q1", RAW["q1"], ctype=ContentType.QUESTION, resource_type="题库"),
        make("code1", RAW["code1"], resource_type="代码"),
    ]

    # ---- GWT② contextualize ----
    ctx = Contextualizer(llm_caller=llm_caller, enabled=True)
    ctx.contextualize(chunks)
    result = {
        "mode": mode,
        "stats": {"contextualized": ctx.contextualized_count,
                  "degraded": ctx.degraded_count, "skipped": ctx.skipped_count},
        "chunks": {},
    }
    for c in chunks:
        result["chunks"][c.chunk_id] = {
            "has_prefix": c.context_prefix is not None,
            "raw_content_preserved": c.content.endswith(RAW[c.chunk_id]) if c.chunk_id in RAW else None,
            "content_len": len(c.content),
            "raw_len": len(c.raw_content or ""),
            "degraded_reason": c.extra.get("contextualize_degraded_reason"),
        }

    # ---- 降级（GWT③）：失败不 500、原文保留 ----
    def boom(doc, chunk):
        raise RuntimeError("模拟 contextualize LLM 不可用")
    deg_ctx = Contextualizer(llm_caller=boom, enabled=True)
    dch = make("d1", RAW["c1"])
    deg_ctx.contextualize([dch])
    result["degrade"] = {
        "content_unchanged": dch.content == RAW["c1"],
        "degraded_reason": dch.extra.get("contextualize_degraded_reason"),
        "no_500": True,
    }

    # ---- 过滤（GWT①）：题库/代码跳过 ----
    result["should_contextualize"] = {cid: should_contextualize(c) for cid, c in zip(
        ["c1", "q1", "code1"], [chunks[0], chunks[2], chunks[3]])}

    # ---- 真实向量化（BGE-M3 CUDA）对前缀版 content ----
    state = ImportState(task_id="task30-verify", source_files=[], chunks=chunks,
                        relations=[], task_type="system_init")
    embedder.embed_node(state)
    result["embed"] = {
        "vec_dim": len(chunks[0].dense_vector) if chunks[0].dense_vector else 0,
        "embedded_on_prefixed": bool(chunks[0].dense_vector),
    }

    # ---- GWT②④ Milvus 真实写入 + 检索（唯一 loader 入口）----
    milvus = None
    try:
        probe = make("task30_probe", RAW["c1"])
        probe.raw_content = RAW["c1"]
        probe.context_prefix = "【上下文】本段属于检索增强课程，介绍 contextual retrieval 思想。"
        probe.content = f"{probe.context_prefix}\n{RAW['c1']}"
        probe.dense_vector = embedder._pseudo_dense(probe.content, embedder.settings.EMBEDDING_DIM)
        svec = embedder.build_sparse_vector(probe.content)
        items = sorted(svec.items(), key=lambda kv: -kv[1])[:64]
        probe.sparse_indices = [int(k) for k, _ in items]
        probe.sparse_values = [float(v) for _, v in items]
        n = loader.load_chunks([probe], tenant_id="_default")
        # 直接按主键读回，验证 content=前缀版 与 raw_content 落库（不依赖相似度排序）
        pk = zlib.crc32("task30_probe".encode("utf-8"))
        client = loader.get_milvus_client()
        client.flush(collection_name=loader.COLLECTION_NAME)  # 强制落segment后 get 可见
        row = client.get(collection_name=loader.COLLECTION_NAME, ids=[pk])[0]
        hit = {"content": row.get("content", ""), "raw_content": row.get("raw_content", "")}
        # 清理探针
        try:
            client.delete(collection_name=loader.COLLECTION_NAME, ids=[pk])
        except Exception:
            pass
        milvus = {
            "inserted": n,
            "content_is_prefixed": bool(hit.get("content", "").startswith("【上下文】")),
            "raw_content_persisted": hit.get("raw_content") == RAW["c1"],
            "pseudo_vec_note": "integrity-probe 用伪向量（避免额外 GPU/API），字段落库路径与真实一致",
        }
    except Exception as exc:
        milvus = {"error": f"{type(exc).__name__}: {exc}"}
    result["milvus"] = milvus

    # ---- GWT④ 存储预算估算（content 容量增量 = 前缀占比）----
    total_raw = sum(len(RAW[cid]) for cid in ("c1", "c2"))
    total_pref = sum(len(c.content) for c in (chunks[0], chunks[1]))
    result["storage_budget"] = {
        "raw_total_chars": total_raw,
        "prefixed_total_chars": total_pref,
        "content_growth_pct": round((total_pref - total_raw) / total_raw * 100, 2),
        # 另存 raw_content（原文）到动态字段 → 总空间 ≈ 前缀版 content + raw_content ≈ 2×原文 + 前缀
        "est_total_storage_growth_pct": round(((total_pref + total_raw) - total_raw) / total_raw * 100, 2),
    }
    return result


if __name__ == "__main__":
    res = run()
    out = os.path.join(os.path.dirname(__file__), "task30_results.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))