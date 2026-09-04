# -*- coding: utf-8 -*-
"""C5 契约测试：管理员从回收站恢复已下架系列（真实 HTTP 直连 127.0.0.1:8000）。

覆盖（契约锁定，前端将按此消费）：
① POST /api/course-admin/series/{series_id}/restore 成功：data={"series_id": <id>, "status": "restored"}
   → sale_status 由 off_sale 恢复为 draft（草稿，可再次上架）
② 软删三态闭环：soft-delete → list(include_deleted=true) 可见 → restore → 重新上架（draft→on_sale）
③ 错误语义：
   - 不存在 / 未处于软删态 → 404（NOT_FOUND，保留业务 message）
   - 匿名 / 非 admin-manager → 401
④ hard 真删仍由既有 DELETE ?hard=true 守卫（有引用 → 40908 SERIES_IN_USE），恢复端点不影响它

鉴权：登录 /api/auth/login（admin），获取真实 access_token。
代理防护：ProxyHandler({}) + NO_PROXY（Windows 系统代理会卡死 127.0.0.1，沿用 task11/12 同款）。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

import pytest

os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

BASE = os.environ.get("TEST_BASE", "http://127.0.0.1:8000")
ADMIN_BASE = "/api/admin/courses"
RESTORE_PREFIX = "/api/admin/courses"

# 测试环境账号（AGENTS 记忆已验证）
_ADMIN = os.environ.get("TEST_ADMIN_ACCOUNT", "adm02test")
_ADMIN_PWD = os.environ.get("TEST_ADMIN_PASSWORD", "Test@123456")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def api(method: str, path: str, headers: dict | None = None, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with _OPENER.open(req, timeout=20) as resp:
            return resp.status, resp.headers, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, e.headers, json.loads(raw)
        except ValueError:
            return e.code, e.headers, {"_raw": raw.decode("utf-8", "replace")}


def _login() -> tuple[str, int]:
    """登录 admin，返回 (access_token, user_id)。"""
    code, _, body = api("POST", "/api/auth/login", body={"account": _ADMIN, "password": _ADMIN_PWD})
    assert code == 200 and body.get("code") == 0, f"管理员登录失败: {code} {body}"
    data = body["data"]
    return data["access_token"], data["user"]["user_id"]


@pytest.fixture(scope="module")
def admin():
    try:
        tok, uid = _login()
    except AssertionError:
        pytest.skip("管理员登录失败（测试环境账号不可用）")
    return {"headers": {"Authorization": f"Bearer {tok}"}, "user_id": uid}


def _make_series_code():
    return f"rst{int(time.time() * 1000)}"


class TestRestoreSuccess:
    """C5 GWT：软删 → include_deleted 可见 → restore → 可再次上架。"""

    def test_restore_full_cycle(self, admin):
        h = admin["headers"]

        # 1. 创建系列（默认 sale_status=draft）
        code = _make_series_code()
        sc, _, sb = api("POST", f"{ADMIN_BASE}/series", headers=h, body={
            "institution_id": 1,
            "delivery_mode": "online_live",
            "series_code": code,
            "series_name": f"C5恢复测试{code}",
            "sale_status": "on_sale",
            "created_by": admin["user_id"],
        })
        assert sc == 200 and sb["code"] == 0, f"创建系列失败: {sb}"
        sid = sb["data"]["id"]
        assert sb["data"]["sale_status"] == "on_sale"

        try:
            # 2. 软删下架 → off_sale
            dc, _, db = api("DELETE", f"{ADMIN_BASE}/series/{sid}", headers=h)
            assert dc == 200 and db["code"] == 0, f"软删失败: {db}"

            # 3. include_deleted=true 时列表可见且 sale_status=off_sale
            lc, _, lb = api("GET", f"{ADMIN_BASE}/series?include_deleted=true&page=1&page_size=100",
                            headers=h)
            assert lc == 200 and lb["code"] == 0
            found = [it for it in lb["data"]["items"] if it["id"] == sid]
            assert found and found[0]["sale_status"] == "off_sale", f"软删后回收站应可见: {found}"

            # 4. restore → ok(data={series_id,status:restored}) && sale_status='draft'
            rcode, _, rb = api("POST", f"{RESTORE_PREFIX}/series/{sid}/restore", headers=h, body={})
            assert rcode == 200 and rb["code"] == 0, f"restore 失败: {rb}"
            assert rb["data"] == {"series_id": sid, "status": "restored"}, f"restore data: {rb['data']}"

            # 5. 恢复后 sale_status='draft'，且默认列表（不含回收站）可见 → 可再次上架
            lc2, _, lb2 = api("GET", f"{ADMIN_BASE}/series?page=1&page_size=100", headers=h)
            assert lc2 == 200 and lb2["code"] == 0
            found2 = [it for it in lb2["data"]["items"] if it["id"] == sid]
            assert found2 and found2[0]["sale_status"] == "draft", f"恢复后应 draft 且默认列表可见: {found2}"

            # 6. draft → on_sale 重新上架（管理员可再次上架）
            pc, _, pb = api("PATCH", f"{ADMIN_BASE}/series/{sid}", headers=h, body={"sale_status": "on_sale"})
            assert pc == 200 and pb["code"] == 0
            assert pb["data"]["sale_status"] == "on_sale", f"重新上架失败: {pb}"
        finally:
            # 清理：软删测试数据，避免污染 in-sale 列表
            api("DELETE", f"{ADMIN_BASE}/series/{sid}", headers=h)


class TestRestoreErrors:
    """C5 错误语义：404（不存在/未软删）、401（匿名）。"""

    def test_restore_nonexistent_404(self, admin):
        h = admin["headers"]
        code, _, body = api("POST", f"{RESTORE_PREFIX}/series/99999999/restore", headers=h, body={})
        assert code == 404 and body["code"] == "40400", f"期望 404，实际 {code} {body}"

    def test_restore_not_soft_deleted_404(self, admin):
        h = admin["headers"]
        code = _make_series_code()
        sc, _, sb = api("POST", f"{ADMIN_BASE}/series", headers=h, body={
            "institution_id": 1,
            "delivery_mode": "online_live",
            "series_code": code,
            "series_name": f"C5非法恢复{code}",
            "sale_status": "on_sale",
            "created_by": admin["user_id"],
        })
        assert sc == 200 and sb["code"] == 0, f"创建系列失败: {sb}"
        sid = sb["data"]["id"]
        try:
            # on_sale 非软删态 → 恢复应 404（未处于回收站）
            rcode, _, rb = api("POST", f"{RESTORE_PREFIX}/series/{sid}/restore", headers=h, body={})
            assert rcode == 404 and rb["code"] == "40400", f"非软删态恢复应 404: {rcode} {rb}"
            # sale_status 保持 on_sale（未被误改）
            g, _, gb = api("GET", f"{ADMIN_BASE}/series/{sid}", headers=h)
            assert gb["data"]["sale_status"] == "on_sale"
        finally:
            api("DELETE", f"{ADMIN_BASE}/series/{sid}", headers=h)

    def test_restore_anonymous_401(self):
        code, _, body = api("POST", f"{RESTORE_PREFIX}/series/1/restore", body={})
        assert code == 401 and body["code"] == "40101", f"匿名 restore 应 401: {code} {body}"


class TestHardDeleteGuardUnchanged:
    """C5 既不破坏原 DELETE ?hard=true 的 40908 拒引用语义。"""

    def test_hard_delete_with_reference_still_40908(self, admin):
        h = admin["headers"]
        code = _make_series_code()
        sc, _, sb = api("POST", f"{ADMIN_BASE}/series", headers=h, body={
            "institution_id": 1,
            "delivery_mode": "online_live",
            "series_code": code,
            "series_name": f"C5硬删守卫{code}",
            "sale_status": "draft",
            "created_by": admin["user_id"],
        })
        assert sc == 200 and sb["code"] == 0, f"创建系列失败: {sb}"
        sid = sb["data"]["id"]
        try:
            # 给系列挂一个班次 → 建立外键引用（head_teacher_id 必为 staff_profile.id）
            cc, _, cb = api("POST", f"{ADMIN_BASE}/cohorts", headers=h, body={
                "institution_id": 1,
                "series_id": sid,
                "head_teacher_id": 1,
                "cohort_code": _make_series_code(),
                "cohort_name": f"C5硬删守卫班次{code}",
                "sale_price": "1999.00",
                "max_student_count": 30,
                "start_date": "2026-09-01",
                "end_date": "2026-12-31",
            })
            assert cc == 200 and cb["code"] == 0, f"创建班次失败: {cb}"

            # hard=true 真删 → 有引用 → 40908
            hc, _, hb = api("DELETE", f"{ADMIN_BASE}/series/{sid}?hard=true", headers=h)
            assert hc == 409 and hb["code"] == "40908", f"有引用硬删应 409 40908: {hc} {hb}"
        finally:
            api("DELETE", f"{ADMIN_BASE}/series/{sid}", headers=h)