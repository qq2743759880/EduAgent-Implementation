# -*- coding: utf-8 -*-
"""task-P1L 优化H：规则路由先行 —— 0-LLM 意图分类，削减主链路串行 LLM 调用。

对齐 Anthropic Building Effective Agents 的 workflow/agent 取舍：意图分类的高频信号
（问候 / 数值计算 / 学习规划 / 学科知识）可用确定性规则覆盖，命中即 0 LLM 决策；
规则未命中才回退 LLM 路由兜底（保开放场景质量）。压测语料与常见输入均被规则覆盖
→ 主链路正常路径省 1 次串行 LLM 调用（task39 实测单次 1.4~5.0s）。

确定性保证：纯正则 + 关键词，无随机/时间依赖，同一输入恒同输出（可单测、可审计）。
优先级（由高到低）：learning > tool > chitchat > knowledge（默认兜底）。
  - learning 先于 tool/chitchat：学习规划类请求常带问候/引导词（"你好，帮我制定计划"），
    学习信号最具体；数值计算信号（"乘以/等于/保留小数"）几乎不会出现在学习规划中。
  - chitchat 最低：问候语常与真实请求混排（"你好，什么是机器学习"→knowledge）。
"""
from __future__ import annotations

import re

# 四类意图（与 graph._FAST_INTENTS 一致）
INTENTS = ("chitchat", "knowledge", "tool", "learning")

# ------------------------------------------------------------
# learning 强信号：学习方法 / 路径 / 规划（优先级最高）
# ------------------------------------------------------------
_LEARNING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"学习计划|学习路径|学习节奏|学习建议|学习方法|学习方案|学习规划"),
    re.compile(r"怎么学|如何学|怎样学|怎么学好|如何学好|怎么自学"),
    re.compile(r"怎么提升|如何提升|怎么提高|如何提高"),
    re.compile(r"备考|复习计划|从零学|零基础学|该学什么|先学什么"),
    re.compile(r"制定.{0,8}计划|规划一下|安排一下|如何安排|怎么安排"),
)

# ------------------------------------------------------------
# tool 强信号：数值计算 / 换算 / 格式化（明确可调用工具）
# ------------------------------------------------------------
_TOOL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"计算|算一下|帮我算|算一算|帮我计算"),
    re.compile(r"乘以|除以|加上|减去|等于多少|求和|求积|求差"),
    re.compile(r"保留.{0,4}位小数|四舍五入|取整|精确到"),
    re.compile(r"换算|折合|汇率|转换(成|为)"),
)

# ------------------------------------------------------------
# chitchat 强信号：纯问候 / 闲聊（优先级最低，避免误吞真实请求）
# ------------------------------------------------------------
_CHITCHAT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(你好|您好|嗨|哈喽|hello|hi|hey)[!！。？~\s]*$", re.IGNORECASE),
    re.compile(r"^(早上好|中午好|下午好|晚上好|早安|晚安)[!！。？~\s]*$"),
    # 问候前缀 + AI 身份询问（"你好，你是谁"）→ chitchat；注意与"你好，什么是机器学习"（knowledge）
    # 区分：后者无身份询问词，不命中本模式（chitchat 优先级低于 learning/tool，身份询问也非学习信号）。
    re.compile(r"^(你好|您好|嗨|哈喽|hello|hi|hey)[，,、!\s]*?(你是谁|你叫什么|你是什么|你是做什么|介绍一下你|介绍一下自己|干嘛的|做什么的)[?？]?$", re.IGNORECASE),
    re.compile(r"^(你是谁|你叫什么|介绍一下你自己|你会什么)[?？]?$"),
    re.compile(r"^(谢谢|多谢|感谢|辛苦了)(你|您)?[!！。？~\s]*$"),
    re.compile(r"^(再见|拜拜|下次见|回聊)[!！。？~\s]*$"),
    re.compile(r"^(在吗|在不在)[?？]?$"),
)


def _match_any(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(p.search(text) for p in patterns)


def classify_intent(query: str) -> str | None:
    """规则意图分类。命中返回四类之一；未命中返回 None（调用方走 LLM 兜底）。

    返回 None 而非默认 knowledge：让调用方明确区分「规则已判」与「规则未覆盖」，
    未覆盖场景由 LLM 路由保质量（chitchat 等开放场景）。
    """
    text = (query or "").strip()
    if not text:
        return "chitchat"  # 空消息按闲聊兜底（几乎不会发生，防御）
    if _match_any(text, _LEARNING_PATTERNS):
        return "learning"
    if _match_any(text, _TOOL_PATTERNS):
        return "tool"
    if _match_any(text, _CHITCHAT_PATTERNS):
        return "chitchat"
    return None  # 未覆盖 → LLM 兜底


def classify_intent_or_default(query: str, default: str = "knowledge") -> str:
    """规则分类，未命中返回 default（knowledge 为最稳 RAG 兜底）。"""
    intent = classify_intent(query)
    return intent if intent is not None else default
