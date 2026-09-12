# -*- coding: utf-8 -*-
"""task13 写路径独立实证（自建测试系列全生命周期，真实 HTTP，无 MOCK）。

前置：后端 8000 运行中；账号 adm02test/Test@123456（admin）。
范围：仅对自建测试系列（series_code 前缀 t13w）执行写操作；
     对存量真实系列一律只读；hard 删除仅用于清理自建数据。
复跑：python test-reports/task13-lifecycle-probe.py
"""
import json
import os
import sys
import time

import requests

BASE = "http://127.0.0.1:8000"
# 凭据不入库:从环境变量读取(测试账号见 AGENTS.md,本机演示环境)
ACCOUNT, PASSWORD = os.environ.get("EDU_TEST_ACCOUNT", ""), os.environ.get("EDU_TEST_PASSWORD", "")
if not (ACCOUNT and PASSWORD):
    sys.exit("请先设置 EDU_TEST_ACCOUNT / EDU_TEST_PASSWORD 环境变量(值见 AGENTS.md 测试账号)")


def show(tag, resp):
    try:
        body = resp.json()
    except ValueError:
        body = {"<non-json>": resp.text[:200]}
    print(f"[{tag}] HTTP {resp.status_code} :: {json.dumps(body, ensure_ascii=False)[:400]}")
    return body


def main():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"account": ACCOUNT, "password": PASSWORD}, timeout=10)
    login = show("LOGIN", r)
    tok = login["data"]["access_token"]
    H = {"Authorization": f"Bearer {tok}"}
    me = show("ME", s.get(f"{BASE}/api/auth/me", headers=H, timeout=10))
    uid = me["data"].get("user_id") or me["data"].get("id")
    print(f"admin user_id = {uid}\n")

    code = f"t13w{int(time.time())}a"
    sid = None
    try:
        # W1 创建（必填字段按 schemas.SeriesCreateAdmin）
        r = s.post(f"{BASE}/api/admin/courses/series", headers=H, timeout=10, json={
            "institution_id": 1, "delivery_mode": "online_recorded",
            "series_code": code, "series_name": "task13接线验证A",
            "sale_status": "draft", "description": "task13 自建测试系列，验证后清理",
            "created_by": uid})
        w1 = show("W1 create", r)
        assert r.status_code == 200 and w1["code"] == 0
        sid = w1["data"]["id"]
        print(f"  -> T1 id={sid} code={code} sale_status={w1['data']['sale_status']}\n")

        # W2 重复编码创建 → 409/40901（SERIES_CODE_CONFLICT 错误形状证据）
        r = s.post(f"{BASE}/api/admin/courses/series", headers=H, timeout=10, json={
            "institution_id": 1, "delivery_mode": "online_recorded",
            "series_code": code, "series_name": "task13重复编码", "created_by": uid})
        w2 = show("W2 create-dup(40901)", r)
        assert r.status_code == 409 and w2["code"] == "40901", "期望 409/40901"
        print()

        # W3 PATCH 编辑（SeriesUpdateAdmin：无 series_code 字段）
        r = s.patch(f"{BASE}/api/admin/courses/series/{sid}", headers={**H, "Content-Type": "application/json"},
                    timeout=10, json={"series_name": "task13接线验证A-改名", "description": "task13 实测更新"})
        w3 = show("W3 patch rename", r)
        assert r.status_code == 200 and w3["data"]["series_name"] == "task13接线验证A-改名"
        print()

        # W4 对未软删系列 restore → 404（restore 错误分支证据）
        r = s.post(f"{BASE}/api/admin/courses/series/{sid}/restore", headers=H, timeout=10)
        show("W4 restore-on-alive(404)", r)
        print()

        # W5 软删（DELETE 默认 → off_sale）
        r = s.delete(f"{BASE}/api/admin/courses/series/{sid}", headers=H, timeout=10)
        show("W5 delete-soft", r)
        r = s.get(f"{BASE}/api/admin/courses/series/{sid}", headers=H, timeout=10)
        assert r.json()["data"]["sale_status"] == "off_sale", "软删后应为 off_sale"
        print("  -> detail.sale_status = off_sale OK\n")

        # W6 回收站视图可见（sale_status=off_sale 组合过滤）
        r = s.get(f"{BASE}/api/admin/courses/series",
                  params={"sale_status": "off_sale", "include_deleted": "true",
                          "keyword": code, "page": 1, "page_size": 20},
                  headers=H, timeout=10)
        w6 = show("W6 bin-view keyword filter", r)
        ids = [i["id"] for i in w6["data"]["items"]]
        assert sid in ids and w6["data"]["total"] >= 1, "回收站视图应能按 keyword 命中 T1"
        print()

        # W7 恢复成功 → {"series_id","status":"restored"}，状态回 draft
        r = s.post(f"{BASE}/api/admin/courses/series/{sid}/restore", headers=H, timeout=10)
        w7 = show("W7 restore ok", r)
        assert r.status_code == 200 and w7["data"] == {"series_id": sid, "status": "restored"}
        r = s.get(f"{BASE}/api/admin/courses/series/{sid}", headers=H, timeout=10)
        assert r.json()["data"]["sale_status"] == "draft", "恢复后应为 draft"
        print("  -> detail.sale_status = draft OK\n")

        # W8 再次软删 + 硬删（?hard=true 仅 ADMIN；自建零引用数据）
        r = s.delete(f"{BASE}/api/admin/courses/series/{sid}", headers=H, timeout=10)
        show("W8a delete-soft(2nd)", r)
        r = s.delete(f"{BASE}/api/admin/courses/series/{sid}?hard=true", headers=H, timeout=10)
        w8 = show("W8b delete-hard", r)
        assert r.status_code == 200 and w8["code"] == 0
        r = s.get(f"{BASE}/api/admin/courses/series/{sid}", headers=H, timeout=10)
        assert r.status_code == 404 and r.json()["code"] == "40400", "硬删后应 404"
        print("  -> detail after hard-delete = 404/40400 OK（自建数据已清理）\n")
        sid = None

        # W9 恢复不存在系列 → 404/40400
        r = s.post(f"{BASE}/api/admin/courses/series/99999999/restore", headers=H, timeout=10)
        show("W9 restore-404(99999999)", r)
        print()
        print("ALL WRITE-PATH PROBES PASSED")
    finally:
        if sid:  # 兜底清理：任何断言失败也尽力清掉自建数据
            try:
                s.delete(f"{BASE}/api/admin/courses/series/{sid}", headers=H, timeout=10)
                s.delete(f"{BASE}/api/admin/courses/series/{sid}?hard=true", headers=H, timeout=10)
                print(f"[cleanup] T1 id={sid} soft+hard deleted")
            except Exception as e:  # noqa: BLE001
                print(f"[cleanup] FAILED id={sid}: {e}")


if __name__ == "__main__":
    sys.exit(main())
