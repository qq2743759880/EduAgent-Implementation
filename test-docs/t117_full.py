# -*- coding: utf-8 -*-
"""task117 全链验收脚本（消费 task116 C-C 契约）。

链路：登录 admin → 取 institution_id → 新建系列 → 默认列表可见（keyword 命中）
→ PATCH 改名（刷新后新值）→ 上架 on_sale → 下架 off_sale
→ 软删 DELETE（默认，message=系列已下架）→ 默认列表消失（WHERE sale_status!='off_sale'）
→ include_deleted=true 回收站仍可见 → 重复 code 40901 → 非法 delivery_mode 42200
→ finally 清理：hard 删除自有测试行（零引用，彻底清除）。

运行： edu-agent/.venv/Scripts/python.exe test-docs/t117_full.py
可选环境变量 T117_BASE（默认 http://127.0.0.1:8078）
"""
import os, sys, json, time, requests

base = os.environ.get("T117_BASE", "http://127.0.0.1:8078").rstrip("/")


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


def list_by(h, keyword=None, include_deleted=False):
    url = base + "/api/admin/courses/series?page=1&page_size=50"
    if keyword:
        url += "&keyword=" + keyword
    if include_deleted:
        url += "&include_deleted=true"
    st, b = jr(requests.get(url, headers=h, timeout=30))
    if st == 200 and b.get("code") == 0:
        return st, b["data"]["items"]
    return st, None


results = []
created_id = None
code = "T117_%d" % int(time.time())


def check(name, cond, extra=""):
    results.append((name, cond, extra))
    print(("[PASS] " if cond else "[FAIL] ") + name + ("  " + extra if extra else ""))


