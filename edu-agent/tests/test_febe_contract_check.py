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
