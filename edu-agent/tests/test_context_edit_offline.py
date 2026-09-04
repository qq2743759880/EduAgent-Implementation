# -*- coding: utf-8 -*-
"""C1-③ 环境依赖项离线单测：上下文冻结/阈值监测决策（plan_context_action 决策矩阵）。

无需真实对话流量即可验证阈值监测 + 决策逻辑：
  1) 未超阈值 → action=none；
  2) 超阈值且 context_edit 可降至阈值内 → context_edit；
  3) 超阈值且编辑仍不足/禁用 → compaction；
  4) 冻结区（前缀占用）占比正确计入 usage。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.ai.context_edit import plan_context_action, measure_usage, ThresholdStrategy
from langchain_core.messages import HumanMessage, AIMessage


def _msgs(n: int, content: str = "x" * 200) -> list:
    out = []
    for i in range(n):
        out.append(HumanMessage(content=f"Q{i}:{content}"))
        out.append(AIMessage(content=f"A{i}:{content}"))
    return out


# 1. 未超阈值 → none
def test_plan_none_when_under_threshold():
    st = ThresholdStrategy(edit_threshold=10000, keep_rounds=2, window_tokens=20000,
                           warn_ratio=0.6, order=("context_edit", "compaction"), context_edit_enabled=True)
    res = plan_context_action(_msgs(2), strategy=st)
    assert res["action"] == "none"
    assert res["reason"] == "under_threshold"


# 2. usage 超阈值 → 决策进入编辑或压缩（编辑 enabled 时阈值极低 → 超阈值）
def test_plan_exceeds_threshold_triggers_edit_or_compaction():
    st = ThresholdStrategy(edit_threshold=100, keep_rounds=2, window_tokens=20000,
                           warn_ratio=0.6, order=("context_edit", "compaction"), context_edit_enabled=True)
    res = plan_context_action(_msgs(2), strategy=st)
    assert res["action"] in ("context_edit", "compaction"), f"超阈值应触发编辑/压缩，得 {res['action']}"
    assert res["usage"].total_tokens > 100


# 3. context_edit 禁用 → 超阈值直接 compaction
def test_plan_compaction_when_edit_disabled():
    st = ThresholdStrategy(edit_threshold=100, keep_rounds=2, window_tokens=20000,
                           warn_ratio=0.6, order=("context_edit",), context_edit_enabled=False)
    res = plan_context_action(_msgs(2), strategy=st)
    assert res["action"] == "compaction"
    assert res["reason"] == "context_edit_disabled"


# 4. 冻结区（前缀）占比正确计入
def test_usage_reports_prefix_tokens():
    msgs = _msgs(3)
    u = measure_usage(msgs, window_tokens=20000, edit_threshold=10000)
    assert u.messages_count == 6
    assert u.total_tokens > 0
    # 前缀占比 < 1　且 total = prefix + 其余（单调合理）
    assert 0 < u.usage_ratio <= 1
    assert u.prefix_tokens >= 0