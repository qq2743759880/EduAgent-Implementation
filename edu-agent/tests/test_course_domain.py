# -*- coding: utf-8 -*-
"""task11: 课程域契约测试 — series 5 端点 + 308 重定向 + Admin 鉴权（直连 127.0.0.1:8000）

GWT 覆盖：
① GET /api/series?category=编程&delivery_mode=online_live&keyword=信息 → on_sale/snake_case/外层分页/P95<200ms
② /api/curriculum/series?category=编程&page=2 → 308 → Location=/api/series?...（参数保留）
③ series → cohorts → modules(挂 cohort) → sessions(挂模块) → videos 层级语义
④ 匿名 GET /api/admin/users → 401 + {"code":"40101","data":null}

边界：page_size=101/0、delivery_mode/sort 非法值 → 422 壳；不存在资源 → 404 壳；
Bearer 格式错误 → 401 壳；全部 5 个旧端点 308（禁自动重定向）。

代理防护：ProxyHandler({}) 禁用系统代理 + NO_PROXY 环境变量（Windows 系统代理会卡死 127.0.0.1）。
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

# ── 代理防护（必须在构建 opener 前设置）──────────────────────
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

BASE = "http://127.0.0.1:8000"

# 308 响应不应被自动跟随：重定向处理器返回 None → urllib 抛 HTTPError(308)
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
CAMEL_CASE_RE = re.compile(r"[a-z][A-Z]")


def api(method: str, path: str, headers: dict | None = None, body: dict | None = None):
    """直连被测服务，返回 (status, headers, json_body)。headers 为原始 HTTPMessage（大小写不敏感）。"""
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


def location_of(headers) -> str | None:
    """取 Location 头（HTTPMessage 大小写不敏感；308 由 uvicorn 输出小写 location）。"""
    return headers.get("Location")


# ════════════════════════════════════════════════════════════
# GWT① 系列列表：筛选 + 壳契约 + snake_case + 外层分页 + P95
# ════════════════════════════════════════════════════════════
GWT1_PATH = (
    "/api/series?category=%E7%BC%96%E7%A8%8B&delivery_mode=online_live"
    "&keyword=%E4%BF%A1%E6%81%AF&page=1&page_size=20"
)  # category=编程 & keyword=信息（库内无 "Python" 字样数据，用 "信息" 等价验证）

SNAKE_REQUIRED_FIELDS = [
    "id", "institution_id", "delivery_mode", "series_code", "series_name",
    "sale_status", "category_names", "created_at", "updated_at",
]


class TestSeriesListGwt1:

    def test_shell_and_filter_semantics(self):
        """GWT①：code=0/message=ok；全部 on_sale、online_live；名称命中关键词；筛选非空。"""
        code, _, body = api("GET", GWT1_PATH)
        assert code == 200
        assert body["code"] == 0
        assert body["message"] == "ok"
        data = body["data"]
        assert isinstance(data, dict) and set(data.keys()) == {"items", "total", "page", "page_size"}
        items = data["items"]
        assert isinstance(items, list) and len(items) >= 1, "category=编程+online_live+keyword=信息 应有数据"
        for it in items:
            assert it["sale_status"] == "on_sale", f"列表必须只含在售系列，实际 {it['sale_status']}"
            assert it["delivery_mode"] == "online_live"
            # keyword 模糊命中 name/description/code 三列之一（用"信息"等价验证）
            joined = f"{it['series_name']}{it.get('description') or ''}{it['series_code']}"
            assert "信息" in joined, f"keyword=信息 未命中: {it['series_name']}"

    def test_snake_case_fields(self):
        """GWT①：字段 snake_case（与 edu.sql 列名一一对应，无 camelCase）。"""
        code, _, body = api("GET", GWT1_PATH)
        assert code == 200
        item = body["data"]["items"][0]
        for f in SNAKE_REQUIRED_FIELDS:
            assert f in item, f"列表项缺少字段 {f}"
        for name in item.keys():
            assert SNAKE_CASE_RE.match(name), f"字段名非 snake_case: {name}"
            assert not CAMEL_CASE_RE.search(name), f"字段名含 camelCase: {name}"
        # 外层分页字段同样 snake_case
        for name in body["data"].keys():
            assert SNAKE_CASE_RE.match(name), f"分页外层字段非 snake_case: {name}"

    def test_pagination_fields(self):
        """GWT①：外层分页 {total,page,page_size,items}（C-B 全站权威，C2 已删 page_meta 双轨）。"""
        code, _, body = api("GET", GWT1_PATH)
        assert code == 200
        assert set(body["data"].keys()) == {"items", "total", "page", "page_size"}
        assert body["data"]["page"] == 1
        assert body["data"]["page_size"] == 20
        assert isinstance(body["data"]["total"], int) and body["data"]["total"] >= 1

    def test_p95_latency_under_200ms(self):
        """GWT①：P95 < 200ms（预热 2 次 + 计 20 次，模拟验收口径）。"""
        url = BASE + GWT1_PATH
        for _ in range(2):  # 预热（连接池/缓存），不计入
            api("GET", GWT1_PATH)
        durations = []
        for _ in range(20):
            req = urllib.request.Request(url, method="GET")
            t0 = time.perf_counter()
            with _OPENER.open(req, timeout=15):
                pass
            durations.append((time.perf_counter() - t0) * 1000)
        durations.sort()
        p95 = durations[int(round(0.95 * (len(durations) - 1)))]
        assert p95 < 200, f"P95={p95:.1f}ms 超出 200ms（样本 {durations}）"


# ════════════════════════════════════════════════════════════
# GWT② 旧端点 308 永久重定向（禁自动重定向 + 参数保留）
# ════════════════════════════════════════════════════════════
class TestLegacy308Gwt2:

    def test_series_list_308_with_params(self):
        """GWT②：/api/curriculum/series?category=编程&page=2 → 308 → /api/series?category=编程&page=2。"""
        code, headers, _ = api("GET", "/api/curriculum/series?category=%E7%BC%96%E7%A8%8B&page=2")
        assert code == 308, f"期望 308，实际 {code}"
        loc = location_of(headers)
        assert loc is not None, "308 缺少 Location 头"
        # Location 为百分号编码形式，解码后参数完整保留
        assert urllib.parse.unquote(loc) == "/api/series?category=编程&page=2", f"Location={loc}"

    def test_308_series_detail(self):
        code, headers, _ = api("GET", "/api/curriculum/series/5")
        assert code == 308
        assert location_of(headers) == "/api/series/5"

    def test_308_series_cohorts(self):
        code, headers, _ = api("GET", "/api/curriculum/series/5/cohorts")
        assert code == 308
        assert location_of(headers) == "/api/series/5/cohorts"

    def test_308_series_modules_to_detail(self):
        """旧 /modules 层级已变（模块挂 cohort）→ 308 至系列详情。"""
        code, headers, _ = api("GET", "/api/curriculum/series/5/modules")
        assert code == 308
        assert location_of(headers) == "/api/series/5"

    def test_308_series_tree_to_detail(self):
        """旧 /tree 层级已变 → 308 至系列详情。"""
        code, headers, _ = api("GET", "/api/curriculum/series/5/tree")
        assert code == 308
        assert location_of(headers) == "/api/series/5"

    def test_308_preserves_multi_params(self):
        """GWT② 补充：多参数全量保留（含 keyword/sort/page_size）。"""
        code, headers, _ = api(
            "GET",
            "/api/curriculum/series?keyword=%E4%BF%A1%E6%81%AF&sort=price_asc&page_size=50&page=3",
        )
        assert code == 308
        loc = location_of(headers)
        assert loc is not None
        parsed = urllib.parse.urlparse(loc)
        assert parsed.path == "/api/series"
        q = urllib.parse.parse_qs(parsed.query)
        assert q.get("keyword") == ["信息"]
        assert q.get("sort") == ["price_asc"]
        assert q.get("page_size") == ["50"]
        assert q.get("page") == ["3"]


# ════════════════════════════════════════════════════════════
# GWT③ 层级语义：series → cohorts → modules(挂 cohort) → sessions(挂模块) → videos
# ════════════════════════════════════════════════════════════
def _first_series_with_full_chain(max_series: int = 5):
    """从列表前 N 个在售系列中找一个有 班次→模块→课次(含视频) 完整链路的，返回 (series, cohort)。"""
    code, _, body = api("GET", "/api/series?page=1&page_size=%d" % max_series)
    assert code == 200
    for s in body["data"]["items"]:
        c2, _, b2 = api("GET", f"/api/series/{s['id']}/cohorts")
        assert c2 == 200
        cohort_items = b2["data"]["items"] if isinstance(b2["data"], dict) else b2["data"]
        for coh in cohort_items:
            c3, _, b3 = api("GET", f"/api/cohorts/{coh['id']}/modules")
            assert c3 == 200
            for m in b3["data"]["modules"]:
                if m["sessions"] and all(s.get("videos") for s in m["sessions"]):
                    return s, coh
    pytest.skip(f"前 {max_series} 个系列无完整 series→cohort→module→session→video 链路")


class TestHierarchyGwt3:

    def test_series_detail_and_cohorts(self):
        """系列详情（含聚合）→ 班次列表挂在 series 下。"""
        s, coh = _first_series_with_full_chain()
        code, _, body = api("GET", f"/api/series/{s['id']}")
        assert code == 200 and body["code"] == 0
        detail = body["data"]
        assert detail["id"] == s["id"]
        assert detail["sale_status"] == "on_sale"
        assert isinstance(detail["categories"], list)
        assert isinstance(detail["cohort_count"], int) and detail["cohort_count"] >= 1
        # 班次列表：分页壳 {total,page,page_size,items}，每条 cohort.series_id == series.id
        code, _, body = api("GET", f"/api/series/{s['id']}/cohorts")
        assert code == 200
        data = body["data"]
        assert isinstance(data, dict) and set(data.keys()) == {"items", "total", "page", "page_size"}
        cohorts = data["items"]
        assert isinstance(cohorts, list) and len(cohorts) >= 1
        for c in cohorts:
            assert c["series_id"] == s["id"], "班次必须挂 series"
            assert c["yn"] == 1

    def test_cohort_detail_modules_attached_to_cohort(self):
        """模块挂 cohort：/api/cohorts/{id} 返回 {cohort, modules}，module.cohort_id 一致。"""
        s, coh = _first_series_with_full_chain()
        code, _, body = api("GET", f"/api/cohorts/{coh['id']}")
        assert code == 200 and body["code"] == 0
        data = body["data"]
        assert set(data.keys()) >= {"cohort", "modules"}
        assert data["cohort"]["id"] == coh["id"]
        assert isinstance(data["modules"], list) and len(data["modules"]) >= 1
        for m in data["modules"]:
            assert m["cohort_id"] == coh["id"], "模块必须挂 cohort（非 series）"

    def test_modules_sessions_videos_hierarchy(self):
        """课次挂模块：session.series_cohort_course_id == module.id；视频内嵌课次。"""
        s, coh = _first_series_with_full_chain()
        code, _, body = api("GET", f"/api/cohorts/{coh['id']}/modules")
        assert code == 200 and body["code"] == 0
        data = body["data"]
        assert data["cohort_id"] == coh["id"]
        modules = data["modules"]
        assert len(modules) >= 1
        found_session = False
        for m in modules:
            assert m["cohort_id"] == coh["id"]
            for sess in m["sessions"]:
                found_session = True
                assert sess["series_cohort_course_id"] == m["id"], "课次必须挂模块（series_cohort_course 表）"
                for v in sess["videos"]:
                    assert v["asset_id"] and v["video_code"]
                    assert v["transcode_status"] in ("completed", "processing", "failed")
        assert found_session, "至少一个课次"


# ════════════════════════════════════════════════════════════
# GWT④ Admin 鉴权：匿名/格式错 → 401 壳 {"code":"40101","data":null}
# ════════════════════════════════════════════════════════════
class TestAdminAuthGwt4:

    def test_anonymous_admin_users_401(self):
        """GWT④：匿名 GET /api/admin/users → 401 + code=40101 + data=null。"""
        code, _, body = api("GET", "/api/admin/users")
        assert code == 401
        assert body["code"] == "40101"
        assert body["data"] is None
        assert isinstance(body["message"], str) and body["message"]

    def test_malformed_bearer_401(self):
        """Bearer 格式错误（非 Bearer 方案）→ 401 壳。"""
        code, _, body = api("GET", "/api/admin/users", headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert code == 401
        assert body["code"] == "40101"
        assert body["data"] is None

    def test_bearer_without_token_401(self):
        """只有 'Bearer' 无 token → 401 壳。"""
        code, _, body = api("GET", "/api/admin/users", headers={"Authorization": "Bearer"})
        assert code == 401
        assert body["code"] == "40101"
        assert body["data"] is None

    def test_bearer_invalid_token_401(self):
        """Bearer + 无效 token 字符串 → 401 壳（fail-closed）。"""
        code, _, body = api(
            "GET", "/api/admin/users",
            headers={"Authorization": "Bearer invalid.token.value"},
        )
        assert code == 401
        assert body["code"] == "40101"
        assert body["data"] is None

    def test_401_shell_has_www_authenticate(self):
        """401 应带 WWW-Authenticate: Bearer（RFC 6750）。"""
        code, headers, _ = api("GET", "/api/admin/users")
        assert code == 401
        assert "Bearer" in (headers.get("WWW-Authenticate") or "")


# ════════════════════════════════════════════════════════════
# 参数边界：422 壳（字符串错误码 42200）
# ════════════════════════════════════════════════════════════
class TestValidation422:

    @pytest.mark.parametrize("qs", [
        "page_size=101",          # 上界 +1 拒绝
        "page_size=0",            # 下界 -1 拒绝
    ])
    def test_page_size_rejected(self, qs):
        code, _, body = api("GET", f"/api/series?{qs}")
        assert code == 422
        assert body["code"] == "42200", "422 壳必须为字符串错误码 42200"
        assert isinstance(body["message"], str) and body["message"]
        # FastAPI 校验错误详情（loc 指向 query.page_size）
        detail = body.get("data")
        assert isinstance(detail, list) and detail, "422 壳 data 应带校验详情"
        assert any("page_size" in str(d.get("loc", [])) for d in detail)

    def test_delivery_mode_invalid_rejected(self):
        """delivery_mode 白名单外 → 422 壳。"""
        code, _, body = api("GET", "/api/series?delivery_mode=hybrid")
        assert code == 422
        assert body["code"] == "42200"
        detail = body["data"]
        assert any("delivery_mode" in str(d.get("loc", [])) for d in detail)

    def test_sort_invalid_rejected(self):
        """sort 白名单外（含注入尝试）→ 422 壳。"""
        code, _, body = api("GET", "/api/series?sort=xxx;DROP%20TABLE%20series")
        assert code == 422
        assert body["code"] == "42200"
        detail = body["data"]
        assert any("sort" in str(d.get("loc", [])) for d in detail)

    def test_page_zero_rejected(self):
        """page=0 → 422 壳（页码从 1 开始）。"""
        code, _, body = api("GET", "/api/series?page=0")
        assert code == 422
        assert body["code"] == "42200"


# ════════════════════════════════════════════════════════════
# 404 壳：不存在资源
# ════════════════════════════════════════════════════════════
class TestNotFound404:

    @pytest.mark.parametrize("path", [
        "/api/series/99999999",
        "/api/series/99999999/cohorts",
        "/api/cohorts/99999999",
        "/api/cohorts/99999999/modules",
    ])
    def test_not_found_shell(self, path):
        code, _, body = api("GET", path)
        assert code == 404
        assert body["code"] == "40400", "404 壳必须为字符串错误码 40400"
        assert body["data"] is None
        assert isinstance(body["message"], str) and body["message"]
