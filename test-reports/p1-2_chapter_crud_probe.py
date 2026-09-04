# -*- coding: utf-8 -*-
"""P1-2 task57 gap：视频章节 CRUD 真实 HTTP 实证（python requests，UTF-8 正确）。"""
import json
import requests

BASE = "http://127.0.0.1:8000"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMDAwMDMiLCJyb2xlIjoiYWRtaW4iLCJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzg4NTkzNTcyfQ.mrUnRWtVkJGA5C8ParrKSBxlZioYTxRxnAiV_xRQqy0"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

def show(tag, r):
    print(f"[{tag}] HTTP {r.status_code} -> {r.text[:300]}")
    try:
        return r.json()
    except Exception:
        return None

BASE_VIDEO = 1
created_id = None

# 1. 列表（实证 200，含既有 3 章节）
r = requests.get(f"{BASE}/api/admin/courses/videos/{BASE_VIDEO}/chapters", headers=H, timeout=10)
d = show("list-before", r); assert r.status_code == 200 and d["code"] == 0
n0 = len(d["data"])

# 2. 创建（UTF-8 中文）
payload = {"video_id": BASE_VIDEO, "chapter_no": 99, "chapter_title": "P1-2临时章节",
           "start_second": 0, "end_second": 60}
r = requests.post(f"{BASE}/api/admin/courses/chapters", data=json.dumps(payload, ensure_ascii=False), headers=H, timeout=10)
d = show("create", r); assert r.status_code == 200 and d["code"] == 0
created_id = d["data"]["id"]
assert d["data"]["chapter_title"] == "P1-2临时章节", "中文标题未 UTF-8 正确落库"
print(f"   created_id={created_id}")

# 3. 冲突：重复 chapter_no -> 40907
r = requests.post(f"{BASE}/api/admin/courses/chapters", data=json.dumps(payload, ensure_ascii=False), headers=H, timeout=10)
d = show("create-dup", r); assert r.status_code == 409 or d.get("code") == "40907"

# 4. GET 详情
r = requests.get(f"{BASE}/api/admin/courses/chapters/{created_id}", headers=H, timeout=10)
d = show("get", r); assert r.status_code == 200 and d["data"]["id"] == created_id

# 5. PATCH 更新
up = {"chapter_title": "P1-2临时章节-改", "end_second": 120}
r = requests.patch(f"{BASE}/api/admin/courses/chapters/{created_id}", data=json.dumps(up, ensure_ascii=False), headers=H, timeout=10)
d = show("patch", r); assert r.status_code == 200 and d["data"]["chapter_title"] == "P1-2临时章节-改"

# 6. 列表应多 1 条
r = requests.get(f"{BASE}/api/admin/courses/videos/{BASE_VIDEO}/chapters", headers=H, timeout=10)
d = show("list-mid", r); assert r.status_code == 200 and len(d["data"]) == n0 + 1

# 7. DELETE
r = requests.delete(f"{BASE}/api/admin/courses/chapters/{created_id}", headers=H, timeout=10)
d = show("delete", r); assert r.status_code == 200 and d["code"] == 0

# 8. 删后再查：列表回到 n0，且按 id 详情 404
r = requests.get(f"{BASE}/api/admin/courses/videos/{BASE_VIDEO}/chapters", headers=H, timeout=10)
d = show("list-after", r); assert r.status_code == 200 and len(d["data"]) == n0
assert all(i["id"] != created_id for i in d["data"]), "删除后章节仍在列表"

# 9. GET 已删章节 -> 404
r = requests.get(f"{BASE}/api/admin/courses/chapters/{created_id}", headers=H, timeout=10)
print(f"[get-deleted] HTTP {r.status_code}")
assert r.status_code == 404

# 清理：幂等删除（兜底）
requests.delete(f"{BASE}/api/admin/courses/chapters/{created_id}", headers=H, timeout=10)

print("\nALL PASSED: create/get/patch/conflict/list/delete/get404 闭环完成，临时数据已清理")