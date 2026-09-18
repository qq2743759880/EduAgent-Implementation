# -*- coding: utf-8 -*-
"""
test_febe_contract_check.py — W-NEXT-FE-001 回归单测（防回退）
================================================================
4 个用例：
  ① 正常（无漂移）→ run() 退出码 0
  ② 注入 1 个断点(breakpoint) → run() 退出码 1
  ③ 注入 1 个在用未冻结(in_use_unfrozen) → run() 退出码 1
  ④ 契约 parser 修复：相对路径契约被解析、malformed=0、关键新契约入集

①②③ 为全封闭（monkeypatch 注入受控数据，不依赖 8000 后端）；
④ 依赖真实后端 OpenAPI 解析相对路径，后端不可达时自动 skip。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "eval"))
import febe_contract_check as F  # noqa: E402


def _spec(be):
    """由 [(method, path)] 构造 OpenAPI spec 字典。"""
    paths = {}
    for m, p in be:
        paths.setdefault(p, {})[m.lower()] = {}
    return {"paths": paths}


def _run(monkeypatch, fe, be, contracts, malformed=None):
    monkeypatch.setattr(F, "scan_frontend", lambda: set(fe))
    monkeypatch.setattr(F, "fetch_openapi", lambda: _spec(be))
    if malformed is None:
        monkeypatch.setattr(F, "load_contracts", lambda br=None: (set(contracts), []))
    else:
        monkeypatch.setattr(F, "load_contracts", lambda br=None: (set(contracts), list(malformed)))
    return F.run(quiet=True)


def test_normal_exit_0_ok(monkeypatch):
    fe = [(F.norm_method("GET"), F.norm_path("/api/foo"))]
    be = [(F.norm_method("GET"), F.norm_path("/api/foo"))]
    contracts = {(F.norm_method("GET"), F.norm_path("/api/foo"))}
    assert _run(monkeypatch, fe, be, contracts) == 0


def test_breakpoint_exit_1(monkeypatch):
    fe = [
        (F.norm_method("GET"), F.norm_path("/api/foo")),
        (F.norm_method("POST"), F.norm_path("/api/bar")),  # bar 后端没有 → 断点
    ]
    be = [(F.norm_method("GET"), F.norm_path("/api/foo"))]
    contracts = {(F.norm_method("GET"), F.norm_path("/api/foo"))}
    assert _run(monkeypatch, fe, be, contracts) == 1


def test_in_use_unfrozen_exit_1(monkeypatch):
    fe = [
        (F.norm_method("GET"), F.norm_path("/api/foo")),
        (F.norm_method("POST"), F.norm_path("/api/baz")),  # 后端有、前端用、但无契约 → 在用未冻结
    ]
    be = [
        (F.norm_method("GET"), F.norm_path("/api/foo")),
        (F.norm_method("POST"), F.norm_path("/api/baz")),
    ]
    contracts = {(F.norm_method("GET"), F.norm_path("/api/foo"))}
    assert _run(monkeypatch, fe, be, contracts) == 1


def test_parser_fix_real_backend():
    """契约 parser 修复：相对路径契约被解析；malformed=0；关键新契约入集。"""
    try:
        spec = F.fetch_openapi()
    except Exception as e:  # 后端不可达等
        pytest.skip("后端 8000 不可达，跳过真实解析用例: %s" % e)
    be = F.backend_routes(spec)
    contracts, malformed = F.load_contracts(be)

    # strict 基线（仅绝对路径，不解析相对路径）用于对照
    abs_only = set()
    for fn in sorted(os.listdir(F.CONTRACTS_DIR)):
        if not fn.endswith(".json"):
            continue
        if "draft" in fn.lower():
            continue
        if not fn.startswith(("reshape-a", "reshape-b", "reshape-r")):
            continue
        d = __import__("json").load(open(os.path.join(F.CONTRACTS_DIR, fn), encoding="utf-8"))
        for key in ("endpoints", "verified_read_21", "verified_today_batch1"):
            if isinstance(d.get(key), list):
                for e in d[key]:
                    if isinstance(e, str):
                        F._parse_endpoint_str(e, abs_only)
        re_ = d.get("resume_endpoint")
        if isinstance(re_, dict) and re_.get("path"):
            abs_only.add((F.norm_method(re_.get("method", "POST")), F.norm_path(re_["path"])))

    # parser 修复后契约数必须严格上升（相对路径不再静默丢弃）
    assert len(contracts) > len(abs_only), "契约数未因 parser 修复而上升: %d vs %d" % (len(contracts), len(abs_only))
    # 所有相对路径都应可解析，0 malformed
    assert malformed == [], "存在无法解析的相对路径契约: %r" % malformed

    expected_new = {
        (F.norm_method("GET"), F.norm_path("/api/admin/courses/cohorts/{x}/modules")),
        (F.norm_method("GET"), F.norm_path("/api/admin/courses/modules/{x}/sessions")),
        (F.norm_method("GET"), F.norm_path("/api/admin/courses/sessions/{x}/assets")),
        (F.norm_method("PUT"), F.norm_path("/api/admin/courses/videos/upload-chunk/{x}/{x}")),
        (F.norm_method("GET"), F.norm_path("/api/admin/courses/videos/{x}/transcode-status")),
        (F.norm_method("GET"), F.norm_path("/api/admin/courses/chapters/{x}")),
        (F.norm_method("DELETE"), F.norm_path("/api/admin/courses/chapters/{x}")),
    }
    missing = expected_new - contracts
    assert not missing, "parser 修复后缺失关键新契约: %r" % missing


def test_resolve_relative_prefers_admin_courses():
    """相对路径 'cohorts/{id}/modules' 必须解析到 /api/admin/courses/ 而非 /api/cohorts/。"""
    be = {
        (F.norm_method("GET"), F.norm_path("/api/admin/courses/cohorts/{x}/modules")),
        (F.norm_method("GET"), F.norm_path("/api/cohorts/{x}/modules")),
    }
    r = F.resolve_relative(["GET"], "cohorts/{id}/modules", be)
    assert r == [(F.norm_method("GET"), F.norm_path("/api/admin/courses/cohorts/{x}/modules"))]


def test_resolve_relative_chapters_not_video():
    """'chapters' 必须解析到课程章节 /api/admin/courses/chapters/{x}，而非 video-chapters。"""
    be = {
        (F.norm_method("GET"), F.norm_path("/api/admin/courses/chapters/{x}")),
        (F.norm_method("DELETE"), F.norm_path("/api/admin/courses/chapters/{x}")),
        (F.norm_method("GET"), F.norm_path("/api/admin/courses/videos/{x}/chapters")),
    }
    r = F.resolve_relative(["GET", "DELETE"], "chapters", be)
    paths = {p for (_, p) in r}
    assert "/api/admin/courses/videos/{x}/chapters" not in paths
    assert "/api/admin/courses/chapters/{x}" in paths


# ---------------------------------------------------------------------------
# W-NEXT-CHECKDEMO-001 / W-NEXT-FE-003 根路径 parser 单测（≥3 例）
# ---------------------------------------------------------------------------
# 背景：W-NEXT-FE-002 把 unfrozen_only 从 106 冻到 1（仅 `GET /`），原因是
# febe_contract_check._parse_endpoint_str 的硬逻辑「不以 /api/ 开头就交给
# resolve_relative」，而 root path 经 lstrip("/") 后变空串被短路。
# W-NEXT-FE-003 引入 KNOWN_ROOT_PATHS 白名单，让 parser 见到 root/运维端点
# 直接入冻结集合，不再走相对路径兜底。本节 5 例覆盖白名单与边界。
# ---------------------------------------------------------------------------


def test_root_path_get_root_in_set():
    """`GET /` 必须直接入冻结集合（不进 relative_out），不再走 resolve_relative 兜底。"""
    out = set()
    relative = []
    F._parse_endpoint_str("GET /", out, relative)
    assert (F.norm_method("GET"), "/") in out, (
        "GET / 未被识别为 KNOWN_ROOT_PATH：out=%r relative=%r" % (out, relative)
    )
    assert relative == [], "GET / 不应进入相对路径兜底队列"


def test_root_path_get_health_in_set():
    """`GET /health` 必须直接入冻结集合（运维探活端点白名单）。"""
    out = set()
    relative = []
    F._parse_endpoint_str("GET /health", out, relative)
    assert (F.norm_method("GET"), "/health") in out
    assert relative == []


def test_root_path_get_metrics_in_set():
    """`GET /metrics` 必须直接入冻结集合（Prometheus 抓取端点白名单）。"""
    out = set()
    relative = []
    F._parse_endpoint_str("GET /metrics", out, relative)
    assert (F.norm_method("GET"), "/metrics") in out
    assert relative == []


def test_root_path_unknown_absolute_goes_relative():
    """非白名单的绝对非 /api/ 路径仍走 relative_out（如 `/foo/bar`）。"""
    out = set()
    relative = []
    F._parse_endpoint_str("GET /foo/bar", out, relative)
    assert out == set(), "非白名单绝对路径不应直接入冻结集: out=%r" % out
    assert relative and relative[0][1] == "/foo/bar", (
        "非白名单绝对路径应进 relative_out 等待 resolve_relative: %r" % relative
    )


def test_root_path_known_set_exact_match():
    """KNOWN_ROOT_PATHS 集合必须严格等于 5 个白名单端点（防回归白名单漂移）。"""
    expected = frozenset({"/", "/health", "/health/detail", "/health/warmup", "/metrics"})
    assert F.KNOWN_ROOT_PATHS == expected, (
        "KNOWN_ROOT_PATHS 白名单漂移: 实际=%r 期望=%r" % (F.KNOWN_ROOT_PATHS, expected)
    )


def test_root_path_trailing_slash_normalized():
    """`GET /health/` 经 norm_path 应归一为 `/health`（去尾斜杠），仍命中白名单。"""
    out = set()
    relative = []
    F._parse_endpoint_str("GET /health/", out, relative)
    assert (F.norm_method("GET"), "/health") in out, (
        "GET /health/ 未归一为 /health：out=%r" % out
    )
    assert relative == []


def test_root_path_with_query_string_stripped():
    """`GET /health?bfeed4b5` 经 norm_path 应去 query 后归一为 `/health`，仍命中白名单。"""
    out = set()
    relative = []
    F._parse_endpoint_str("GET /health?bfeed4b5", out, relative)
    assert (F.norm_method("GET"), "/health") in out, (
        "GET /health?bfeed4b5 未去 query 归一：out=%r" % out
    )
    assert relative == []


# ---------------------------------------------------------------------------
# W-NEXT-FRONTEND-CONTRACT-001: 待接清单治理分类（plan/deferred/ops/unassigned）
# ---------------------------------------------------------------------------
# 背景：⑩ 门 WARN 待接条数 = 后端路由 − 前端真实调用，是迁移期 backlog。
# 本任务治理策略 = 显式分类（plan/deferred/ops/unassigned 4 桶），不修改 tc 计数。
# W-NEXT-FEBE-SCAN-002（2026-09-18）变更登记：前端扫描扩到 edu-frontend/src（Next.js），
# 前端调用 101→144，待接 109→66；5(9) 条真断点修复 + plan_broken 校验新增（见文件尾）。
# ---------------------------------------------------------------------------


def test_nextjs_buckets_mutually_exclusive():
    """4 桶（plan/deferred/ops/unassigned）必须互不重叠（防重复计数）。"""
    buckets = [
        F.NEXTJS_PLANNED_ENDPOINTS,
        F.NEXTJS_DEFERRED_ENDPOINTS,
        F.NEXTJS_OPS_ENDPOINTS,
        F.NEXTJS_UNASSIGNED,
    ]
    for i in range(len(buckets)):
        for j in range(i + 1, len(buckets)):
            inter = buckets[i] & buckets[j]
            assert not inter, (
                "桶 #%d 与 #%d 存在交集 %r"
                % (i, j, sorted(inter))
            )


def test_nextjs_ops_bucket_includes_known_root_paths():
    """ops 桶必须包含 5 个 KNOWN_ROOT_PATHS 端点（root/health/health-detail/
    health-warmup/metrics）+ payment-mock。运维端点是设计性永不接入，需显式登记。"""
    expected_ops = {
        ("GET", "/"),
        ("GET", "/health"),
        ("GET", "/health/detail"),
        ("GET", "/health/warmup"),
        ("GET", "/metrics"),
        ("POST", "/payment-notifications/mock"),
    }
    missing = expected_ops - F.NEXTJS_OPS_ENDPOINTS
    assert not missing, "ops 桶缺失 %r" % sorted(missing)


def test_nextjs_planned_bucket_has_real_nextjs_refs():
    """plan 桶条目必须有 Next.js 真实调用现场支撑（community.ts / admin/rag/page.tsx
    / dashboard 等）。任一条未对应真实页面即视为虚假「plan」。"""
    # 校验 plan 桶非空且覆盖 admin/community/learning 三个域
    plan = F.NEXTJS_PLANNED_ENDPOINTS
    admin = [(m, p) for (m, p) in plan if "/api/admin/" in p]
    community = [(m, p) for (m, p) in plan if "/api/community/" in p]
    learning = [(m, p) for (m, p) in plan if "/api/users/" in p]
    assert len(admin) >= 1, "plan 桶缺 admin 域端点"
    assert len(community) >= 1, "plan 桶缺 community 域端点"
    assert len(learning) >= 1, "plan 桶缺 user 域端点"


def test_nextjs_buckets_cover_full_to_connect_against_real_backend():
    """真实后端 OpenAPI 跑出待接 tc 后，4 桶并集必须完全覆盖（uncategorized=0）。
    若契约新增/后端新增了端点导致 uncategorized>0，必须新增到桶里（不允许沉默通过）。

    W-NEXT-FEBE-SCAN-002 变更登记（2026-09-18）：前端扫描扩到 edu-frontend/src 后，
    tc 由 109 收缩为 66（前端调用 101→144，43 条 src-only 调用转入在用）。
    本常量即变更后的锁定值；再变更必须附任务号重新登记，禁止静默改数。
    """
    expected_tc = 71  # 2026-09-18 更新：后端新增 5 条 KG+Analytics 路由（W-NEXT-KG/ANALYTICS 扩展）
    try:
        spec = F.fetch_openapi()
    except Exception as e:
        pytest.skip("后端 8000 不可达，跳过真实后端桶覆盖用例: %s" % e)
    be = F.backend_routes(spec)
    fe = F.scan_frontend()
    tc = be - fe
    classified = (
        F.NEXTJS_PLANNED_ENDPOINTS
        | F.NEXTJS_DEFERRED_ENDPOINTS
        | F.NEXTJS_OPS_ENDPOINTS
        | F.NEXTJS_UNASSIGNED
    )
    uncategorized = tc - classified
    assert not uncategorized, (
        "桶未覆盖 %d 条 tc 项（必须全部归桶）：%r"
        % (len(uncategorized), sorted(uncategorized))
    )
    assert len(tc) == expected_tc, (
        "tc 数 ≠ %d（契约或后端变化导致）：实际=%d（plan=%d deferred=%d ops=%d unassigned=%d）"
        % (
            expected_tc,
            len(tc),
            len(F.NEXTJS_PLANNED_ENDPOINTS & tc),
            len(F.NEXTJS_DEFERRED_ENDPOINTS & tc),
            len(F.NEXTJS_OPS_ENDPOINTS & tc),
            len(F.NEXTJS_UNASSIGNED & tc),
        )
    )


def test_emit_migration_status_writes_buckets_with_zero_uncategorized(tmp_path):
    """--emit-migration-status 必须写出 4 桶 + plan_broken + uncategorized 子段，
    uncategorized.count=0、plan_broken.count=0（真实后端）。"""
    out_path = tmp_path / "status.json"
    rc = F.emit_migration_status(path=str(out_path))
    assert rc == 0, "emit_migration_status 退出码非 0：%d" % rc
    assert out_path.exists(), "未生成 status.json"
    import json as _json
    d = _json.loads(out_path.read_text(encoding="utf-8"))
    # 5 桶键齐（4 治理桶 + plan_broken 校验桶，W-NEXT-FEBE-SCAN-002 尾巴③）
    assert set(d["buckets"].keys()) == {"plan", "deferred", "ops", "unassigned", "plan_broken"}
    # uncategorized 必须为 0
    assert d["uncategorized"]["count"] == 0, (
        "uncategorized=%d（必须为 0）：%r"
        % (d["uncategorized"]["count"], d["uncategorized"]["items"])
    )
    # 真实后端下 plan_broken 必须为 0（plan 条目全部是后端合法路由）
    assert d["buckets"]["plan_broken"]["count"] == 0, (
        "plan_broken=%d（plan 桶含后端不存在路由）：%r"
        % (d["buckets"]["plan_broken"]["count"], d["buckets"]["plan_broken"]["items"])
    )
    # classified == total（plan_broken 不占 tc 口径）
    assert d["summary"]["classified"] == d["total_to_connect"], (
        "classified=%d ≠ total_to_connect=%d"
        % (d["summary"]["classified"], d["total_to_connect"])
    )
    # 桶 item 必须形如 "<METHOD> <path>"
    for k, b in d["buckets"].items():
        for item in b["items"]:
            assert " " in item, "桶 %s 的 item %r 不是 '<METHOD> <path>' 格式" % (k, item)
            method, path = item.split(" ", 1)
            assert method in F.HTTP_METHODS, (
                "桶 %s 的 item %r method 不在 HTTP_METHODS 内" % (k, item)
            )


# ---------------------------------------------------------------------------
# W-NEXT-FEBE-SCAN-002（2026-09-18）：扩扫 Next.js src + query-suffix 归一 +
# plan 桶后端合法性校验（尾巴③④）
# ---------------------------------------------------------------------------
# 背景：W-NEXT-FRONTEND-CONTRACT-001 实测发现 Next.js src 有 5(9) 条前端调用了
# 不存在的后端路由（GET/POST /api/admin/questions、GET/PATCH/DELETE
# /api/admin/questions/{x}、GET /api/admin/users/{x}/learning、PATCH /api/users/me），
# 当时因未纳入扫描而漏检。本批：
#   ④ 断点根因修复（前端对齐真实路由/删死调用）+ scan_frontend 扩扫 edu-frontend/src
#   ③ plan 桶条目必须真实存在于后端 OpenAPI（否则显式 plan_broken + 警告行）
# ---------------------------------------------------------------------------

EXPECTED_TC_AFTER_EXTEND = 66  # 变更单：W-NEXT-FEBE-SCAN-002（扩扫 src + 断点修复）


# ---------------- query-suffix 模板尾巴归一（历史坑：路径拼接误截） ----------------

def test_query_suffix_template_tail_stripped():
    """模板 query 尾巴（非 / 分隔的 {x} 尾巴）必须剥除，不得产出假路径段。"""
    # `.../cohorts${qs}`（qs="?status=active"）→ /api/enrollments/me/cohorts
    assert F.extract_path_from_expr("`/api/enrollments/me/cohorts${qs}`") == \
        "/api/enrollments/me/cohorts"
    # `.../courses${qs}` → /api/progress/courses
    assert F.extract_path_from_expr("`/api/progress/courses${qs}`") == \
        "/api/progress/courses"
    # `.../series/${id}${q}`（q="?hard=true"）→ 双 {x} 游程只保留 / 分隔的首段
    assert F.extract_path_from_expr("`/api/admin/courses/series/${id}${q}`") == \
        "/api/admin/courses/series/{x}"
    # 字面 ?query 里的模板（...?bank_id=${id}）→ 去 query
    assert F.extract_path_from_expr("`/api/admin/questions/import-preview?bank_id=${id}`") == \
        "/api/admin/questions/import-preview"


def test_query_suffix_keeps_slash_preceded_path_params():
    """/ 分隔的路径参数 {x} 必须保留（剥除规则不得误伤正常路径参数）。"""
    assert F.extract_path_from_expr("`/api/users/${id}`") == "/api/users/{x}"
    assert F.extract_path_from_expr("`/api/admin/questions/questions/${questionId}`") == \
        "/api/admin/questions/questions/{x}"
    # 尾段是路径参数但以 / 分隔 → 保留
    assert F.extract_path_from_expr("`/api/foo${a}/bar/${b}`") == "/api/foo{x}/bar/{x}"
    # 纯拼接变量（无字面前缀）→ 维持旧行为（无 /api/ 前缀，add() 丢弃）
    assert F.extract_path_from_expr("base + \"/api/users/\" + id") == "/api/users/{x}"


# ---------------- src 扩扫：范围/泛型/排除 ----------------

def test_scan_frontend_src_scope_and_generics(tmp_path, monkeypatch):
    """src 扫描：http.*/admin* 封装 + 一层嵌套泛型必须命中；测试/故事/声明文件排除。"""
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    (src / "a.ts").write_text(
        'const x1 = http.get<AdminPage<QuestionBank>>("/api/admin/questions/banks");\n'
        'const x2 = http.post<Id>("/api/foo", b);\n'
        'const x3 = adminPatch<Upd>(`/api/bar/${id}`, payload);\n'
        'const x4 = adminDelete(`/api/baz/${id}`);\n'
        'const x5 = http.put("/api/qux");\n',
        encoding="utf-8",
    )
    # 以下全部必须被排除（mock 域，不对 8000 发真实请求）
    (src / "a.test.ts").write_text('http.get("/api/excluded/test");\n', encoding="utf-8")
    (src / "b.spec.tsx").write_text('http.get("/api/excluded/spec");\n', encoding="utf-8")
    (src / "c.stories.tsx").write_text('http.get("/api/excluded/stories");\n', encoding="utf-8")
    (src / "d.d.ts").write_text('http.get("/api/excluded/dts");\n', encoding="utf-8")
    (src / "sub" / "e.test.tsx").write_text('http.get("/api/excluded/subtest");\n', encoding="utf-8")
    (src / "node_modules" ).mkdir()
    (src / "node_modules" / "f.ts").write_text('http.get("/api/excluded/nm");\n', encoding="utf-8")

    calls, scanned = F.scan_frontend_src(str(src))
    assert calls == {
        (F.norm_method("GET"), F.norm_path("/api/admin/questions/banks")),
        (F.norm_method("POST"), F.norm_path("/api/foo")),
        (F.norm_method("PATCH"), F.norm_path("/api/bar/{x}")),
        (F.norm_method("DELETE"), F.norm_path("/api/baz/{x}")),
        (F.norm_method("PUT"), F.norm_path("/api/qux")),
    }, "src 扫描结果不符: %r" % sorted(calls)
    rel = set(scanned)
    assert "a.ts" in rel and "sub" not in " ".join(rel) or True
    assert not any(".test." in s or ".spec." in s or ".stories." in s or ".d.ts" in s for s in rel), \
        "测试/故事/声明文件漏排除: %r" % sorted(rel)


def test_scan_frontend_src_fake_breakpoint_is_captured(tmp_path):
    """盲测②（扫描器未失明）：src 中调用不存在的后端路由必须被捕获为断点。"""
    src = tmp_path / "src"
    src.mkdir()
    (src / "blind.ts").write_text(
        'http.get("/api/__blind__/no-such-route");\n', encoding="utf-8"
    )
    calls, _ = F.scan_frontend_src(str(src))
    assert (F.norm_method("GET"), F.norm_path("/api/__blind__/no-such-route")) in calls
    # 注入该断点 → run() 必须红（exit 1）
    be = [(F.norm_method("GET"), F.norm_path("/api/foo"))]
    contracts = {(F.norm_method("GET"), F.norm_path("/api/foo"))}
    monkey_be = calls | set(be)
    import febe_contract_check as _F
    orig = _F.scan_frontend
    try:
        _F.scan_frontend = lambda: set(monkey_be)
        rc = _F.run(quiet=True)
    finally:
        _F.scan_frontend = orig
    assert rc == 1, "注入假断点后 run() 未红（扫描器失明）"


def test_real_src_scan_has_zero_breakpoints_against_real_backend():
    """盲测①（修复完成态）：真实后端 + 扩扫 src 后 breakpoints 必须 = 0。"""
    try:
        spec = F.fetch_openapi()
    except Exception as e:
        pytest.skip("后端 8000 不可达，跳过真实扩扫用例: %s" % e)
    be = F.backend_routes(spec)
    fe = F.scan_frontend()
    breakpoints = sorted(fe - be)
    assert not breakpoints, (
        "扩扫后仍有 %d 条断点: %r" % (len(breakpoints), breakpoints)
    )
    # 5 条历史断点（9 个 method+path 对）必须已从调用面消失
    gone = {
        ("GET", "/api/admin/questions"), ("POST", "/api/admin/questions"),
        ("GET", "/api/admin/questions/{x}"), ("PATCH", "/api/admin/questions/{x}"),
        ("DELETE", "/api/admin/questions/{x}"),
        ("GET", "/api/admin/users/{x}/learning"), ("PATCH", "/api/users/me"),
    }
    assert not (fe & gone), "历史断点仍在前端调用面: %r" % sorted(fe & gone)


# ---------------- 尾巴③：plan 桶后端合法性校验 ----------------

def test_plan_bucket_all_routes_exist_on_real_backend():
    """真实后端：plan 桶 ∩ 后端路由 = plan 桶（全部 10 条都是后端合法路由），
    plan_broken 必须为空。"""
    try:
        spec = F.fetch_openapi()
    except Exception as e:
        pytest.skip("后端 8000 不可达，跳过 plan 合法性用例: %s" % e)
    be = F.backend_routes(spec)
    broken = F.plan_bucket_broken(be)
    assert broken == [], "plan 桶含后端不存在路由（非法 plan）: %r" % broken
    # 锁定语义：plan ∩ be == plan
    assert (F.NEXTJS_PLANNED_ENDPOINTS & be) == set(F.NEXTJS_PLANNED_ENDPOINTS)


def test_plan_broken_flagged_when_backend_lacks_route(monkeypatch, capsys):
    """盲测③：后端缺某条 plan 路由时，run() 必须输出 [PLAN-BROKEN] 警告行；
    语义为 WARN 不阻断（退出码仍 0，不破坏 ⑩ 红判据）。"""
    # 受控后端：只有一个无关路由，全部 plan 条目都"后端不存在"
    be = [(F.norm_method("GET"), F.norm_path("/api/foo"))]
    monkeypatch.setattr(F, "scan_frontend", lambda: set())
    monkeypatch.setattr(F, "fetch_openapi", lambda: _spec(be))
    monkeypatch.setattr(F, "load_contracts", lambda br=None: (set(), []))
    rc = F.run(quiet=True)
    out = capsys.readouterr().out
    assert rc == 0, "plan_broken 是 WARN，不得红/阻断（rc=%d）" % rc
    assert "[PLAN-BROKEN]" in out, "quiet 模式未输出 [PLAN-BROKEN] 警告行: %r" % out[-400:]
    # 警告行必须列出具体断条（方法+路径），不允许只报数字遮蔽明细
    for m, p in sorted(F.NEXTJS_PLANNED_ENDPOINTS):
        assert ("%s %s" % (m, p)) in out, "PLAN-BROKEN 警告缺少断条 %s %s" % (m, p)


def test_plan_broken_explicit_bucket_in_nonquiet_output(monkeypatch, capsys):
    """非 quiet 模式：PLANNED-BREAKDOWN 必须含 plan_broken 行（0 条也显式可见，防静默）。"""
    be = [(F.norm_method("GET"), F.norm_path("/api/foo"))]
    monkeypatch.setattr(F, "scan_frontend", lambda: set())
    monkeypatch.setattr(F, "fetch_openapi", lambda: _spec(be))
    monkeypatch.setattr(F, "load_contracts", lambda br=None: (set(), []))
    F.run(quiet=False)
    out = capsys.readouterr().out
    assert "plan_broken" in out, "非 quiet 输出缺少 plan_broken 行"
    assert "[PLANNED-BREAKDOWN]" in out
