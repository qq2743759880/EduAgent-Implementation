# -*- coding: utf-8 -*-
"""遗留项 1 契约测试：series 三 JSON 列（target_*_codes）写侧 round-trip（真实 HTTP 直连 127.0.0.1:8000）。

背景：POST /api/admin/courses/series 带 JSON 列表字段（target_learner_identity_codes 等）
曾返回 500 {code:"50000"}——根因 repository 写侧未序列化 list，asyncmy execute 抛
"Argument 'val' has incorrect type (expected tuple, got list)"。已补 `_json_or_null` 序列化。

覆盖：
① POST 创建含 ["C1","C2"] → 200 {code:0}，data 三列 round-trip 回 list
② PATCH 更新三列为新 list → 同样 round-trip
③ 三列置 null（传 None）也能 round-trip 为 null（不 500）

鉴权：登录 /api/auth/login（admin adm02test / Test@123456）取真实 access_token。
代理防护：ProxyHandler({}) + NO_PROXY（Windows 系统代理会卡死 127.0.0.1）。
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

_JSON_COLS = ("target_learner_identity_codes", "target_learning_goal_codes", "target_grade_codes")


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


@pytest.fixture(scope="module")
def admin():
    """登录 admin，返回带 Authorization 头 + user_id。"""
    code, _, body = api("POST", "/api/auth/login",
                        body={"account": _ADMIN, "password": _ADMIN_PWD})
    assert code == 200 and body.get("code") == 0, f"管理员登录失败: {code} {body}"
    data = body["data"]
    return {"headers": {"Authorization": f"Bearer {data['access_token']}"},
            "user_id": data["user"]["user_id"]}


def _make_series_code(prefix: str = "jsn") -> str:
    return f"{prefix}{int(time.time() * 1000)}"


def test_create_with_json_list_columns_roundtrip(admin):
    """① POST 创建含 list 字段系列 → 200，三列 round-trip 回 list（不再 500）。"""
    h = admin["headers"]
    code_str = _make_series_code()
    payload = {
        "institution_id": 1,
        "delivery_mode": "online_live",
        "series_code": code_str,
        "series_name": f"JSON列测试{code_str}",
        "target_learner_identity_codes": ["C1", "C2"],
        "target_learning_goal_codes": ["G1"],
        "target_grade_codes": ["GR1", "GR2", "GR3"],
        "created_by": admin["user_id"],
    }
    sc, _, sb = api("POST", f"{ADMIN_BASE}/series", headers=h, body=payload)
    assert sc == 200, f"创建含 list 字段系列应 200，实际 {sc} {sb}"
    assert sb["code"] == 0, f"创建含 list 字段系列应 code=0，实际 {sb}"
    sid = sb["data"]["id"]
    try:
        for col in _JSON_COLS:
            assert sb["data"][col] == payload[col], \
                f"{col} 创建 round-trip 应为 list {payload[col]}，实际 {sb['data'][col]!r}"
    finally:
        api("DELETE", f"{ADMIN_BASE}/series/{sid}", headers=h)


def test_patch_update_json_list_columns_roundtrip(admin):
    """② 先建空系列，PATCH 更新三列为 list → 200，round-trip 回 list。"""
    h = admin["headers"]
    code_str = _make_series_code("jsnu")
    sc, _, sb = api("POST", f"{ADMIN_BASE}/series", headers=h, body={
        "institution_id": 1, "delivery_mode": "online_live", "series_code": code_str,
        "series_name": f"JSON更新{code_str}", "created_by": admin["user_id"],
    })
    assert sc == 200 and sb["code"] == 0, f"创建失败: {sb}"
    sid = sb["data"]["id"]
    try:
        patch_body = {
            "target_learner_identity_codes": ["C1", "C2"],
            "target_learning_goal_codes": ["G1", "G2"],
            "target_grade_codes": ["GR1"],
        }
        pc, _, pb = api("PATCH", f"{ADMIN_BASE}/series/{sid}", headers=h, body=patch_body)
        assert pc == 200, f"PATCH 更新 list 字段应 200，实际 {pc} {pb}"
        assert pb["code"] == 0, f"PATCH 更新 list 字段应 code=0，实际 {pb}"
        for col in _JSON_COLS:
            assert pb["data"][col] == patch_body[col], \
                f"{col} 更新 round-trip 应为 list {patch_body[col]}，实际 {pb['data'][col]!r}"
    finally:
        api("DELETE", f"{ADMIN_BASE}/series/{sid}", headers=h)


def test_create_with_null_json_columns(admin):
    """③ 三列显式传 null → 200，round-trip 为 None（不 500，NULL 语义保持）。"""
    h = admin["headers"]
    code_str = _make_series_code("jsnn")
    sc, _, sb = api("POST", f"{ADMIN_BASE}/series", headers=h, body={
        "institution_id": 1, "delivery_mode": "online_live", "series_code": code_str,
        "series_name": f"JSON null 测试{code_str}",
        "target_learner_identity_codes": None,
        "target_learning_goal_codes": None,
        "target_grade_codes": None,
        "created_by": admin["user_id"],
    })
    assert sc == 200, f"创建 null 字段应 200，实际 {sc} {sb}"
    assert sb["code"] == 0, f"创建 null 字段应 code=0，实际 {sb}"
    sid = sb["data"]["id"]
    try:
        for col in _JSON_COLS:
            assert sb["data"][col] is None, \
                f"{col} 传 null 应 round-trip 为 None，实际 {sb['data'][col]!r}"
    finally:
        api("DELETE", f"{ADMIN_BASE}/series/{sid}", headers=h)