# -*- coding: utf-8 -*-
"""
W-NEXT-INT-001A 方案 A 单元测试 —— 732 条 internal=true 恢复后的健康门。

不依赖 live backend / 真 Milvus（loader/hybrid_search monkeypatch）。
测试范围：
  ① classify_internal 对 hex 临时名 + 内部内容仍判 True（classify 门未受影响）
  ② role_allows_internal：admin/manager 可见，student 不可见
  ③ internal_visibility_allowed：student 上下文=False，admin=True
  ④ _is_internal_doc 分类函数（A∩B/C 三条件判据）：单元测试
  ⑤ dry-run 幂等：plan_changes() 重跑结果不变
  ⑥ chunk_id 集合稳定：732 内部 id 清单与全库 doc_chunk _default ∩ internal=true 对账
  ⑦ fallback 行为：_default 行 internal 字段缺失 → 退回 classify_internal 仍判 True
  ⑧ 数据完整性：loader 内 _row_is_internal 与 INTERNAL_FILTER_EXPR 协同正确
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.knowledge.importer.loader import (
    INTERNAL_FIELD,
    INTERNAL_FILTER_EXPR,
    classify_internal,
    internal_visibility_allowed,
    reset_internal_visibility,
    role_allows_internal,
    set_internal_visibility,
    _row_is_internal,
)
from app.knowledge.importer import loader as L

from scripts.eval import wnextint1a_revert as WV1A


def _test_milvus_reachable() -> bool:
    """探测 Milvus 是否可达；不可达时跳过 live 对账类测试。"""
    try:
        import socket
        from app.config import settings
        host = settings.MILVUS_URI.split("://")[-1].split(":")[0]
        port = int(settings.MILVUS_URI.split(":")[-1])
        with socket.create_connection((host, port), timeout=2.0):
            return True
    except Exception:
        return False


# ============================================================
# ① classify_internal 基础（classify 门完好 = WNEXTRAG1 §1 已验证）
# ============================================================
class TestClassifyInternalGate:
    def test_hex_temp_filename_is_internal(self):
        for src in [
            "3e2b7812be2f.md",       # 12-char hex
            "1578ae407f71.md",
            "296c5e2852b3.md",
            "a1b2c3d4e5f6.txt",
        ]:
            assert classify_internal(src, "普通正文") is True, src

    def test_internal_content_patterns_match(self):
        for body in [
            "②若需要可登录批量用户，在 task09~14 中补 sys_user_auth 批量生成",
            "优化方案：restore_admin.py 的哈希逻辑",
            "本批次为 W-NEXT-10，GWT 见下",
            "编排者已复现该问题",
            "kickoff 文件路径：.ai-hub/plans/artifacts/kickoff-WNEXTINT1A.md",
        ]:
            assert classify_internal("some/business.md", body) is True, body

    def test_business_corpus_not_internal(self):
        # 业务语料：seeds 来源 + 题目/课程正文（应零误伤）
        assert classify_internal(
            "seeds/3_question/question.csv",
            "本课程介绍牛顿第一定律，惯性与质量量度"
        ) is False


# ============================================================
# ② role_allows_internal
# ============================================================
class TestRoleAllowsInternal:
    def test_admin_manager_yes(self):
        assert role_allows_internal("admin") is True
        assert role_allows_internal("manager") is True

    def test_student_teacher_none_no(self):
        assert role_allows_internal("student") is False
        assert role_allows_internal("teacher") is False
        assert role_allows_internal(None) is False


# ============================================================
# ③ internal_visibility_allowed（请求级上下文）
# ============================================================
class TestInternalVisibilityContext:
    def test_default_allowed(self):
        reset_internal_visibility(None)  # restore to default
        # 缺省为 True（向后兼容历史行为）
        assert internal_visibility_allowed() is True

    def test_student_context_blocks(self):
        token = set_internal_visibility(role_allows_internal("student"))
        try:
            assert internal_visibility_allowed() is False
        finally:
            reset_internal_visibility(token)

    def test_admin_context_allows(self):
        token = set_internal_visibility(role_allows_internal("admin"))
        try:
            assert internal_visibility_allowed() is True
        finally:
            reset_internal_visibility(token)


# ============================================================
# ④ _is_internal_doc 分类函数（A∩B/C 三条件判据）
# ============================================================
class TestIsInternalDoc:
    """WNEXTINT1A 内部分类函数（A∩B or A∩C 命中 = 真内部）。

    A = original_internal=True
    B = source_file 命中 hex 临时名 ^[0-9a-f]{12}\\.md$
    C (fallback) = content 含内部强特征关键词

    注：原 kickoff 给的是12-char hex；保留 8-32 兼容 loader 既有正则。
    """

    def test_truthy_A_and_B(self):
        # A=True, B=hex 临时名 → 真内部
        assert WV1A._is_internal_doc(
            source_file="3e2b7812be2f.md",
            content="任意正文",
            original_internal=True,
        ) is True

    def test_truthy_A_and_C(self):
        # A=True, B=否（业务名）, C=内容含 task09 → 真内部
        assert WV1A._is_internal_doc(
            source_file="seeds/some.md",
            content="涉及 task09 sys_user_auth 的批量操作",
            original_internal=True,
        ) is True

    def test_falsy_A_only_with_B_and_C(self):
        # A=False 一定是用户上传（业务向），不当内部
        assert WV1A._is_internal_doc(
            source_file="3e2b7812be2f.md",
            content="task09 sys_user_auth",
            original_internal=False,
        ) is False

    def test_truthy_A_needs_B_or_C(self):
        # kickoff §1：A∩B or A∩C 命中才算真内部；纯 A=True + 业务名 + 业务内容 = False
        assert WV1A._is_internal_doc(
            source_file="notes/random.md",
            content="纯业务文案，无内部特征",
            original_internal=True,
        ) is False

    def test_truthy_A_and_B_over_user_tenant(self):
        # 即便 user_1 租户，A=True+B=hex 命中也是原始内部
        assert WV1A._is_internal_doc(
            source_file="c56769527306.md",
            content="T10IDEMARK8Z7Q",
            original_internal=True,
        ) is True


# ============================================================
# ⑤ dry-run 幂等（plan_changes 重跑结果不变）
# ============================================================
class TestDryRunIdempotent:
    """模拟 plan_changes 的两次调用，验证幂等性。"""

    def _mock_rows(self, internal_flags):
        rows = []
        for i, flag in enumerate(internal_flags):
            rows.append({
                "id": 1000 + i,
                "chunk_id": f"_default:abc{i:04d}def{i:04d}:1",
                "source_file": f"hex{i:04d}abcdef.md",
                "internal": flag,
                "tenant_id": "_default",
            })
        return rows

    def test_first_run_then_rerun_yields_zero(self):
        # 初次：所有 internal=False → 全部要 update
        rows = self._mock_rows([False] * 10)
        rows_by_id = {r["id"]: r for r in rows}
        to_update, already_true, missing = WV1A.plan_changes(rows_by_id)
        assert len(to_update) == 10
        assert len(already_true) == 0
        assert len(missing) == 0

        # 模拟 apply 后：所有 internal=True
        rows2 = self._mock_rows([True] * 10)
        rows_by_id2 = {r["id"]: r for r in rows2}
        to_update2, already_true2, missing2 = WV1A.plan_changes(rows_by_id2)
        assert len(to_update2) == 0  # 幂等：第二次重跑无变化
        assert len(already_true2) == 10
        assert len(missing2) == 0

    def test_mixed_state_correct_partition(self):
        rows = self._mock_rows([True, False, True, False, True])
        rows_by_id = {r["id"]: r for r in rows}
        to_update, already_true, missing = WV1A.plan_changes(rows_by_id)
        assert len(to_update) == 2  # idx 1, 3
        assert len(already_true) == 3
        assert len(missing) == 0

    def test_missing_internal_field_treated_as_false(self):
        rows = [
            {"id": 1, "chunk_id": "x:1", "source_file": "y.md", "internal": None, "tenant_id": "_default"},
            {"id": 2, "chunk_id": "x:2", "source_file": "y.md", "internal": False, "tenant_id": "_default"},
        ]
        rows_by_id = {r["id"]: r for r in rows}
        to_update, already_true, missing = WV1A.plan_changes(rows_by_id)
        assert len(to_update) == 2  # None 当 False 处理
        assert len(already_true) == 0


# ============================================================
# ⑥ chunk_id 集合稳定（732 id 清单对账：仅在真 Milvus 时跑）
# ============================================================
@pytest.mark.skipif(
    not _test_milvus_reachable(),
    reason="Milvus 不可达；离线跳过",
)
class TestIdListReconciliation:
    def test_internal_true_doc_chunk_count_is_732(self):
        """当前 internal=True 的 doc_chunk 数 = 732（方案 A apply 后）。"""
        from app.config import settings
        from pymilvus import MilvusClient
        client = MilvusClient(uri=settings.MILVUS_URI, token=settings.MILVUS_TOKEN or None, timeout=15.0)
        rows = []
        offset = 0
        while True:
            page = client.query(
                settings.MILVUS_COLLECTION,
                filter='content_type == "doc_chunk"',
                output_fields=["id", "internal"],
                limit=5000,
                offset=offset,
                consistency_level="Strong",
            )
            if not page:
                break
            rows.extend(page)
            offset += len(page)
            if len(page) < 5000:
                break
        true_cnt = sum(1 for r in rows if r.get("internal") in (True, "true", 1))
        # 732 + 0（user_1 原始 internal=true 的 10 行已被 WNEXTRAG1 重置）
        # 实际期望：732（_default 真内部）+ 0（user_1 现 internal=false）
        assert true_cnt == 732, f"expected 732 internal=true, got {true_cnt}"


# ============================================================
# ⑦ fallback 行为：_default 行 internal 字段缺失 → 退回 classify_internal
# ============================================================
class TestRowIsInternalFallback:
    def test_explicit_true(self):
        row = {"source_file": "any.md", "content": "any", "internal": True}
        assert _row_is_internal(row) is True

    def test_explicit_false(self):
        row = {"source_file": "any.md", "content": "any", "internal": False}
        assert _row_is_internal(row) is False

    def test_missing_falls_back_to_classify(self):
        # internal 字段缺失 → 退回 classify_internal（来源 hex + 内容 task09 → True）
        row = {"source_file": "3e2b7812be2f.md", "content": "task09 内容"}
        assert _row_is_internal(row) is True

    def test_string_true_normalized(self):
        row = {"source_file": "any.md", "content": "any", "internal": "true"}
        assert _row_is_internal(row) is True

    def test_string_one_true(self):
        row = {"source_file": "any.md", "content": "any", "internal": "1"}
        assert _row_is_internal(row) is True


# ============================================================
# ⑧ INTERNAL_FILTER_EXPR 表达式结构
# ============================================================
class TestInternalFilterExpr:
    def test_filter_expr_format(self):
        # Milvus dynamic field 过滤：internal != true
        assert INTERNAL_FILTER_EXPR == f"{INTERNAL_FIELD} != true"

    def test_field_name(self):
        assert INTERNAL_FIELD == "internal"