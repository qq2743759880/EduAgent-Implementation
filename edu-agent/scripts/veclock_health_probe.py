# -*- coding: utf-8 -*-
"""
VEC-LOCK embed 一致性健康探针（check-demo.mjs ⑩ 调用；VEC-G5 健康门子断言）

机验：edu_knowledge 全部行 embedding_model = 锁定 BGE-M3 revision、无 embed_fallback、
无空文本 chunk、embed_normalized 全 1。全过 exit 0，否则 exit 1 并输出原因。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.knowledge.importer.embedder import _bge_revision_fingerprint, is_blank_text  # noqa: E402
from app.knowledge.importer.loader import get_milvus_client  # noqa: E402

rev = _bge_revision_fingerprint()
client = get_milvus_client()
rows = client.query(
    "edu_knowledge", filter="",
    output_fields=["embedding_model", "embed_precision", "embed_normalized", "embed_fallback", "content"],
    limit=10000,
)
bad_model = {r.get("embedding_model") for r in rows} - {rev}
bad_fallback = {r.get("embed_fallback") for r in rows if r.get("embed_fallback")}
bad_norm = sum(1 for r in rows if r.get("embed_normalized") != 1)
bad_blank = sum(1 for r in rows if is_blank_text(str(r.get("content") or "")))
ok = not bad_model and not bad_fallback and bad_norm == 0 and bad_blank == 0
print(
    f"edu_knowledge {len(rows)} 行 embed 一致性：model={rev} 混写={bad_model or '无'} "
    f"fallback={bad_fallback or '无'} 未归一化={bad_norm} 空文本={bad_blank} => {'PASS' if ok else 'FAIL'}"
)
sys.exit(0 if ok else 1)
