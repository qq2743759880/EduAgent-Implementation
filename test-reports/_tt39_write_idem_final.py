# -*- coding: utf-8 -*-
"""task39 item ④（最终）：真实写入口幂等命中。
POST /api/trade/coupon/receive（领券=真实写）带 Idempotency-Key 发两次：
  - 首次：service 真实领券（DB 落 coupon_receive_record），中间件缓存 idem:resp:{key}
  - 二次：中间件缓存命中，直接返回缓存（不再触达 service/DB）
验证 Redis idem:resp:* key 存在 == 真实写入口 Redis 命中。
顺带清理早前误落的两笔 pending 订单（80383/80384）。"""
from __future__ import annotations
import json, uuid, requests, redis, pymysql

BASE = "http://127.0.0.1:8000"
REDIS_URL = "redis://127.0.0.1:6379/0"
COUPON_TEMPLATE_ID = 68
ACCOUNT, PASSWD = "user000001", "Test@123456"

r = redis.from_url(REDIS_URL, decode_responses=True)
def log(*a): print(" ".join(str(x) for x in a), flush=True)

tok = requests.post(f"{BASE}/api/auth/login", json={"account": ACCOUNT, "password": PASSWD}, timeout=15).json()["data"]["access_token"]
h = {"Authorization": "Bearer " + tok}

key = uuid.uuid4().hex
idem_key = f"idem:resp:{key}"

req1 = requests.post(f"{BASE}/api/trade/coupon/receive", json={"coupon_template_id": COUPON_TEMPLATE_ID},
                     headers={"Idempotency-Key": key, **h}, timeout=15)
d1 = req1.json()
req2 = requests.post(f"{BASE}/api/trade/coupon/receive", json={"coupon_template_id": COUPON_TEMPLATE_ID},
                     headers={"Idempotency-Key": key, **h}, timeout=15)
d2 = req2.json()
log("[④] 领券 首次 status:", req1.status_code, "| 二次(同key) status:", req2.status_code)
log("[④] 首次 body:", json.dumps(d1, ensure_ascii=False)[:220])
log("[④] 二次 body == 首次:", json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True))
exists = bool(r.exists(idem_key)); ttl = r.ttl(idem_key)
log("[④] Redis 幂等 key 存在:", exists, "| key:", idem_key, "| TTL:", ttl)
val = r.get(idem_key) or ""
log("[④] Redis 幂等缓存体片段:", val[:200])
# DB：coupon_receive_record 仅 1 行（service 幂等 + 中间件缓存双控）
c = pymysql.connect(host="localhost", port=3306, user="root", password="123456", db="edu", charset="utf8mb4")
cur = c.cursor(pymysql.cursors.DictCursor)
cur.execute("SELECT id,coupon_id,user_id,receive_status FROM coupon_receive_record WHERE coupon_id=%s AND user_id=1 AND yn=1", (COUPON_TEMPLATE_ID,))
rows = cur.fetchall()
log("[④] DB coupon_receive_record(coupon=68,user=1) 行数:", len(rows))
for row in rows: log("     ", row)
log("[④] 写入口幂等结论：Redis 命中 == ", bool(exists) and req1.status_code < 400 and json.dumps(d1, sort_keys=True)==json.dumps(d2, sort_keys=True))

# 清理早前误落的 pending 订单（80383/80384）
for ono in ("6-260904192754-ca6665", "6-260904192754-45f5a7"):
    cr = requests.post(f"{BASE}/api/trade/order/{ono}/cancel", headers=h, timeout=15)
    log(f"[④] 清理 pending 订单 {ono} → cancel status:", cr.status_code, cr.text[:80])