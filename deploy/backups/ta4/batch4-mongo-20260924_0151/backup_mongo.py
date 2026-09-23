#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TA4 Batch4 (Mongo) - 只读盘点 + 备份 (不删除)。
导出目标集合的目标文档到 JSON (bson.json_util 可无损还原 ObjectId)。"""
import os, json
from dotenv import load_dotenv
load_dotenv("edu-agent/.env")
from pymongo import MongoClient
from bson.json_util import dumps

URI = os.getenv("MONGO_URI")
DB = os.getenv("MONGO_DB")
OUT = os.path.dirname(os.path.abspath(__file__))

client = MongoClient(URI, serverSelectionTimeoutMS=8000)
db = client[DB]

manifest = {}

# ---- artifacts.files: 全部 41 个均为 eval/ 或 orchestrator-verify-probe* ----
files = list(db["artifacts.files"].find({}))
print(f"artifacts.files total={len(files)}")
file_ids = [f["_id"] for f in files]
manifest["artifacts.files"] = {"count": len(files), "ids": [str(x) for x in file_ids]}
with open(os.path.join(OUT, "artifacts.files.json"), "w", encoding="utf-8") as fp:
    fp.write(dumps(files, indent=2))

# ---- artifacts.chunks: 属于上述 41 个 file 的 chunk ----
chunks = list(db["artifacts.chunks"].find({"files_id": {"$in": file_ids}}))
print(f"artifacts.chunks (target-owned)={len(chunks)}  (collection total={db['artifacts.chunks'].count_documents({})})")
manifest["artifacts.chunks"] = {"count": len(chunks), "ids": [str(x["_id"]) for x in chunks]}
with open(os.path.join(OUT, "artifacts.chunks.json"), "w", encoding="utf-8") as fp:
    fp.write(dumps(chunks, indent=2))

# ---- learning_event: 全部 20 个均为探针 ----
le = list(db["learning_event"].find({}))
print(f"learning_event total={len(le)}")
le_ids = [e["_id"] for e in le]
manifest["learning_event"] = {"count": len(le), "ids": [str(x) for x in le_ids]}
with open(os.path.join(OUT, "learning_event.json"), "w", encoding="utf-8") as fp:
    fp.write(dumps(le, indent=2))

with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as fp:
    json.dump(manifest, fp, indent=2)

print("=== BACKUP MANIFEST ===")
for k, v in manifest.items():
    print(f"  {k}: {v['count']} docs")
print("backup files written to", OUT)
