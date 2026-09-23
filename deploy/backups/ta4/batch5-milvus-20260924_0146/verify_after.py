#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TA4 Batch5 - 删除后独立复核 (新连接 + Strong 一致性)。"""
import os, json, time
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

# 全新连接 + Strong 一致性
client = MilvusClient(uri=URI, db_name=DB, consistency_level="Strong")
time.sleep(2)
print("fresh connect OK")

# 复核: 9 个 PK 是否仍在
left = client.query(COLL, filter=f'{pk_field} in {pks}', output_fields=[pk_field], consistency_level="Strong")
print(f"REMAINING_OF_TARGET_PKS={len(left)} (expected 0)")

# 复核: A7 source 是否还有残留
left_src = client.query(COLL, filter=f'source_file == "{src}"', output_fields=[pk_field], consistency_level="Strong")
print(f"REMAINING_OF_SOURCE={len(left_src)} (expected 0)")
if left_src:
    print("  leftover ids:", [e[pk_field] for e in left_src])

stats = client.get_collection_stats(COLL)["row_count"]
print(f"CURRENT_TOTAL={stats}  (was 3435; expected 3426 if delete persisted)")

if len(left) == 0 and len(left_src) == 0:
    print("VERDICT: A7 chunks confirmed GONE (logically + via strong query).")
else:
    print("VERDICT: A7 chunks STILL PRESENT -> delete did not persist, needs investigation.")
