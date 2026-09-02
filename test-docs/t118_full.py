# -*- coding: utf-8 -*-
"""task118 全链验收脚本：发帖→点赞→评论→评论点赞→详情持久→版块筛选→未登录拦截→清理折叠。"""
import requests, json, time
base = "http://127.0.0.1:8000"

def jr(r):
    try: return r.status_code, r.json()
    except Exception: return r.status_code, {"raw": r.text[:200]}

def login(acc, pw):
    r = requests.post(base + "/api/auth/login", json={"account": acc, "password": pw}, timeout=30)
    st, b = jr(r)
    h = {"Authorization": "Bearer " + b["data"]["access_token"]} if st == 200 and b.get("data") else None
    return h, b.get("data", {}).get("user", {}).get("role")

print("=== 0. 登录 student ===")
h, role = login("user000001", "Test@123456")
print("role:", role)

print("\n=== 1. 发帖（board_code=programming）===")
ts = int(time.time() * 1000)
title = "task118 全链验收帖 %d" % ts
r = requests.post(base + "/api/community/posts", headers=h, timeout=30,
                  json={"board_code": "programming", "title": title,
                        "content_md": "验收正文 %d **加粗**\n第二行" % ts, "tags": ["验收", "task118"]})
st, b = jr(r); print(st, json.dumps(b, ensure_ascii=False))
pid = b["data"]["post_id"]
print("created pid:", pid)

print("\n=== 2. 点赞帖子（第1次 active=true）===")
st, b = jr(requests.post(base + "/api/community/posts/%d/like" % pid, headers=h, timeout=30))
print(st, json.dumps(b, ensure_ascii=False))

print("\n=== 3. 评论帖子 ===")
st, b = jr(requests.post(base + "/api/community/posts/%d/comments" % pid, headers=h, timeout=30,
                         json={"content_md": "验收评论 %d" % ts}))
print(st, json.dumps(b, ensure_ascii=False)); cid = b["data"]["comment_id"]

print("\n=== 4. 评论点赞（第1次 active=true）===")
st, b = jr(requests.post(base + "/api/community/comments/%d/like" % cid, headers=h, timeout=30))
print(st, json.dumps(b, ensure_ascii=False))

print("\n=== 5. 帖子详情（刷新后持久：like_count=1, comment_count=1, mine_react_like=true）===")
st, b = jr(requests.get(base + "/api/community/posts/%d" % pid, headers=h, timeout=30))
d = b["data"]
print(st, "like_count=%s comment_count=%s mine_react_like=%s mine_react_favorite=%s favorite_count=%s board_code=%s" % (
    d["like_count"], d["comment_count"], d["mine_react_like"], d["mine_react_favorite"], d["favorite_count"], d["board_code"]))

print("\n=== 6. 评论列表渲染字段 ===")
st, b = jr(requests.get(base + "/api/community/posts/%d/comments?page=1&page_size=20" % pid, headers=h, timeout=30))
print(st, json.dumps(b["data"]["items"][0], ensure_ascii=False))

print("\n=== 7. 版块筛选 board_code=programming 命中；board=xxx 被忽略（返回全部）===")
st1, b1 = jr(requests.get(base + "/api/community/posts?board_code=programming&page=1&page_size=5", headers=h, timeout=30))
ids1 = [i["post_id"] for i in b1["data"]["items"]]
print("board_code=programming total=%d 含 %d=%s" % (b1["data"]["total"], pid, pid in ids1))
st2, b2 = jr(requests.get(base + "/api/community/posts?board=programming&page=1&page_size=5", headers=h, timeout=30))
codes2 = sorted(set(i["board_code"] for i in b2["data"]["items"]))
print("board=programming total=%d 未过滤(仍含 general) codes=%s" % (b2["data"]["total"], codes2))

print("\n=== 8. 未登录点赞被后端放行（前端必须自行拦 -> 前端实现已走 EAPI.buildLoginUrl）===")
stn, bn = jr(requests.post(base + "/api/community/posts/%d/like" % pid))
print("no-token like status=%d body=%s" % (stn, json.dumps(bn, ensure_ascii=False)[:120]))

print("\n=== 9. 取消点赞（第2次 active=false, total=0）===")
st, b = jr(requests.post(base + "/api/community/posts/%d/like" % pid, headers=h, timeout=30))
print(st, json.dumps(b, ensure_ascii=False))

print("\n=== 10. 清理：admin 锁帖折叠本次验收帖 ===")
ad, ar = login("adm02test", "Test@123456")
st, b = jr(requests.patch(base + "/api/community/posts/%d" % pid, headers=ad, timeout=30, json={"is_locked": True}))
print(st, json.dumps(b, ensure_ascii=False))
print("FOLDED_PID=%s CID=%s" % (pid, cid))