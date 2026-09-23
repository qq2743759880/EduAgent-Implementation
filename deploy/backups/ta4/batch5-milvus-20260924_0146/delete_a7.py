#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TA4 Batch5 (Milvus) - 删除 A7 关联的 9 个 chunk。
前置: a7_chunks_backup.json 已落盘 (含向量，可恢复)。"""
import os, json
from pymilvus import MilvusClient

URI = "http://192.168.85.101:19530"
DB = "default"
COLL = "edu_knowledge"
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(OUT_DIR, "a7_chunks_backup.json"), encoding="utf-8") as fp:
    bk = json.load(fp)
pk_field = bk["pk_field"]
pks = bk["a7_primary_pks"]
src = bk["a7_primary_source"]
print(f"loaded backup: pk_field={pk_field} count={len(pks)} source={src}")
print(f"PKS={pks}")

client = MilvusClient(uri=URI, db_name=DB)
before = client.get_collection_stats(COLL)["row_count"]
print(f"BEFORE_TOTAL={before}")

# 执行删除 (ids 与 filter 不能同传, 用 ids)
res = client.delete(COLL, ids=pks)
print(f"DELETE_RESULT={res}")
client.flush(COLL)
after = client.get_collection_stats(COLL)["row_count"]
print(f"AFTER_TOTAL={after}")
print(f"DELTA={before-after} (expected 9)")

# 复核: 这 9 个 PK 应不存在
left = client.query(COLL, filter=f'{pk_field} in {pks}', output_fields=[pk_field])
print(f"REMAINING_OF_TARGET={len(left)} (expected 0)")
# 复核: 该 source 应无残留
left_src = client.query(COLL, filter=f'source_file == "{src}"', output_fields=[pk_field])
print(f"REMAINING_OF_SOURCE={len(left_src)} (expected 0)")

# 幂等: 再跑一次删除 (用 filter 形式), 应影响 0
res2 = client.delete(COLL, filter=f'{pk_field} in {pks}')
print(f"DELETE_RESULT_2_IDEMPOTENT={res2}")
client.flush(COLL)
after2 = client.get_collection_stats(COLL)["row_count"]
print(f"AFTER_TOTAL_2={after2} (expected == AFTER_TOTAL)")
print("=== DONE ===")
