#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TA4 Batch5 (Milvus) - 验证 + 备份 A7 关联 chunk。
仅查询/导出，不做任何删除。"""
import json, os, sys
from pymilvus import MilvusClient

URI = "http://192.168.85.101:19530"
DB = "default"
COLL = "edu_knowledge"
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

A7_PRIMARY_SOURCE = "up_1_1215916b_ib_g2_WNI1BG2_1789562680.md"  # task144 上传件
# 其他 4 个 A7 文件名的模式（应无匹配）
A7_OTHER_PATTERNS = ["%t10_same%", "%test_s4%", "%知识库测试%", "%WNI1BG2%"]

client = MilvusClient(uri=URI, db_name=DB)

# 1) schema
schema = client.describe_collection(COLL)
fields = schema.get("fields", schema.get("schema", {}).get("fields", [])) if isinstance(schema, dict) else schema.fields
print("=== SCHEMA FIELDS ===")
pk_field = None
source_field = None
for f in fields:
    name = f.get("name") if isinstance(f, dict) else f.name
    is_pk = f.get("is_primary") if isinstance(f, dict) else getattr(f, "is_primary", False)
    dtype = f.get("type") if isinstance(f, dict) else getattr(f, "type", None)
    print(f"  {name}  pk={is_pk}  type={dtype}")
    if is_pk:
        pk_field = name
    if name in ("source", "source_file"):
        source_field = name
print(f"PK_FIELD={pk_field}  SOURCE_FIELD={source_field}")

# 2) count before
total = client.get_collection_stats(COLL)["row_count"]
print(f"COLLECTION_TOTAL={total}")

# 3) A7 primary exact match
q_exact = client.query(COLL, filter=f'{source_field} == "{A7_PRIMARY_SOURCE}"', output_fields=["*"])
print(f"A7_PRIMARY_EXACT_MATCH count={len(q_exact)}")
pks_primary = [e[pk_field] for e in q_exact]
print(f"A7_PRIMARY_PKS={pks_primary}")

# 4) other 4 patterns -> should be 0
other_hits = {}
for pat in A7_OTHER_PATTERNS:
    q = client.query(COLL, filter=f'{source_field} like "{pat}"', output_fields=[source_field])
    uniq = sorted({e[source_field] for e in q})
    other_hits[pat] = {"count": len(q), "sources": uniq}
    print(f"PATTERN {pat} -> count={len(q)} sources={uniq}")

# 5) backup matched entities (vectors included) to JSON
backup = {
    "collection": COLL,
    "db": DB,
    "uri": URI,
    "pk_field": pk_field,
    "source_field": source_field,
    "a7_primary_source": A7_PRIMARY_SOURCE,
    "a7_primary_pks": pks_primary,
    "a7_primary_count": len(q_exact),
    "other_pattern_hits": other_hits,
    "entities": q_exact,
}
out_path = os.path.join(OUT_DIR, "a7_chunks_backup.json")
with open(out_path, "w", encoding="utf-8") as fp:
    json.dump(backup, fp, ensure_ascii=False, indent=2)
print(f"BACKUP_WRITTEN={out_path} bytes={os.path.getsize(out_path)}")

# 6) summary
print("=== SUMMARY ===")
print(f"to_delete_pks={pks_primary}")
print(f"to_delete_count={len(pks_primary)}")
all_other = sum(v["count"] for v in other_hits.values())
print(f"other_4_files_matched_chunks={all_other} (must be 0)")
