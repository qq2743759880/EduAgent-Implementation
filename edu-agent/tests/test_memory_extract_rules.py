# -*- coding: utf-8 -*-
"""FEAT-WIRE-V2 缺陷#11：记忆提取规则回归（姓名自述 + 显式记住整句捕获）。

背景（用户实测+DB 实证）：「我叫小明，请记住我的名字」落库 content=「我的名字」——
_RE_EXPLICIT 只取「记住」之后的尾巴，事实值（在关键词之前）整段丢弃；且无姓名自述规则。
修复：显式记住记整句；新增 _RE_NAME 姓名规则（用户名字：X）。

纯函数测试，零 I/O。
"""
from __future__ import annotations

from app.ai.memory.ingest import detect_memories


def test_explicit_remember_captures_full_utterance():
    """「我叫小明，请记住我的名字」→ 记忆内容必须含姓名值（旧版只落「我的名字」）。"""
    cands = detect_memories("我叫小明，请记住我的名字")
    assert cands, "显式记住信号未触发"
    joined = " | ".join(c.content for c in cands)
    assert "小明" in joined, f"事实值丢失（#11 根因）：{joined}"


def test_name_introduction_rule():
    """「我叫小明」→ 产出「用户名字：小明」profile 记忆。"""
    cands = detect_memories("我叫小明，今年12岁")
    joined = " | ".join(c.content for c in cands)
    assert "用户名字：小明" in joined, f"姓名规则未命中：{joined}"
    hit = next(c for c in cands if c.content == "用户名字：小明")
    assert hit.memory_type == "profile" and hit.importance == 5


def test_name_rule_narrow_no_false_positive():
    """「我是学生」类自我描述与疑问句不得误判为姓名。"""
    cands = detect_memories("我是学生，我喜欢 Python")
    joined = " | ".join(c.content for c in cands)
    assert "用户名字" not in joined
    # 「我叫什么名字？」是问句，不是姓名自述（#11 E2E 实测误报 id=208）
    cands2 = detect_memories("我叫什么名字？")
    joined2 = " | ".join(c.content for c in cands2)
    assert "用户名字" not in joined2, f"疑问句误报为姓名：{joined2}"


def test_name_rule_variants():
    """「我的名字叫X / 叫我X」变体均命中。"""
    for text, name in [("我的名字叫王小明", "王小明"), ("叫我阿明就行", "阿明")]:
        cands = detect_memories(text)
        joined = " | ".join(c.content for c in cands)
        assert f"用户名字：{name}" in joined, f"{text} 未命中：{joined}"
