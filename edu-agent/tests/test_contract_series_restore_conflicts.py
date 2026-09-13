# -*- coding: utf-8 -*-
"""H1c（P2-13 热修）：restore-40901 / hard-delete-40908 冲突分支契约测试（真实 HTTP 直连 127.0.0.1:8000）。

P2-13 原始任务书设想「建 A(code X) → 软删 A → 建 B(code X) → restore A → 40901」。
实现复核（service.restore_series / series_repo / baseline_schema.sql 实读 + 本文件实测）：

- series 表有 DB 唯一约束 uk_series_code(institution_id, series_code)，且软删
  （sale_status='off_sale'）**保留整行**、编码不释放；
- create_series 前置 get_by_code 校验（不过滤 sale_status）→ 软删态 A 仍占用编码，
  建 B(code X) 在 **CREATE 时**即 409/40901；
- 因此 restore_series 里的 40901 分支（get_by_code 命中且 id≠本系列）在当前约束下
  **无法经 HTTP API 构造**（编码不可能重复）——该分支为纵深防御，仅在库外直写数据
  造成重复时兜底。本文件按「真实契约」断言：
  ① 软删后编码仍被占用 → 建 B 得 40901（CREATE 时）；
  ② restore A（编码属主仍是 A 自己）→ 200 恢复成功，无误伤 40901；
  ③ hard delete 有班次引用 → 409/40908，且系列不被删除；
  ④ hard delete 零引用 → 200 真删，GET → 404（40908 的对偶语义）。

夹具模式沿学 tests/test_course_admin_restore.py：module 级登录 + 唯一前缀
h1c{epoch_ms} + try/finally 清理（①④用 hard delete 零残留；③的班次仅有软删
端点，best-effort 软删后残留 2 行（cohort yn=0 + series off_sale），已登记 H2
清理脚本范畴——见 test-reports/H1-hotfix-report.md）。
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
        with _OPENER.open(req, timeout=30) as resp:
            return resp.status, resp.headers, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, e.headers, json.loads(raw)
        except ValueError:
            return e.code, e.headers, {"_raw": raw.decode("utf-8", "replace")}


def _login() -> tuple[str, int]:
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


def _code() -> str:
    return f"h1c{int(time.time() * 1000)}"


def _create_series(h: dict, user_id: int, code: str, *, sale_status: str = "on_sale"):
    sc, _, sb = api("POST", f"{ADMIN_BASE}/series", headers=h, body={
        "institution_id": 1,
        "delivery_mode": "online_live",
        "series_code": code,
        "series_name": f"H1c冲突测试{code}",
        "sale_status": sale_status,
        "created_by": user_id,
    })
    assert sc == 200 and sb["code"] == 0, f"创建系列失败: {sb}"
    return sb["data"]["id"]


def _hard_delete(h: dict, series_id: int):
    return api("DELETE", f"{ADMIN_BASE}/series/{series_id}?hard=true", headers=h)


class TestRestoreCodeConflict40901:
    """①+②：软删编码不释放 → 建 B 在 CREATE 时 40901；restore 自身无误伤。"""

    def test_softdel_retains_code_and_restore_no_false_conflict(self, admin):
        h, uid = admin["headers"], admin["user_id"]
        code = _code()
        sid_a = _create_series(h, uid, code, sale_status="on_sale")
        try:
            # 软删 A → off_sale（行保留）
            dc, _, db = api("DELETE", f"{ADMIN_BASE}/series/{sid_a}", headers=h)
            assert dc == 200 and db["code"] == 0, f"软删失败: {db}"

            # ① 建 B(同 institution + 同 code) → CREATE 时即 409/40901
            # （软删不释放编码；这就是 restore-40901 经 API 不可达的原因）
            bc, _, bb = api("POST", f"{ADMIN_BASE}/series", headers=h, body={
                "institution_id": 1,
                "delivery_mode": "online_live",
                "series_code": code,
                "series_name": f"H1c编码占用{code}",
                "sale_status": "draft",
                "created_by": uid,
            })
            assert bc == 409, f"建 B 应 409，实际 {bc}: {bb}"
            assert bb["code"] == "40901", f"建 B 应 40901，实际 {bb}"

            # ② restore A（编码属主=A 自己，existing.id==series_id）→ 200 恢复成功
            rc, _, rb = api("POST", f"{ADMIN_BASE}/series/{sid_a}/restore", headers=h, body={})
            assert rc == 200 and rb["code"] == 0, f"restore 应成功（编码属主是自身）: {rb}"
            assert rb["data"] == {"series_id": sid_a, "status": "restored"}, f"restore data: {rb}"
            gc, _, gb = api("GET", f"{ADMIN_BASE}/series/{sid_a}", headers=h)
            assert gc == 200 and gb["data"]["sale_status"] == "draft"

            # 恢复后编码仍被 A 占用 → 再建 B 依旧 40901
            bc2, _, bb2 = api("POST", f"{ADMIN_BASE}/series", headers=h, body={
                "institution_id": 1,
                "delivery_mode": "online_live",
                "series_code": code,
                "series_name": f"H1c编码占用2{code}",
                "sale_status": "draft",
                "created_by": uid,
            })
            assert bc2 == 409 and bb2["code"] == "40901", f"恢复后再建 B 应 40901: {bb2}"
        finally:
            # 清理（零引用 → hard delete 物理删，零残留）
            hc, _, hb = _hard_delete(h, sid_a)
            if hc != 200:
                api("DELETE", f"{ADMIN_BASE}/series/{sid_a}", headers=h)  # 兜底软删


class TestHardDeleteConflict40908:
    """③：有班次引用 → hard delete 409/40908，系列不被删除。"""

    def test_hard_delete_with_cohort_reference_40908(self, admin):
        h, uid = admin["headers"], admin["user_id"]
        code = _code()
        sid = _create_series(h, uid, code, sale_status="draft")
        cohort_id = None
        try:
            # 建班次引用 A（head_teacher_id=1 为既有 staff_profile 种子）
            cc, _, cb = api("POST", f"{ADMIN_BASE}/cohorts", headers=h, body={
                "institution_id": 1,
                "series_id": sid,
                "head_teacher_id": 1,
                "cohort_code": _code(),
                "cohort_name": f"H1c硬删守卫班次{code}",
                "sale_price": "999.00",
                "max_student_count": 10,
                "start_date": "2026-09-01",
                "end_date": "2026-12-31",
            })
            assert cc == 200 and cb["code"] == 0, f"创建班次失败: {cb}"
            cohort_id = cb["data"]["id"]

            # hard=true → 409/40908（SERIES_IN_USE）
            hc, _, hb = api("DELETE", f"{ADMIN_BASE}/series/{sid}?hard=true", headers=h)
            assert hc == 409, f"有引用硬删应 409，实际 {hc}: {hb}"
            assert hb["code"] == "40908", f"应 40908，实际 {hb}"
            assert "班次" in hb.get("message", ""), f"message 应含引用计数: {hb}"

            # 系列未被删除（仍在）
            gc, _, gb = api("GET", f"{ADMIN_BASE}/series/{sid}", headers=h)
            assert gc == 200 and gb["data"]["id"] == sid, "409 后系列必须仍存在"
        finally:
            # best-effort 清理：班次仅软删端点（yn=0 仍持 FK）→ 系列无法物理删，
            # 残留 2 行（cohort yn=0 + series off_sale），唯一前缀 h1c 可枚举，登记 H2 清理。
            if cohort_id is not None:
                api("DELETE", f"{ADMIN_BASE}/cohorts/{cohort_id}", headers=h)
            dc, _, _ = api("DELETE", f"{ADMIN_BASE}/series/{sid}", headers=h)
            if dc == 200:
                pass  # 软删成功（off_sale，回收站可见，可人工复删）
            else:
                _hard_delete(h, sid)  # 若班次清理链路已放行引用则物理删


class TestHardDeleteZeroReference:
    """④（对偶验证）：零引用 → hard delete 200 真删 → GET 404。"""

    def test_hard_delete_zero_reference_succeeds(self, admin):
        h, uid = admin["headers"], admin["user_id"]
        code = _code()
        sid = _create_series(h, uid, code, sale_status="draft")
        hc, _, hb = _hard_delete(h, sid)
        assert hc == 200 and hb["code"] == 0, f"零引用硬删应 200: {hb}"
        assert "彻底删除" in hb.get("message", ""), f"message 应为真删语义: {hb}"
        gc, _, gb = api("GET", f"{ADMIN_BASE}/series/{sid}", headers=h)
        assert gc == 404 and gb["code"] == "40400", f"真删后 GET 应 404: {gc} {gb}"


class TestUploadIdPathTraversal:
    """Mimosa HIGH 修复回归（H1d）：upload_id 含路径穿越段 → 校验拒绝，不落盘。"""

    def test_traversal_upload_id_rejected(self, admin):
        h = admin["headers"]
        sc, _, sb = api("POST", f"{ADMIN_BASE}/videos/init-chunked?session_id=1&file_name=x.mp4&file_size=1024&chunk_count=1", h, {})
        assert sc == 200 and sb["code"] == 0, f"init 失败: {sb}"
        up = sb["data"]["upload_id"]
        import urllib.parse
        evil = urllib.parse.quote(up + "/../../evil", safe="")
        cc, _, cb = api("PUT", f"{ADMIN_BASE}/videos/upload-chunk/{evil}/0", h, {"_raw": "x"})
        # 变更单外新行为：非法 upload_id 走 VALIDATION 42200（HTTP 400/422），路由层 404 同样视为拒绝
        assert cc in (400, 404, 422) and (cc == 404 or cb.get("code") == "42200"), f"穿越 upload_id 未被拒绝: {cc} {cb}"
        # 合法 upload_id 正常工作（对偶验证）
        oc, _, ob = api("PUT", f"{ADMIN_BASE}/videos/upload-chunk/{up}/0", h, {"_raw": "x"})
        assert oc in (200, 400) and ob.get("code") in (0, "50301"), f"合法 upload_id 异常: {oc} {ob}"
