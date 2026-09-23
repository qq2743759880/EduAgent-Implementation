#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TA4 Batch4 (Mongo) - 按 _id 精确删除 D1+D2+D3, 含对账与幂等复核。
前置: backup_mongo.py 已落盘 manifest.json + 三份 JSON 备份。"""
import os, json
from dotenv import load_dotenv
load_dotenv("edu-agent/.env")
from pymongo import MongoClient
from bson import ObjectId

URI = os.getenv("MONGO_URI")
DB = os.getenv("MONGO_DB")
OUT = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(OUT, "manifest.json"), encoding="utf-8") as fp:
    manifest = json.load(fp)

client = MongoClient(URI, serverSelectionTimeoutMS=8000)
db = client[DB]

def oids(strs):
    return [ObjectId(s) for s in strs]

results = {}
for coll, info in manifest.items():
    ids = oids(info["ids"])
    before = db[coll].count_documents({})
    r1 = db[coll].delete_many({"_id": {"$in": ids}})
    after = db[coll].count_documents({})
    # 幂等: 再删一次
    r2 = db[coll].delete_many({"_id": {"$in": ids}})
    results[coll] = {
        "target": len(ids),
        "deleted_1": r1.deleted_count,
        "before_total": before,
        "after_total": after,
        "deleted_2_idempotent": r2.deleted_count,
    }
    print(f"[{coll}] target={len(ids)} deleted_1={r1.deleted_count} before={before} after={after} deleted_2={r2.deleted_count}")

print("\n=== RECONCILE ===")
ok = True
for coll, r in results.items():
    # 目标数应等于首次删除数, after 应为 0, 幂等删除应为 0
    cond = (r["deleted_1"] == r["target"]) and (r["after_total"] == 0) and (r["deleted_2_idempotent"] == 0)
    print(f"  {coll}: {'PASS' if cond else 'FAIL'}  (deleted1={r['deleted_1']}==target={r['target']}, after={r['after_total']}, idem={r['deleted_2_idempotent']})")
    ok = ok and cond
print("OVERALL:", "ALL PASS" if ok else "SOME FAIL")