try:
    print("=== 0. 登录 admin (adm02test) ===")
    h, me = login("adm02test", "Test@123456")
    print("role:", me.get("role"), "user_id:", me.get("user_id") or me.get("id"))
    assert h, "登录失败"
    uid = me.get("user_id") or me.get("id")

    print("\n=== 1. 取一个有效 institution_id ===")
    st, items = list_by(h)
    print("list status=%d items=%s" % (st, len(items) if items is not None else None))
    assert st == 200 and items is not None, "列表拉取失败"
    inst = items[0]["institution_id"] if items else 1
    print("使用 institution_id =", inst)

    print("\n=== 2. 新建系列（唯一 code=%s）===" % code)
    payload = {
        "series_name": "task117 验收系列 " + code,
        "series_code": code,
        "institution_id": inst,
        "delivery_mode": "online_live",
        "sale_status": "draft",
        "created_by": uid,
    }
    r = requests.post(base + "/api/admin/courses/series", headers=h, json=payload, timeout=30)
    st, b = jr(r)
    print(st, json.dumps(b, ensure_ascii=False))
    assert st == 200 and b.get("code") == 0, "创建失败"
    created_id = b["data"]["id"]
    check("新建系列成功", True, "id=%s" % created_id)

    print("\n=== 3. 默认列表命中新建行（keyword=%s）===" % code)
    st, items = list_by(h, keyword=code)
    ids = [i["id"] for i in items] if items is not None else []
    check("列表立现新建行", created_id in ids, "in_list=%s" % (created_id in ids))

    print("\n=== 4. 编辑名称 PATCH ===")
    new_name = "task117 改名 " + code
    r = requests.patch(base + "/api/admin/courses/series/%d" % created_id, headers=h,
                       json={"series_name": new_name}, timeout=30)
    st, b = jr(r)
    print(st, json.dumps(b, ensure_ascii=False))
    check("PATCH 改名成功", st == 200 and b.get("code") == 0)
    st2, b2 = jr(requests.get(base + "/api/admin/courses/series/%d" % created_id, headers=h, timeout=30))
    got = b2.get("data", {}).get("series_name")
    check("刷新后为新值", got == new_name, "got=%s" % got)

    print("\n=== 5. 上架 on_sale ===")
    r = requests.patch(base + "/api/admin/courses/series/%d" % created_id, headers=h,
                       json={"sale_status": "on_sale"}, timeout=30)
    st, b = jr(r)
    print(st, json.dumps(b, ensure_ascii=False))
    check("上架成功", st == 200 and b.get("code") == 0)
    st2, b2 = jr(requests.get(base + "/api/admin/courses/series/%d" % created_id, headers=h, timeout=30))
    check("状态=on_sale", b2.get("data", {}).get("sale_status") == "on_sale",
          "st=%s" % b2.get("data", {}).get("sale_status"))

    print("\n=== 6. 下架 off_sale ===")
    r = requests.patch(base + "/api/admin/courses/series/%d" % created_id, headers=h,
                       json={"sale_status": "off_sale"}, timeout=30)
    st, b = jr(r)
    print(st, json.dumps(b, ensure_ascii=False))
    check("下架成功", st == 200 and b.get("code") == 0)
    st2, b2 = jr(requests.get(base + "/api/admin/courses/series/%d" % created_id, headers=h, timeout=30))
    check("状态=off_sale", b2.get("data", {}).get("sale_status") == "off_sale")

    print("\n=== 7. 软删 DELETE（默认路径，呼应 C-C）===")
    r = requests.delete(base + "/api/admin/courses/series/%d" % created_id, headers=h, timeout=30)
    st, b = jr(r)
    print(st, json.dumps(b, ensure_ascii=False))
    check("软删 message=系列已下架", b.get("code") == 0 and b.get("message") == "系列已下架",
          "msg=%s" % b.get("message"))

    print("\n=== 8. 默认列表消失（C-C：WHERE sale_status != 'off_sale'）===")
    st, items = list_by(h, keyword=code)
    ids = [i["id"] for i in items] if items is not None else []
    check("默认列表已剔除软删行", created_id not in ids, "in_list=%s" % (created_id in ids))

    print("\n=== 9. include_deleted=true 回收站仍可见（软删保留行）===")
    st, items = list_by(h, keyword=code, include_deleted=True)
    ids = [i["id"] for i in items] if items is not None else []
    check("回收站视图仍可见", created_id in ids, "in_recycle=%s" % (created_id in ids))

    print("\n=== 10. 重复 code → 40901 ===")
    r = requests.post(base + "/api/admin/courses/series", headers=h, json=payload, timeout=30)
    st, b = jr(r)
    print(st, json.dumps(b, ensure_ascii=False))
    check("重复编码 409/40901", st == 409 and b.get("code") == "40901", "code=%s" % b.get("code"))

    print("\n=== 11. 非法 delivery_mode → 42200 ===")
    bad = dict(payload)
    bad["series_code"] = "T117BAD_%d" % int(time.time())
    bad["delivery_mode"] = "invalid_mode"
    r = requests.post(base + "/api/admin/courses/series", headers=h, json=bad, timeout=30)
    st, b = jr(r)
    print(st, json.dumps(b, ensure_ascii=False))
    check("非法字段 422/42200", st == 422 and b.get("code") == "42200", "code=%s" % b.get("code"))

finally:
    print("\n=== 清理：hard 删除测试系列（零引用，彻底清除）===")
    if created_id:
        r = requests.delete(base + "/api/admin/courses/series/%d?hard=true" % created_id, headers=h, timeout=30)
        st, b = jr(r)
        print(st, json.dumps(b, ensure_ascii=False))
        check("清理：hard 删除成功", st == 200 and b.get("code") == 0, "msg=%s" % b.get("message"))
    else:
        print("（无 created_id，跳过清理）")

print("\n==== 汇总 ====")
np = fp = 0
for n, c, e in results:
    print(("[PASS] " if c else "[FAIL] ") + n + ("  " + e if e else ""))
    if c:
        np += 1
    else:
        fp += 1
print("PASS=%d FAIL=%d" % (np, fp))
sys.exit(0 if fp == 0 else 1)
