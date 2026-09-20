# -*- coding: utf-8 -*-
"""EVALFREEZE-B1 探针：实跑 idx31（v1_idx=31）检索，dump top5 docs 的 chunk_id/sha256/内容头，
判定「组命中」（golden doc_sha256 任一成员进 top5）是否成立。只读，不写库。"""
from __future__ import annotations
import asyncio, hashlib, json, os, sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PARAMS = dict(recall_topk=150, rerank_topk=20, final_max_k=5, cutoff_drop_ratio=0.40,
              use_hyde=False, enable_graph=True, nprobe=10, rrf_k=60)

async def main() -> int:
    from app.auth import UserRole
    from app.chat.retriever import retrieve_three_channel
    from app.knowledge.importer.embedder import encode_dense_batch, ensure_jieba_ready

    with open(os.path.join(BASE_DIR, "scripts", "eval", "data", "r64v3_eval_set64.json"),
              encoding="utf-8") as f:
        case = [c for c in json.load(f)["cases"] if c.get("v1_idx") == 31][0]

    ensure_jieba_ready()
    _ = encode_dense_batch(["预热"])

    # 同时跑 V2 题干与 V3 改写题干
    queries = [("V2", case["v2_query"]), ("V3", case["query"])]
    golden_sha = case["golden"]["doc_sha256"]
    golden_id = case["golden"]["chunk_id"]
    print(f"golden chunk_id={golden_id}")
    print(f"golden doc_sha256={golden_sha}")
    print(f"gt_content head: {case['gt_content'][:60]!r}")
    print("=" * 70)

    for tag, q in queries:
        bundle = await retrieve_three_channel(
            q, user_id=1, role=UserRole.STUDENT,
            use_hyde=PARAMS["use_hyde"], enable_graph=PARAMS["enable_graph"],
            top_k=5, final_max_k=5, cutoff_drop_ratio=PARAMS["cutoff_drop_ratio"])
        docs = [{"chunk_id": d.doc_id, "content": d.content, "score": d.score} for d in bundle.docs]
        print(f"[{tag}] query={q!r}  final_docs={len(docs)}  recall={bundle.raw_retrieved_count} degraded={bundle.degraded_reason}")
        group_hits = []
        for i, d in enumerate(docs):
            sh = hashlib.sha256(d["content"].encode("utf-8")).hexdigest()
            is_group = (sh == golden_sha)
            is_id = (d["chunk_id"] == golden_id)
            if is_group:
                group_hits.append(i + 1)
            print(f"  rank{i+1}: chunk_id={d['chunk_id']} score={d['score']:.4f} "
                  f"sha={sh[:16]}... group={is_group} exact_id={is_id}")
            print(f"           head={d['content'][:70]!r}")
        print(f"  >>> 组命中排名(group sha 命中): {group_hits if group_hits else 'NONE'}")
        print("-" * 70)
    return 0

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
