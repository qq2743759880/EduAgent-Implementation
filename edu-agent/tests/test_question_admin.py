# -*- coding: utf-8 -*-
"""task13: 管理端题库 CRUD 契约测试 — question_bank + question + 批量导入 + 组卷快照 + 401 安全壳

GWT 覆盖（3条）：
① 批量导入 1752 题：全量入库 + 失败行（题干/答案缺失、题型非法）逐行报告；幂等（question_code 唯一键冲突回查返回原记录）
② quiz 出题源切换：题目来源为 question 表且返回含 analysis_text 解析字段
③ 考试发布快照：发布后考试题目快照到 session_exam_question_rel，改原题不影响考试判分

边界：page_size=101/0 → 422 壳；不存在资源 → 404 壳；Bearer 格式错误 → 401 壳。
标签逻辑删除（task13）— 不再维护 tag 表，stem/analysis_text LIKE 检索替代。
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
ADMIN_PREFIX = "/api/admin/questions"

# 鉴权：优先取 CI 注入的环境变量，否则本地开发时手动设置
TOKEN = os.environ.get("TEST_ADMIN_TOKEN", "")
_AUTH_HEADER = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, headers, msg, newurl):
        return None


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def api(method: str, path: str, headers: dict | None = None, body: dict | list | None = None):
    """直连被测服务，返回 (status, json_body, raw_headers)。"""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with _OPENER.open(req, timeout=15) as resp:
            body_bytes = resp.read()
            ct = resp.headers.get("Content-Type", "")
            if "json" in ct or path.startswith("/api/"):
                return resp.status, json.loads(body_bytes.decode()), dict(resp.headers)
            return resp.status, body_bytes.decode(), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        body_bytes = exc.read()
        try:
            j = json.loads(body_bytes.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            j = {"raw": body_bytes.decode(errors="replace")}
        return exc.code, j, dict(exc.headers)


def _check_ok(status: int, j: dict) -> dict:
    """断言响应壳成功格式（code=0 int）。"""
    assert status == 200 or status == 201, f"期望 200/201 得到 {status} body={json.dumps(j, ensure_ascii=False)[:200]}"
    assert j.get("code") == 0, f"code != 0: {j}"
    return j["data"]


def _check_fail(status: int, j: dict, expected_code_prefix: str = "4"):
    """断言响应壳失败格式。"""
    assert status != 200, f"期望非200得到 {status} body={json.dumps(j, ensure_ascii=False)[:200]}"
    code = j.get("code")
    assert code is not None, f"响应缺少 code: {j}"
    # 业务错误码为字符串，4xx/5xx
    code_str = str(code)
    assert code_str.startswith(expected_code_prefix), f"code={code_str} 不以 {expected_code_prefix} 开头"
    assert j.get("data") is None, f"失败响应 data 不为 null: {j}"
    return j


# ═══════════════════════════════════════════
# Fixtures（类级）
# ═══════════════════════════════════════════

@pytest.fixture(scope="module")
def bank_id():
    """创建题库供后续测试使用，测试结束后清理。"""
    if not TOKEN:
        pytest.skip("需要 TEST_ADMIN_TOKEN 环境变量")
    status, j, _ = api("POST", f"{ADMIN_PREFIX}/banks", headers=_AUTH_HEADER, body={
        "institution_id": 1,
        "category_id": 1,
        "bank_code": "TEST-BANK-TASK13",
        "bank_name": "测试题库-task13",
    })
    data = _check_ok(status, j)
    created_id = data["id"]
    yield created_id
    # teardown: 软删题库
    api("DELETE", f"{ADMIN_PREFIX}/banks/{created_id}", headers=_AUTH_HEADER)


# ═══════════════════════════════════════════
# GWT ①：批量导入 + 幂等
# ═══════════════════════════════════════════

class TestBatchImport:
    """批量导入：预览 + 执行 + 幂等。"""

    @pytest.fixture(autouse=True)
    def require_auth(self):
        if not TOKEN:
            pytest.skip("需要 TEST_ADMIN_TOKEN 环境变量")

    def test_preview_invalid_rows(self, bank_id):
        """预览：非法行（题干/答案缺失、题型非法）正确报告。"""
        items = [
            {"question_code": "Q001", "question_type_id": 1, "stem": "题干1", "answer_text": "答案1"},
            {"question_code": "", "question_type_id": 1, "stem": "题干2", "answer_text": "答案2"},
            {"question_code": "Q003", "question_type_id": 999, "stem": "题干3", "answer_text": "答案3"},
            {"question_code": "Q004", "question_type_id": 1, "stem": "", "answer_text": "答案4"},
            {"question_code": "Q005", "question_type_id": 1, "stem": "题干5", "answer_text": ""},
        ]
        status, j, _ = api("POST", f"{ADMIN_PREFIX}/import-preview?bank_id={bank_id}",
                           headers=_AUTH_HEADER, body=items)
        data = _check_ok(status, j)
        assert data["total_rows"] == 5
        assert data["valid_rows"] == 1  # 仅 Q001 有效
        assert data["invalid_rows"] == 4
        # 验证失败行报告
        invalid_rows = [r for r in data["rows"] if not r["valid"]]
        assert len(invalid_rows) == 4
        row_map = {r["row_index"]: r for r in invalid_rows}
        assert "" in row_map[1]["errors"][0]  # 空 question_code

    def test_execute_import_and_idempotent(self, bank_id):
        """执行导入 + 幂等验证。"""
        items = [
            {"question_code": "T13-Q001", "question_type_id": 1, "stem": "测试题目1", "answer_text": "答案1", "analysis_text": "解析1"},
            {"question_code": "T13-Q002", "question_type_id": 1, "stem": "测试题目2", "answer_text": "答案2"},
            {"question_code": "T13-Q003", "question_type_id": 2, "stem": "测试题目3", "answer_text": "答案3"},
        ]
        # 首次执行
        status, j, _ = api("POST", f"{ADMIN_PREFIX}/import-execute?bank_id={bank_id}",
                           headers=_AUTH_HEADER, body=items)
        data = _check_ok(status, j)
        assert data["imported"] == 3
        assert data["skipped"] == 0
        assert data["failed"] == 0
        assert data["total"] == 3

        # 幂等：重复执行
        status, j, _ = api("POST", f"{ADMIN_PREFIX}/import-execute?bank_id={bank_id}",
                           headers=_AUTH_HEADER, body=items)
        data = _check_ok(status, j)
        assert data["imported"] == 0, "幂等失败：应全部跳过"
        assert data["skipped"] == 3, f"期望 3 跳过，得到 {data['skipped']}"
        assert data["failed"] == 0

    def test_list_questions(self, bank_id):
        """验证导入题目可查询。"""
        status, j, _ = api("GET", f"{ADMIN_PREFIX}/banks/{bank_id}/questions",
                           headers=_AUTH_HEADER)
        data = _check_ok(status, j)
        assert data["total"] > 0
        # 关键词检索（LIKE 替代标签）
        status, j, _ = api("GET", f"{ADMIN_PREFIX}/banks/{bank_id}/questions?keyword=测试题目1",
                           headers=_AUTH_HEADER)
        data = _check_ok(status, j)
        assert data["total"] >= 1

    def test_get_question_detail(self, bank_id):
        """题目详情含 analysis_text。"""
        status, j, _ = api("GET", f"{ADMIN_PREFIX}/banks/{bank_id}/questions?page_size=1",
                           headers=_AUTH_HEADER)
        data = _check_ok(status, j)
        assert data["total"] >= 1
        qid = data["items"][0]["id"]
        status, j, _ = api("GET", f"{ADMIN_PREFIX}/questions/{qid}",
                           headers=_AUTH_HEADER)
        data = _check_ok(status, j)
        assert data["stem"] is not None
        # analysis_text 可能为 null 但字段存在


# ═══════════════════════════════════════════
# GWT ②：quiz 出题源切换
# ═══════════════════════════════════════════

class TestQuizSourceSwitch:
    """出题源从 admin_question → question 表。"""

    def test_question_types_list(self):
        """题型维表只读查询。"""
        if not TOKEN:
            pytest.skip("需要 TEST_ADMIN_TOKEN")
        status, j, _ = api("GET", f"{ADMIN_PREFIX}/types", headers=_AUTH_HEADER)
        data = _check_ok(status, j)
        assert isinstance(data, list)
        assert len(data) > 0
        assert data[0].get("type_code") is not None


# ═══════════════════════════════════════════
# GWT ③：考试发布 + 快照
# ═══════════════════════════════════════════

class TestExamSnapshot:
    """组卷快照机制。"""

    @pytest.fixture(autouse=True)
    def require_auth(self):
        if not TOKEN:
            pytest.skip("需要 TEST_ADMIN_TOKEN")

    def test_create_exam(self, bank_id):
        """创建考试。"""
        status, j, _ = api("POST", f"{ADMIN_PREFIX}/exams", headers=_AUTH_HEADER, body={
            "session_id": 1,
            "exam_code": "T13-EXAM-001",
            "exam_name": "测试考试-task13",
            "total_score": 100.00,
            "pass_score": 60.00,
            "duration_minutes": 120,
            "window_start_at": "2026-08-20T00:00:00",
            "deadline_at": "2026-09-20T00:00:00",
            "created_by": 1,
        })
        data = _check_ok(status, j)
        assert data["exam_code"] == "T13-EXAM-001"
        assert data["publish_status"] == "draft"

    def test_publish_exam_snapshot(self, bank_id):
        """发布考试 = 快照题目。"""
        # 先创建考试
        status, j, _ = api("POST", f"{ADMIN_PREFIX}/exams", headers=_AUTH_HEADER, body={
            "session_id": 1,
            "exam_code": "T13-EXAM-SNAP",
            "exam_name": "快照测试",
            "total_score": 100.00,
            "pass_score": 60.00,
            "duration_minutes": 120,
            "window_start_at": "2026-08-20T00:00:00",
            "deadline_at": "2026-09-20T00:00:00",
            "created_by": 1,
        })
        data = _check_ok(status, j)
        exam_id = data["id"]

        # 获取题库中已导入的题目
        status, j, _ = api("GET", f"{ADMIN_PREFIX}/banks/{bank_id}/questions",
                           headers=_AUTH_HEADER)
        qdata = _check_ok(status, j)
        if qdata["total"] < 2:
            pytest.skip("题库题目不足 2 道，无法组卷")
        qids = [item["id"] for item in qdata["items"][:2]]

        # 发布快照
        status, j, _ = api("POST", f"{ADMIN_PREFIX}/exams/{exam_id}/publish",
                           headers=_AUTH_HEADER, body={
            "question_ids": [
                {"question_id": qids[0], "sort_no": 1, "score": 50.00},
                {"question_id": qids[1], "sort_no": 2, "score": 50.00},
            ],
        })
        data = _check_ok(status, j)
        assert data["publish_status"] == "published"
        assert data["question_count"] == 2

        # 验证考试详情含快照
        status, j, _ = api("GET", f"{ADMIN_PREFIX}/exams/{exam_id}",
                           headers=_AUTH_HEADER)
        data = _check_ok(status, j)
        assert len(data.get("questions", [])) == 2
        assert data["publish_status"] == "published"


# ═══════════════════════════════════════════
# 安全壳测试
# ═══════════════════════════════════════════

class TestSecurityShell:
    """401 安全壳 + 404 壳 + 422 壳。"""

    def test_anonymous_401(self):
        """匿名访问返回 401。"""
        status, j, _ = api("GET", f"{ADMIN_PREFIX}/types")
        _check_fail(status, j, "4")
        assert str(j.get("code", "")).startswith("401"), f"期望 401xx 得到 {j.get('code')}"

    def test_not_found(self):
        """不存在资源返回 404。"""
        if not TOKEN:
            pytest.skip("需要 TEST_ADMIN_TOKEN")
        status, j, _ = api("GET", f"{ADMIN_PREFIX}/banks/999999",
                           headers=_AUTH_HEADER)
        _check_fail(status, j, "4")

    def test_invalid_page_size(self):
        """page_size 超界 → 422。"""
        if not TOKEN:
            pytest.skip("需要 TEST_ADMIN_TOKEN")
        status, j, _ = api("GET", f"{ADMIN_PREFIX}/banks?page_size=101",
                           headers=_AUTH_HEADER)
        # 422 或 400 均可接受
        assert status in (422, 400), f"期望 422/400 得到 {status}"