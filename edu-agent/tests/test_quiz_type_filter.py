# -*- coding: utf-8 -*-
"""FEAT-WIRE-V2 缺陷#7：专项练习选题型过滤修复的回归测试。

背景（2026-09-21 实测）：GET /api/interactive/quiz/next?question_type=X 六种题型全部
返回同一道 SINGLE 题——根因：
  ① 错题本优先分支不按 question_type 过滤（用户有一道到期 SINGLE 错题即抢占一切题型）；
  ② mock 过滤 `or bank` 兜底静默吞掉题型过滤。
修复后语义：
  A) 显式题型时错题优先也只在该题型内；
  B) mock 严格按题型过滤，无该题型时回退真实题库，仍无则 404001 诚实空态。

全部用 monkeypatch 打桩 DB 边界（fetch_one / 掌握度加载），零数据库依赖。
mock 题库分布备注：math 有 SINGLE/MULTI?/JUDGE/DRAG_SORT——math×MULTI 为真实空缺组合。
"""
from __future__ import annotations

import pytest

from app.common.exceptions import AppException as BizError
from app.interactive.quiz import service as qs
from app.interactive.quiz.schemas import DRAG_SORT, FILL, JUDGE, MATCH, MULTI, SINGLE


async def _no_due_wrong_book(sql=None, args=None, *a, **kw):
    return None


@pytest.fixture(autouse=True)
def _no_mastery(monkeypatch):
    """掌握度加载打桩为空（next_question 内部延迟 import，patch 源模块）。"""
    from app.recommender import engine

    async def _empty(*a, **kw):
        return {}

    monkeypatch.setattr(engine, "_load_mastery_by_kp_code", _empty)


@pytest.mark.parametrize("qtype", [SINGLE, MULTI, JUDGE, FILL, DRAG_SORT, MATCH])
async def test_type_filter_strict(monkeypatch, qtype):
    """① 六种题型各自返回对应题型（旧版 `or bank` 兜底会返回任意题型）。"""
    monkeypatch.setattr(qs, "fetch_one", _no_due_wrong_book)
    q = await qs.next_question(user_id=1, question_type=qtype)
    assert q.question_type == qtype, f"选题 {qtype} 却返回 {q.question_type}"


async def test_wrong_book_priority_respects_type(monkeypatch):
    """② 错题优先分支按题型过滤：有一道到期 SINGLE 错题时，选 MULTI 不再被抢占。

    桩按 SQL 参数行为区分：只有当服务真的把 question_type 写进错题本查询
    （且值不是 SINGLE）时，才返回 None——未修的旧代码不会带 MULTI 参数，桩会
    返回 SINGLE 错题并使本断言失败。"""
    wb_row = {"question_id": None, "custom_question_code": "Q-MATH-SINGLE-SUM100", "subject_code": "math"}

    async def fake_fetch_one(sql, args=None, *a, **kw):
        if "quiz_wrong_book" in sql:
            typed = tuple(args or ())[1:]  # (user_id[, subject][, question_type])
            if typed and SINGLE not in typed and MULTI in typed:
                return None  # 题型过滤后：无 MULTI 到期错题
            return wb_row
        return None

    monkeypatch.setattr(qs, "fetch_one", fake_fetch_one)
    q = await qs.next_question(user_id=1, question_type=MULTI)
    assert q.question_type == MULTI, "错题本 SINGLE 抢占了 MULTI 选题（根因①未修）"

    # 不选题型（错题本「重做」入口）：SINGLE 错题优先语义保持不变
    q2 = await qs.next_question(user_id=1)
    assert q2.question_type == SINGLE, "未选题型时错题优先语义被破坏"

    # 选题型与错题同型：错题优先仍生效
    q3 = await qs.next_question(user_id=1, question_type=SINGLE)
    assert q3.custom_code == "Q-MATH-SINGLE-SUM100"


async def test_empty_bank_honest_404001(monkeypatch):
    """④ （学科×题型）无 mock 且真实题库也无 → 诚实 404001，不再静默换题型。"""
    monkeypatch.setattr(qs, "fetch_one", _no_due_wrong_book)
    with pytest.raises(BizError) as ei:
        await qs.next_question(user_id=1, subject_code="math", question_type=MATCH)
    assert ei.value.code == 404001


async def test_real_bank_fallback(monkeypatch):
    """⑤ mock 无该组合（math×MULTI）时回退真实题库（question 表随机抽）。"""
    async def fake_fetch_one(sql, args=None, *a, **kw):
        if "quiz_wrong_book" in sql:
            return None
        if "FROM `question` q" in sql:
            return {"id": 1}
        return None

    async def fake_load(*, code=None, qid=None):
        assert qid == 1
        from app.interactive.quiz.schemas import Question
        return Question(custom_code="Q-REAL-1", subject_code="general",
                        question_type=MULTI, title="真实题库回退题")

    monkeypatch.setattr(qs, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(qs, "_load_by_code_or_id", fake_load)
    q = await qs.next_question(user_id=1, subject_code="math", question_type=MULTI)
    assert q.custom_code == "Q-REAL-1" and q.question_type == MULTI
