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
