# -*- coding: utf-8 -*-
"""证明幂等中间件缓存命中：复用上一轮已写的 idem key 再发同 key 请求。
发第 3 次相同请求：应由 Redis 缓存直接返回（不经 service/DB），响应与缓存体一致、
DB receive_count/receive_record 不新增。"""
from __future__ import annotations
import json, requests, redis, pymysql

BASE="http://127.0.0.1:8000"; REDIS_URL="redis://127.0.0.1:6379/0"
ACCOUNT,PASSWD="user000001","Test@123456"
r=redis.from_url(REDIS_URL,decode_responses=True)
def log(*a): print(" ".join(str(x) for x in a),flush=True)
tok=requests.post(f"{BASE}/api/auth/login",json={"account":ACCOUNT,"password":PASSWD},timeout=15).json()["data"]["access_token"]
h={"Authorization":"Bearer "+tok}
key="5e112f04985e4808a88069f29e8a1f54"  # 上轮落库的 idem key
idem_key=f"idem:resp:{key}"
cached_before=r.get(idem_key)
c=r.get(idem_key)
cached_body=json.loads(c)["body"] if c else None

db=pymysql.connect(host="localhost",port=3306,user="root",password="123456",db="edu",charset="utf8mb4")
cur=db.cursor(pymysql.cursors.DictCursor)
cur.execute("SELECT receive_count FROM coupon WHERE id=68"); rc_before=int(cur.fetchone()["receive_count"])
cur.execute("SELECT COUNT(*) c FROM coupon_receive_record WHERE coupon_id=68 AND user_id=1 AND yn=1"); n_before=cur.fetchone()["c"]

resp=requests.post(f"{BASE}/api/trade/coupon/receive",json={"coupon_template_id":68},
                   headers={"Idempotency-Key":key,**h},timeout=15)
d=resp.json()
cur.execute("SELECT receive_count FROM coupon WHERE id=68"); rc_after=int(cur.fetchone()["receive_count"])
cur.execute("SELECT COUNT(*) c FROM coupon_receive_record WHERE coupon_id=68 AND user_id=1 AND yn=1"); n_after=cur.fetchone()["c"]

log("[缓存命中] 第3次同 key 请求 status:",resp.status_code)
log("[缓存命中] HTTP 响应 == Redis 缓存体:", json.dumps(d,sort_keys=True)==json.dumps(cached_body,sort_keys=True) )
log("[缓存命中] HTTP 响应:", json.dumps(d,ensure_ascii=False)[:160])
log("[缓存命中] coupon.receive_count 68:", rc_before,"->",rc_after,"| 互不影响(未重新领券):", rc_before==rc_after)
log("[缓存命中] receive_record(coupon68,user1) 行数:", n_before,"->",n_after,"| 未新增:", n_before==n_after)
log("[缓存命中] 结论：幂等中间件从真实 Redis 命中，未重复写库 ==",
    resp.status_code==200 and json.dumps(d,sort_keys=True)==json.dumps(cached_body,sort_keys=True) and rc_before==rc_after and n_before==n_after)