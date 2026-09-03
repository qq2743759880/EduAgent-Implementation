# -*- coding: utf-8 -*-
"""task121 筛选栏接线验证（只读，消费 GET /series 真实筛选参数）。

验证前端筛选栏现在发往后端的 query 参数真实生效：
  keyword / delivery_mode / sale_status / sort
对应 admin-courses.html 的 #f-kw / #f-dm / #f-ss / #f-sort。

运行： edu-agent/.venv/Scripts/python.exe test-docs/t121_filter_check.py
可选环境变量 T121_BASE（默认 http://127.0.0.1:8078）
"""
import os, requests

base = os.environ.get("T121_BASE", "http://127.0.0.1:8078").rstrip("/")


def jr(r):
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:300]}


def login(acc, pw):
    r = requests.post(base + "/api/auth/login", json={"account": acc, "password": pw}, timeout=30)
    st, b = jr(r)
    h = {"Authorization": "Bearer " + b["data"]["access_token"]} if st == 200 and b.get("data") else None
    return h, (b.get("data", {}).get("user", {}) or {})


def get(h, **params):
    url = base + "/api/admin/courses/series"
    st, b = jr(requests.get(url, headers=h, params=params, timeout=30))
    if st == 200 and b.get("code") == 0:
        return st, b["data"]
    return st, b


results = []


def check(name, cond, extra=""):
    results.append((name, cond, extra))
    print(("[PASS] " if cond else "[FAIL] ") + name + ("  " + extra if extra else ""))


h, me = login("adm02test", "Test@123456")
assert h, "登录失败"
print("role:", me.get("role"), "user_id:", me.get("user_id") or me.get("id"))

# 基准：默认列表
st, data = get(h, page=1, page_size=50)
assert st == 200 and data and data.get("items") is not None, "默认列表拉取失败"
items = data["items"]
total = (data.get("page_meta") or {}).get("total", len(items))
print("默认列表 items=%d total=%s" % (len(items), total))
check("默认列表非空", len(items) > 0, "items=%d" % len(items))
if not items:
    print("无数据可验证筛选，终止")
    raise SystemExit(0)

s0 = items[0]
print("基准系列: id=%s code=%s dm=%s st=%s name=%s" % (s0["id"], s0.get("series_code"), s0.get("delivery_mode"), s0.get("sale_status"), s0.get("series_name")))

# 1) keyword（前端 #f-kw）→ 应命中 series_code
st, d = get(h, keyword=s0.get("series_code"))
ok = st == 200 and d.get("items") is not None and any(x["id"] == s0["id"] for x in d["items"])
check("keyword=编码 命中该系列", ok, "code=%s 返回=%d" % (s0.get("series_code"), len(d.get("items") or [])))

# 2) delivery_mode（前端 #f-dm）→ 返回项 delivery_mode 一致
st, d = get(h, delivery_mode=s0.get("delivery_mode"))
rows = d.get("items") or []
ok = st == 200 and len(rows) > 0 and all(x.get("delivery_mode") == s0.get("delivery_mode") for x in rows)
check("delivery_mode 过滤一致", ok, "dm=%s 返回=%d" % (s0.get("delivery_mode"), len(rows)))

# 3) sale_status（前端 #f-ss）→ 返回项 sale_status 一致
st, d = get(h, sale_status=s0.get("sale_status"))
rows = d.get("items") or []
ok = st == 200 and len(rows) > 0 and all(x.get("sale_status") == s0.get("sale_status") for x in rows)
check("sale_status 过滤一致", ok, "st=%s 返回=%d" % (s0.get("sale_status"), len(rows)))

# 4) sort=name_asc（前端 #f-sort）→ 200 且按 series_name 升序
st, d = get(h, sort="name_asc", page=1, page_size=50)
rows = d.get("items") or []
names = [x.get("series_name") or "" for x in rows]
ok = st == 200 and names == sorted(names)
check("sort=name_asc 升序生效", ok, "items=%d" % len(rows))

# 5) sort=newest → 200（不报错）
st, d = get(h, sort="newest", page=1, page_size=10)
check("sort=newest 被接受(200)", st == 200, "status=%d" % st)

# 6) 非法 sort → 422（确认参数被校验，前端只发合法枚举）
st, d = get(h, sort="bogus")
check("非法 sort 被拒(422)", st == 422, "status=%d" % st)

# 7) 组合筛选：delivery_mode + sale_status
st, d = get(h, delivery_mode=s0.get("delivery_mode"), sale_status=s0.get("sale_status"))
rows = d.get("items") or []
ok = st == 200 and all(x.get("delivery_mode") == s0.get("delivery_mode") and x.get("sale_status") == s0.get("sale_status") for x in rows)
check("组合筛选一致", ok, "返回=%d" % len(rows))

print("\n==== 汇总 ====")
for n, c, e in results:
    print(("[PASS] " if c else "[FAIL] ") + n + ("  " + e if e else ""))
p = sum(1 for _, c, _ in results if c); f = sum(1 for _, c, _ in results if not c)
print("PASS=%d FAIL=%d" % (p, f))
raise SystemExit(0 if f == 0 else 1)
