# -*- coding: utf-8 -*-
"""task12: 管理端课程 CRUD 契约测试 — 四级序列+分片上传占位 + 401 安全壳（直连 127.0.0.1:8000）

GWT 覆盖：
① 匿名 GET /api/admin/courses/series → 401 壳 {"code":"40101","data":null}
② 管理端系列 CRUD 端点可达（需有效 token，验证 200/422/404 壳）
③ 班次/模块/课次四级层级语义
④ 分片上传占位端点可达

边界：page_size=101/0 → 422 壳；不存在资源 → 404 壳；
Bearer 格式错误 → 401 壳。

代理防护：ProxyHandler({}) 禁用系统代理 + NO_PROXY 环境变量。
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

import pytest

# ── 代理防护 ──────────────────────
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

BASE = os.environ.get("TEST_BASE", "http://127.0.0.1:8000")
ADMIN_BASE = "/api/admin/courses"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def api(method: str, path: str, headers: dict | None = None, body: dict | None = None):
    """直连被测服务，返回 (status, headers, json_body)。"""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with _OPENER.open(req, timeout=15) as resp:
            return resp.status, resp.headers, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, e.headers, json.loads(raw)
        except ValueError:
            return e.code, e.headers, {"_raw": raw.decode("utf-8", "replace")}


# 一个有效的管理端 token（测试环境可用固定值；生产需从 /api/auth/login 获取）
# 此处使用占位——实际 GWT②~④ 需先获取有效 admin token
_VALID_ADMIN_TOKEN = os.environ.get("TEST_ADMIN_TOKEN", "")


def _admin_headers() -> dict:
    """返回带有效管理端 token 的请求头；若环境变量未设置则返回空 dict（测试会跳过）。"""
    if _VALID_ADMIN_TOKEN:
        return {"Authorization": f"Bearer {_VALID_ADMIN_TOKEN}"}
    return {}


# ════════════════════════════════════════════════════════════
# GWT① 匿名访问 → 401 壳
# ════════════════════════════════════════════════════════════
class TestAdminAuthGwt1:

    def test_anonymous_series_list_401(self):
        """GWT①：匿名 GET /api/admin/courses/series → 401 + code=40101 + data=null。"""
        code, _, body = api("GET", f"{ADMIN_BASE}/series")
        assert code == 401
        assert body["code"] == "40101"
        assert body["data"] is None
        assert isinstance(body["message"], str) and body["message"]

    def test_malformed_bearer_401(self):
        """Bearer 格式错误 → 401 壳。"""
        code, _, body = api("GET", f"{ADMIN_BASE}/series",
                            headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert code == 401
        assert body["code"] == "40101"

    def test_bearer_without_token_401(self):
        """只有 'Bearer' 无 token → 401 壳。"""
        code, _, body = api("GET", f"{ADMIN_BASE}/series",
                            headers={"Authorization": "Bearer"})
        assert code == 401
        assert body["code"] == "40101"

    def test_bearer_invalid_token_401(self):
        """Bearer + 无效 token → 401 壳。"""
        code, _, body = api("GET", f"{ADMIN_BASE}/series",
                            headers={"Authorization": "Bearer invalid.token.value"})
        assert code == 401
        assert body["code"] == "40101"


# ════════════════════════════════════════════════════════════
# GWT② 管理端系列 CRUD（需有效 token）
# ════════════════════════════════════════════════════════════
class TestSeriesAdminGwt2:

    def test_list_series_shell(self):
        """GWT②：系列列表返回正确壳（需有效 token）。"""
        headers = _admin_headers()
        if not headers:
            pytest.skip("无有效 TEST_ADMIN_TOKEN")
        code, _, body = api("GET", f"{ADMIN_BASE}/series?page=1&page_size=20", headers=headers)
        assert code == 200
        assert body["code"] == 0
        assert body["message"] == "ok"
        data = body["data"]
        assert isinstance(data, dict)
        assert set(data.keys()) == {"items", "total", "page", "page_size"}, \
            f"C2 外层 triple 权威，实际 keys={list(data.keys())}"
        assert isinstance(data["items"], list)
        assert isinstance(data["total"], int) and data["total"] >= 0
        assert data["page"] >= 1
        assert 1 <= data["page_size"] <= 100

    def test_get_series_not_found(self):
        """不存在的系列 → 404 壳。"""
        headers = _admin_headers()
        if not headers:
            pytest.skip("无有效 TEST_ADMIN_TOKEN")
        code, _, body = api("GET", f"{ADMIN_BASE}/series/99999999", headers=headers)
        assert code == 404
        assert body["code"] == "40400"
        assert body["data"] is None

    def test_create_series_validation(self):
        """创建系列参数校验失败 → 422 壳。"""
        headers = _admin_headers()
        if not headers:
            pytest.skip("无有效 TEST_ADMIN_TOKEN")
        # 缺少必填字段
        code, _, body = api("POST", f"{ADMIN_BASE}/series", headers=headers, body={})
        assert code == 422
        assert body["code"] == "42200"


# ════════════════════════════════════════════════════════════
# GWT③ 四级层级：series → cohorts → modules → sessions
# ════════════════════════════════════════════════════════════
class TestHierarchyGwt3:

    def test_cohort_list_by_series(self):
        """GWT③：班次列表按系列（需有效 token）。"""
        headers = _admin_headers()
        if not headers:
            pytest.skip("无有效 TEST_ADMIN_TOKEN")
        code, _, body = api("GET", f"{ADMIN_BASE}/series/1/cohorts", headers=headers)
        # 200 或 404（系列 1 可能不存在）—— 验证壳正确
        assert code in (200, 404)
        if code == 200:
            assert body["code"] == 0
            assert isinstance(body["data"], list)

    def test_module_list_by_cohort(self):
        """模块列表按班次（需有效 token，修复 P0：无 500）。"""
        headers = _admin_headers()
        if not headers:
            pytest.skip("无有效 TEST_ADMIN_TOKEN")
        code, _, body = api("GET", f"{ADMIN_BASE}/cohorts/1/modules", headers=headers)
        # task12-fix 修复前此处 500 Unknown column 'yn'；修复后必为 200 或 404
        assert code in (200, 404), f"module list should be 200/404, got {code}: {body}"
        assert code != 500
        if code == 200:
            assert body["code"] == 0
            assert isinstance(body["data"], list)

    def test_sessions_by_cohort_route(self):
        """班次下课次列表（批判②：cohort sessions 路由补全，需有效 token）。"""
        headers = _admin_headers()
        if not headers:
            pytest.skip("无有效 TEST_ADMIN_TOKEN")
        code, _, body = api("GET", f"{ADMIN_BASE}/cohorts/1/sessions", headers=headers)
        # 修复前 404（路由未命中）；修复后 200（列表）或 404（班次 1 不存在）
        assert code in (200, 404), f"cohort sessions should be 200/404, got {code}: {body}"
        assert code != 500
        if code == 200:
            assert body["code"] == 0

    def test_session_list_by_module(self):
        """课次列表按模块（需有效 token，修复 P0：无 500）。"""
        headers = _admin_headers()
        if not headers:
            pytest.skip("无有效 TEST_ADMIN_TOKEN")
        code, _, body = api("GET", f"{ADMIN_BASE}/modules/1/sessions", headers=headers)
        assert code in (200, 404)
        assert code != 500
        if code == 200:
            assert body["code"] == 0
            assert isinstance(body["data"], list)

    def test_delete_module_physical(self):
        """删除模块 → 物理 DELETE（修复 P0：无 500；断言 404 语义也行——200 表示成功删除）。"""
        headers = _admin_headers()
        if not headers:
            pytest.skip("无有效 TEST_ADMIN_TOKEN")
        code, _, body = api("DELETE", f"{ADMIN_BASE}/modules/99999999", headers=headers)
        assert code in (200, 404), f"delete module should be 200/404, got {code}: {body}"
        assert code != 500

    def test_delete_session_physical(self):
        """删除课次 → 物理 DELETE（修复 P0：无 500）。"""
        headers = _admin_headers()
        if not headers:
            pytest.skip("无有效 TEST_ADMIN_TOKEN")
        code, _, body = api("DELETE", f"{ADMIN_BASE}/sessions/99999999", headers=headers)
        assert code in (200, 404), f"delete session should be 200/404, got {code}: {body}"
        assert code != 500


# ════════════════════════════════════════════════════════════
# GWT④ 视频分片上传占位端点可达
# ════════════════════════════════════════════════════════════
class TestVideoEndpointsGwt4:

    def test_init_chunked_upload_placeholder(self):
        """GWT④：分片上传 init 占位（需有效 token）。"""
        headers = _admin_headers()
        if not headers:
            pytest.skip("无有效 TEST_ADMIN_TOKEN")
        # 用 query 参数模拟（简化占位）
        code, _, body = api(
            "POST",
            f"{ADMIN_BASE}/videos/init-chunked?session_id=1&file_name=test.mp4&file_size=1048576&chunk_count=4",
            headers=headers,
        )
        assert code in (200, 422)  # 422 可能因参数校验；200 表示占位实现
        if code == 200:
            assert body["code"] == 0
            assert "upload_id" in body["data"]

    def test_transcode_status_placeholder(self):
        """转码状态查询占位（需有效 token）。"""
        headers = _admin_headers()
        if not headers:
            pytest.skip("无有效 TEST_ADMIN_TOKEN")
        code, _, body = api("GET", f"{ADMIN_BASE}/videos/0/transcode-status", headers=headers)
        # 404（视频 0 不存在）或 200（占位返回模拟值）
        assert code in (200, 404)
        if code == 200:
            assert body["code"] == 0
            assert "transcode_status" in body["data"]


# ════════════════════════════════════════════════════════════
# 参数边界：422 壳
# ════════════════════════════════════════════════════════════
class TestValidation422:

    @pytest.mark.parametrize("qs", [
        "page_size=101",
        "page_size=0",
    ])
    def test_page_size_rejected(self, qs):
        """page_size 越界 → 422（需有效 token，否则 401 属鉴权先行）。"""
        headers = _admin_headers()
        if not headers:
            pytest.skip("无有效 TEST_ADMIN_TOKEN")
        code, _, body = api("GET", f"{ADMIN_BASE}/series?{qs}", headers=headers)
        assert code == 422
        assert body["code"] == "42200"

    def test_sort_invalid_rejected(self):
        """sort 白名单外 → 422（需有效 token）。"""
        headers = _admin_headers()
        if not headers:
            pytest.skip("无有效 TEST_ADMIN_TOKEN")
        code, _, body = api("GET", f"{ADMIN_BASE}/series?sort=xxx", headers=headers)
        assert code == 422
        assert body["code"] == "42200"

    def test_page_zero_rejected(self):
        """page=0 → 422（需有效 token）。"""
        headers = _admin_headers()
        if not headers:
            pytest.skip("无有效 TEST_ADMIN_TOKEN")
        code, _, body = api("GET", f"{ADMIN_BASE}/series?page=0", headers=headers)
        assert code == 422
        assert body["code"] == "42200"