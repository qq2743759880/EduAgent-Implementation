# -*- coding: utf-8 -*-
"""F-W1-GUARD（AUTO20 T7，C-W1-② 硬化）：答案层写类回执机检护栏单测。

对应任务铁律 4 的必配四态：
  GR-G1 写类提及 + 凭据空 → 标记 True + 答案尾部追加诚实修正句（原内容保留）；
  GR-G2 凭据存在（任一 success）→ 零标记零追加；
  GR-G3 只读工具提及（search_knowledge 等，无写类语义）→ 零标记；
  GR-G4 闲聊 → 零标记。
补充：GR-G5 幂等（已含修正句不重复追加）、GR-G6 配置化词表（禁散落硬编码）。

全部进程内纯函数测试（不触 DB / 不触 LLM / 不触 HTTP），任意时段可跑。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.chat.receipt_guard import (
    TOOL_RECEIPT_FLAG,
    TOOL_RECEIPT_NOTICE,
    _write_phrases,
    _write_tools,
    apply_tool_receipt_guard,
)
from app.chat.schemas import MCPToolCallSummary
from app.config import settings


def _summary(tool_name: str, status: str) -> MCPToolCallSummary:
    return MCPToolCallSummary(
        call_id=f"t-{tool_name}-{status}",
        tool_name=tool_name,
        args_summary="{}",
        status=status,  # type: ignore[arg-type]
        latency_ms=1,
        result_summary="ok" if status == "success" else "",
    )


# ============================================================
# GR-G1：写类完成语义提及 + 凭据空 → 标记 True + 追加修正句
# ============================================================
@pytest.mark.parametrize("text", [
    "课程系列 3 已收藏。",                       # 「已收藏」完成态
    "你的导入任务已提交，稍后生效。",             # 「已提交」
    "知识库已导入 12 篇资料。",                   # 「已导入」
    "学习计划已创建，开始吧。",                   # 「已创建」（连续完成态）
    "用 favorite_add 收藏该课程即可。",           # 写类工具名提及
])
def test_write_mention_no_receipt_flags_and_appends(text):
    final, flagged = apply_tool_receipt_guard(text, mcp_tool_calls=[])
    assert flagged is True, f"应标记 {TOOL_RECEIPT_FLAG}=True：{text}"
    assert final.startswith(text), "禁删改原答案：原文必须完整保留在头部"
    assert final.rstrip().endswith(TOOL_RECEIPT_NOTICE), "答案尾部必须追加诚实修正句"
    assert text in final and final != text, "修正句为追加而非改写"


def test_denied_or_held_receipt_is_not_evidence():
    """凭据只有 error（权限门拦截/HITL 挂起）→ 不算真实凭据 → 照样标记（捏造高发场景）。"""
    for st in ("error", "timeout"):
        final, flagged = apply_tool_receipt_guard(
            "课程系列 3 已收藏。", mcp_tool_calls=[_summary("favorite_add", st)],
        )
        assert flagged is True, f"status={st} 不构成凭据，应标记"
        assert final.endswith(TOOL_RECEIPT_NOTICE)


# ============================================================
# GR-G2：凭据存在（任一 success）→ 零标记零追加
# ============================================================
def test_success_receipt_no_flag_no_append():
    text = "课程系列 3 已收藏。"
    receipts = [_summary("favorite_add", "success")]
    final, flagged = apply_tool_receipt_guard(text, mcp_tool_calls=receipts)
    assert flagged is False, "有真实 success 凭据 → 不标记"
    assert final == text, "有真实凭据 → 答案零变化（不追加修正句）"


def test_mixed_receipt_with_one_success_is_clean():
    """一次失败 + 一次成功（真实执行存在）→ 不标记（以真实凭据为准）。"""
    text = "课程系列 3 已收藏。"
    receipts = [_summary("favorite_add", "error"), _summary("favorite_add", "success")]
    final, flagged = apply_tool_receipt_guard(text, mcp_tool_calls=receipts)
    assert flagged is False and final == text


# ============================================================
# GR-G3：只读工具提及（无写类语义）→ 零标记
# ============================================================
@pytest.mark.parametrize("text", [
    "已通过 search_knowledge 检索到 3 篇资料。",   # 只读工具名
    "知识库里已入库的学习资料共 12 篇。",           # 「已入库」不在写类关键词表（只读语境）
])
def test_readonly_mention_no_flag(text):
    final, flagged = apply_tool_receipt_guard(text, mcp_tool_calls=[])
    assert flagged is False, f"只读提及不应标记：{text}"
    assert final == text, "零追加"


# ============================================================
# GR-G4：闲聊 → 零标记
# ============================================================
@pytest.mark.parametrize("text", [
    "今天聊聊英语学习方法，多听多说多读。",
    "背单词可以按艾宾浩斯遗忘曲线安排复习。",
    "",
])
def test_chitchat_no_flag(text):
    final, flagged = apply_tool_receipt_guard(text, mcp_tool_calls=[])
    assert flagged is False
    assert final == text


# ============================================================
# GR-G5：幂等（已含修正句不重复追加）
# ============================================================
def test_idempotent_notice_not_duplicated():
    text = "课程系列 3 已收藏。\n\n" + TOOL_RECEIPT_NOTICE
    final, flagged = apply_tool_receipt_guard(text, mcp_tool_calls=[])
    assert flagged is True, "仍应保持标记态"
    assert final.count("⚠️") == 1, "修正句必须幂等，禁止重复追加"


# ============================================================
# GR-G6：词表配置化（禁散落硬编码）
# ============================================================
def test_keyword_lists_are_config_backed():
    """默认词表必须来自 Settings（配置化单点），且包含任务钉死的六短语+四工具名。"""
    for p in ("已收藏", "已提交", "已导入", "已创建", "已删除", "已支付"):
        assert p in _write_phrases(), f"写类短语 {p} 必须在配置化列表中"
    for t in ("favorite_add", "knowledge_import", "course_create", "order_create"):
        assert t in _write_tools(), f"写类工具名 {t} 必须在配置化列表中"
    assert settings.TOOL_RECEIPT_WRITE_PHRASES, "Settings 必须提供默认词表"


def test_config_override_changes_detection(monkeypatch):
    """配置可覆盖：清空短语+工具名 → 同一文本不再标记（配置化单点生效）。"""
    monkeypatch.setattr(settings, "TOOL_RECEIPT_WRITE_PHRASES", [])
    monkeypatch.setattr(settings, "TOOL_RECEIPT_WRITE_TOOLS", [])
    final, flagged = apply_tool_receipt_guard("课程系列 3 已收藏。", mcp_tool_calls=[])
    assert flagged is False and final == "课程系列 3 已收藏。"


def test_flag_constant_name():
    """标记字段名钉死（前端 chat.html 渲染黄色警示条依据）。"""
    assert TOOL_RECEIPT_FLAG == "tool_receipt_unverified"
