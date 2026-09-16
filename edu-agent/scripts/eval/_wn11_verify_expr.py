# -*- coding: utf-8 -*-
"""WNEXT11 GWT③ 验证：student vs admin 原生 expr 检索路径对照（Milvus 层，零 HTTP 依赖）。

背景：8010 临时实例因本机页面文件太小，BGE 本地模型加载失败→embedding 降级
DashScope 15s+ → 超 8s 检索超时 → HTTP 对照仅 student 侧可采信（student 0 命中已通过）。
admin「可见」改用 Milvus 原生 expr 直接验证（GWT③ 明示「原生 expr 路径」），
并以库内真实向量为查询向量走 loader.hybrid_search(role=...) 双通道对照，不依赖 embedding。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.knowledge.importer.loader import (  # noqa: E402
    COLLECTION_NAME,
    get_milvus_client,
    hybrid_search,
)

INTERNAL_FIELD = "internal"


def main() -> int:
    client = get_milvus_client()

    # ① 原生 expr 计数对账
    n_true = int(client.query(COLLECTION_NAME, filter=f"{INTERNAL_FIELD} == true",
                              partition_names=["_default"],
                              output_fields=["count(*)"])[0]["count(*)"])
    n_not_true = int(client.query(COLLECTION_NAME, filter=f"{INTERNAL_FIELD} != true",
                                  partition_names=["_default"],
                                  output_fields=["count(*)"])[0]["count(*)"])
    n_total = int(client.query(COLLECTION_NAME, filter="id >= 0",
                               partition_names=["_default"],
                               output_fields=["count(*)"])[0]["count(*)"])
    print(f"[expr] internal==true : {n_true}")
    print(f"[expr] internal!=true : {n_not_true}")
    print(f"[expr] total(_default): {n_total}")
    assert n_true + n_not_true == n_total, "expr 语义不互斥！"
    print("[expr 计数] PASS (互斥且全覆盖)")

    # ② admin 可见：取一条 internal 行的真实向量做查询，role='admin' 必须召回该 internal 行
    internal_row = client.query(
        COLLATION_NAME if False else COLLECTION_NAME,  # noqa 保持 COLLECTION_NAME 使用
        filter=f"{INTERNAL_FIELD} == true",
        partition_names=["_default"],
        output_fields=["dense_vec", "sparse_vec", "chunk_id", "source_file", "internal"],
        limit=1,
    )[0]
    print(f"[sample internal 行] chunk_id={internal_row.get('chunk_id')} "
          f"source={internal_row.get('source_file')} internal={internal_row.get('internal')}")

    a_docs = hybrid_search(
        dense_vec=[float(x) for x in internal_row["dense_vec"]],
        sparse_vec={str(k): float(v) for k, v in (internal_row.get("sparse_vec") or {}).items()},
        tenant_ids=None,              # admin: 搜所有分区
        top_k=10,
        role="admin",
    )
    a_internal = [d for d in a_docs if d.get("internal") is True]
    print(f"[admin] 检索返回 {len(a_docs)} 条，其中 internal=true {len(a_internal)} 条")
    assert len(a_internal) >= 1, "admin 应可见 internal 文档！"
    print("[admin 可见] PASS")

    # ③ student：同向量 role='student' → 原生 expr 过滤 internal!=true，internal 行必被剔除
    s_docs = hybrid_search(
        dense_vec=[float(x) for x in internal_row["dense_vec"]],
        sparse_vec={str(k): float(v) for k, v in (internal_row.get("sparse_vec") or {}).items()},
        tenant_ids=["_default"],
        top_k=10,
        role="student",
    )
    s_internal = [d for d in s_docs if d.get("internal") is True]
    print(f"[student] 检索返回 {len(s_docs)} 条，其中 internal=true {len(s_internal)} 条")
    assert len(s_internal) == 0, "student 不应命中 internal 文档（原生 expr）！"
    print("[student 0 命中] PASS")

    # ④ 契约不破坏：不传 role/include_internal（历史调用）→ 不追加过滤
    d_docs = hybrid_search(
        dense_vec=[float(x) for x in internal_row["dense_vec"]],
        sparse_vec={str(k): float(v) for k, v in (internal_row.get("sparse_vec") or {}).items()},
        tenant_ids=["_default"],
        top_k=10,
    )
    d_internal = [d for d in d_docs if d.get("internal") is True]
    print(f"[default(无 role)] 检索返回 {len(d_docs)} 条，其中 internal=true {len(d_internal)} 条")
    assert len(d_internal) >= 1, "默认调用（历史行为=可见）不应改变！"
    print("[契约不破坏] PASS (默认调用 internal 可见=历史行为)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
