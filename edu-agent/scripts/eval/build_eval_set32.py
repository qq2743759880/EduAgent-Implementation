# -*- coding: utf-8 -*-
"""
task32 · RAG 离线评估集构造（冻结召回候选 + 真实 GT + 规则低分样本）

设计：auto-retrieval 基准。
  - query      = 题库题目的「题干」片段（取自真实 question chunk，提取到 答案/选项 前），
                模拟真实用户问句。
  - ground_truth= 该 question chunk 自身的 chunk_id（含题干+答案+解析，即「能回答该问的文档」）。
  - candidates = hybrid_search(query, top_k=recall_topk) 的**冻结**召回结果
                （doc_id/content/score），存盘 JSON —— 之后 verify_task32.py 对同一份
                候选 A/B（BGE-rerank top-20 vs _rule_rerank top-20）。

规则低分样本（GWT②）：记录每个 sample 的 rrf_rank_of_gt（GT 在 RRF 原生分数里的位置）。
  - rrf_rank_of_gt >= k  → GT 不在融合分数 top-k → 记 note="rule_low_score"，
    提示这是「规则/初排会给低分」的困难样本，正是 BGE 语义重排应展示差异之处。

Milvus 一切走 loader 唯一入口；不调用任何 LLM（不烧 DeepSeek）。

用法：
  .venv\\Scripts\\python.exe scripts\\eval\\build_eval_set32.py [--limit 80] [--recall-topk 150]
输出：
  scripts/eval/data/task32_eval_set.json  （含 data_hash，可复现）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.config import settings
from app.chat.rag_evaluator import _data_hash  # 复用可复现指纹（与 verify 对齐）
from app.knowledge.importer.embedder import (
    build_sparse_vector,
    encode_dense_batch,
    ensure_jieba_ready,
)
from app.knowledge.importer.loader import (
    COLLECTION_NAME,
    COURSE_PUBLIC,
    get_milvus_client,
    hybrid_search,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "scripts", "eval", "data")
OUT_PATH = os.path.join(DATA_DIR, "task32_eval_set.json")

# 生产检索的可排除 content_type（与 retriever._milvus_hybrid_search_safe 对齐）
_EXCLUDE = tuple(getattr(settings, "RETRIEVER_EXCLUDE_CONTENT_TYPES", ()) or ())


def _build_filter_expr() -> str | None:
    if not _EXCLUDE:
        return None
    quoted = ", ".join(f'"{ct}"' for ct in _EXCLUDE)
    return f"content_type not in [{quoted}]"


def _extract_query(content: str) -> str:
    """从 question chunk 提取「题干」作为查询（去掉题型标签/选项/答案/解析）。

    口径（task32）：优先取**第一句带问号的问句**——最贴近真实用户查询；
    次选「题目：」后到「选项/答案/解析」前的主体。避免把整段含选项/答案的原文当查询，
    否则 query 成为 GT chunk 的子串 → 自匹配 trivial（rank=1），评估失去判别力（GWT② 失效）。
    """
    text = content or ""
    if "题目：" in text:
        head = text.split("题目：", 1)[1]
    else:
        head = text
    head = re.sub(r"【[^】]*】", "", head).replace("\n", " ").strip()
    head = re.sub(r"\s+", " ", head)

    # 第一句问句：取第一个句末问号（含，与中文？）前的子串
    m = re.search(r"[^？?。]*[？?]", head)
    crisp = m.group(0).strip() if m else None
    if crisp and 6 <= len(crisp) <= 90:
        return crisp

    # 回退：题干主体（到选项/答案/解析前）
    fallback = head
    for cut in ("选项：", "答案：", "解析："):
        if cut in fallback:
            fallback = fallback.split(cut, 1)[0]
            break
    return (fallback or text)[:120]


def _sample_questions(client, n_series: int, per_series: int) -> list[tuple[str, str]]:
    """从不同题库 series 各取若干 question chunk（(chunk_id, content)），尽量多样。

    采用**一次全量捞取 + 内存内按 series 确定性抽样**，避免对 Milvus 发起超大 IN 过滤
    （实测客户端对上百个值的 `chunk_id in [...]` 过滤返回不稳定）。
    """
    rows = client.query(
        COLLECTION_NAME,
        filter="content_type == 'question'",
        output_fields=["question_bank_code", "chunk_id", "content"],
        limit=8000,
    )
    by_bank: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        # series_code 在 question 块上为 None，用 question_bank_code 作多样性分桶键
        bank = str(row.get("question_bank_code") or "unknown_bank")
        cid = str(row.get("chunk_id") or "")
        content = str(row.get("content") or "")
        if cid and content.strip():
            by_bank.setdefault(bank, []).append((cid, content))
    # 排序稳定，保证可复现：按 bank 字典序，块内按 chunk_id 字典序
    chosen: list[tuple[str, str]] = []
    for bank in sorted(by_bank.keys())[:n_series]:
        for cid, content in sorted(by_bank[bank], key=lambda x: x[0])[:per_series]:
            chosen.append((cid, content))
    return chosen


def main() -> None:
    ap = argparse.ArgumentParser(description="构造 task32 离线评估集")
    ap.add_argument("--limit", type=int, default=80, help="最多构造多少个评估样本")
    ap.add_argument("--recall-topk", type=int, default=int(getattr(settings, "RETRIEVER_RECALL_TOPK", 150)))
    ap.add_argument("--n-series", type=int, default=60, help="采样覆盖的 series 数量")
    ap.add_argument("--per-series", type=int, default=2, help="每个 series 采样多少个 question")
    args = ap.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    ensure_jieba_ready()
    client = get_milvus_client()
    filter_expr = _build_filter_expr()
    tenant_ids = ["_default", COURSE_PUBLIC]  # 与生产非 admin 检索范围对齐（course_public 隔离）

    # 1) 抽样题目 chunk（chunk_id + content），作为 query 源 + GT
    samples = _sample_questions(client, args.n_series, args.per_series)
    if not samples:
        raise SystemExit("未找到任何 question 块，无法构造评估集。")

    # 2) 提取题干 query
    queries = [(cid, _extract_query(content)) for cid, content in samples]
    queries = queries[: args.limit]
    if not queries:
        raise SystemExit("构造出的有效 query 为空。")

    # 3) 批量编码全部 query（一次 encode_dense_batch，GPU 一次性，省开销）
    print(f"[build] 待评估 query 数: {len(queries)}")
    q_texts = [q for _, q in queries]
    dense_all = encode_dense_batch(q_texts)
    sparse_all = [build_sparse_vector(q) for q in q_texts]

    # 4) 逐一冻结召回候选 + 记录 GT 的 RRF 原生排名
    cases: list[dict] = []
    for (cid, query), dense_vec, sparse_vec in zip(queries, dense_all, sparse_all):
        dense = [float(x) for x in dense_vec]
        recall = hybrid_search(
            dense_vec=dense,
            sparse_vec=sparse_vec,
            tenant_ids=tenant_ids,
            top_k=args.recall_topk,
            filter_expr=filter_expr,
            timeout=getattr(settings, "MILVUS_SEARCH_TIMEOUT", 8.0),
        )
        candidates = [
            {
                "doc_id": str(c.get("chunk_id") or ""),
                "content": str(c.get("content") or ""),
                "score": float(c.get("score") or 0.0),
                "content_type": str(c.get("content_type") or ""),
                "series_code": str(c.get("series_code") or ""),
            }
            for c in recall
        ]
        raw_ids = [c["doc_id"] for c in candidates]
        rrf_rank = (raw_ids.index(cid) + 1) if cid in raw_ids else None

        # 规则低分样本标注：GT 已被召回但不在 RRF 融合分数 top-k(=20) → 初排给低分，
        # 这正是 BGE 语义重排应展示差异的困难样本（GWT②）
        rule_low = rrf_rank is not None and rrf_rank >= 20
        cases.append({
            "query": query,
            "ground_truth_doc_ids": [cid],
            "candidates": candidates,   # 冻结召回候选（A/B 共用同一份）
            "gt_in_recall": rrf_rank is not None,
            "rrf_rank_of_gt": rrf_rank,
            "note": "rule_low_score" if rule_low else "normal",
        })

    gt_in_recall = sum(1 for c in cases if c["gt_in_recall"])
    low_score = sum(1 for c in cases if c["note"] == "rule_low_score")
    print(f"[build] 样本总数 {len(cases)}，GT 已被召回 {gt_in_recall}，规则低分样本 {low_score}")

    meta = {
        "builder": "build_eval_set32.py",
        "applied_at": None,  # 由 verify 在运行时补当前时间（不写死，保证 hash 只盯数据/参数）
        "recall_topk": args.recall_topk,
        "tenant_ids": tenant_ids,
        "filter_expr": filter_expr,
        "milvus_collection": COLLECTION_NAME,
        "n_cases": len(cases),
    }
    out = {"meta": meta, "cases": cases}
    out["meta"]["data_hash"] = _data_hash(
        cases,
        k=20,
        recall_topk=args.recall_topk,
        params={"filter_expr": filter_expr, "tenant_ids": tenant_ids},
        use_reranker=True,
    )
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[build] 已写出 {OUT_PATH}")
    print(f"[build] data_hash = {out['meta']['data_hash']}")


if __name__ == "__main__":
    main()