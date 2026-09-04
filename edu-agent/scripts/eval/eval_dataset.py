# -*- coding: utf-8 -*-
"""
task29 评估集（四类意图 + L0~L3 分级样本）。

Ground truth 标注两维：
  - intent : chitchat / knowledge / tool / learning（四类意图）
  - effort : L0(直答) / L1(单检索) / L2(工具+检索组合) / L3(复杂多步)

设计依据（.opencode/plans/ai-agent-revision-plan.md R8 + tech-source-audit §二 effort scaling）：
  - L0：闲聊/系统询问，直接答，零工具零检索
  - L1：单一学科知识检索即可回答
  - L2：需调用工具（计算/代码）或检索+综合
  - L3：复杂多步（多轮检索/推理/规划），做 R8 压测与成本测算的顶档样本

说明：样本是给「评估回放 + LLM-as-judge」用的，不伪造数据；answer_guide 仅辅助 judge 判断对错。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalSample:
    id: str
    query: str
    intent: str          # chitchat / knowledge / tool / learning
    effort: str          # L0 / L1 / L2 / L3
    answer_guide: str = ""   # judge 判断对错的关键要点（关键词）
    attack: str = ""     # 攻防标注：L0 样本含陷阱词，检验不会被误升 L3


# L0 · 闲聊 / 系统询问（含陷阱词，检验 L0 误判 L3 攻防 W1）
L0: tuple[EvalSample, ...] = (
    EvalSample("L0-1", "你好，自我介绍下你是谁？", "chitchat", "L0", "是EduAgent教育助手", "包含自称助手闲聊"),
    EvalSample("L0-2", "谢谢你的回答", "chitchat", "L0", "礼貌回应即可", "反讽/多步陷阱"),
    EvalSample("L0-3", "今天能给我讲讲怎么用这个学习平台吗？", "chitchat", "L0", "平台功能使用引导", "平台功能询问"),
    EvalSample("L0-4", "再见，我下线了", "chitchat", "L0", "告别回应", ""),
    EvalSample("L0-5", "这套课后练习一共多少分？", "chitchat", "L0", "作答而非检索/调工具", "疑似统计查询陷阱"),
    EvalSample("L0-6", "哈哈，你说的真有意思", "chitchat", "L0", "轻松互动即可，不要查知识库", "反讽陷阱"),
    EvalSample("L0-7", "你能不能帮我叫一下客服？", "chitchat", "L0", "功能引导，不调工具", "疑似工具调用陷阱"),
    EvalSample("L0-8", "下载这个PDF我看看", "chitchat", "L0", "说明需到资源页，不臆造", ""),
    EvalSample("L0-9", "这道题我不会，你来替我答吧", "chitchat", "L0", "引导自主学习，直接建议", "怀疑学习路径陷阱"),
    EvalSample("L0-10", "收到，谢谢", "chitchat", "L0", "简短确认", ""),
)

# L1 · 单一学科知识检索即可回答
L1: tuple[EvalSample, ...] = (
    EvalSample("L1-1", "Python 中列表和元组的区别是什么？", "knowledge", "L1", "列表可变/元组不可变", "两概念对比"),
    EvalSample("L1-2", "现在完成时和一般过去时的用法区别", "knowledge", "L1", "present perfect vs past simple 用法", ""),
    EvalSample("L1-3", "勾股定理的内容是什么？", "knowledge", "L1", "a²+b²=c²", ""),
    EvalSample("L1-4", "什么是冒泡排序，稳定吗？", "knowledge", "L1", "冒泡排序稳定", ""),
    EvalSample("L1-5", "英语中可数名词和不可数名词怎么区分？", "knowledge", "L1", "可数/不可数规则", ""),
    EvalSample("L1-6", "牛顿第二定律表达式", "knowledge", "L1", "F=ma", ""),
    EvalSample("L1-7", "什么是递归？", "knowledge", "L1", "递归=函数调用自身+终止条件", ""),
    EvalSample("L1-8", "现在分词和过去分词作定语的区别", "knowledge", "L1", "主动/被动 进行/完成", ""),
    EvalSample("L1-9", "时态里一般现在时标志词有哪些？", "knowledge", "L1", "always/often/every day", ""),
    EvalSample("L1-10", "内存和硬盘的区别", "knowledge", "L1", "易失性/容量/速度对比", ""),
)

# L2 · 需调用工具（计算/代码）或检索+综合
L2: tuple[EvalSample, ...] = (
    EvalSample("L2-1", "计算 17*43+89 等于多少？", "tool", "L2", "计算得820", "需要 tool 计算"),
    EvalSample("L2-2", "帮我算一下 (1+2)*3/4 的结果", "tool", "L2", "2.25", "需要 tool 计算"),
    EvalSample("L2-3", "写一段 Python 计算 1 到 100 的偶数和的代码", "tool", "L2", "2550", "需要 code runner"),
    EvalSample("L2-4", "198 除以 7 余数是几？", "tool", "L2", "余 2", "需要 tool 计算"),
    EvalSample("L2-5", "最近特斯拉股价大概在什么区间？", "tool", "L2", "实时/区间参考", "需实时查询工具"),
    EvalSample("L2-6", "这段代码报错 IndexError，帮我找出问题行", "tool", "L2", "越界定位", "需要代码执行调试"),
    EvalSample("L2-7", "把字符串 'hello world' 每个单词首字母大写", "tool", "L2", "Hello World", "需要 code"),
    EvalSample("L2-8", "判断一个年份能不能被4整除但不能被100整除是否是闰年，2026呢？", "tool", "L2", "2026 不是闰年", "需要 tool 判断"),
)

# L2/进阶 · 学习路径 / 引导性建议
LEARNING: tuple[EvalSample, ...] = (
    EvalSample("L2-L1", "我英语四级还没过，该怎么规划三个月学习？", "learning", "L2", "分阶段单词/听力/真题", ""),
    EvalSample("L2-L2", "零基础学 Python，先学什么再学什么？", "learning", "L2", "从语法到项目阶梯", ""),
    EvalSample("L2-L3", "想考研数学，如何安排复习节奏？", "learning", "L2", "基础-强化-冲刺", ""),
    EvalSample("L2-L4", "孩子刚上初一数学跟不上，怎么办？", "learning", "L2", "补基础+习惯+规划", ""),
    EvalSample("L2-L5", "雅思听力差，有没有练习方法？", "learning", "L2", "精听/同义替换/场景", ""),
    EvalSample("L2-L6", "怎么提高英语口语？", "learning", "L2", "跟读/输出/口语打卡", ""),
)

# L3 · 复杂多步（多轮检索/推理/综合，R8 压测顶档 + 成本测算）
L3: tuple[EvalSample, ...] = (
    EvalSample("L3-1", "对比 Python 和 Java 在内存管理、性能、生态三方面差异，并给出学习建议",
               "knowledge", "L3", "三方面对比+建议", ""),
    EvalSample("L3-2", "小明有 5 个苹果，妈妈又给他 3 个，他吃了 2 个，请问还剩几个？并说明运算步骤",
               "tool", "L3", "6 个，分步计算", ""),
    EvalSample("L3-3", "帮我把这段 Python 递归计算斐波那契改成迭代版本，并分析时间复杂度",
               "tool", "L3", "迭代+O(n)", "需要 code"),
    EvalSample("L3-4", "英语虚拟语气、倒装、强调句型三个语法点综合复习，帮我出3道自测题",
               "knowledge", "L3", "讲清三点+出题", ""),
    EvalSample("L3-5", "我要在一个月内同时备考四级和考证，帮我做一份每周时间分配表",
               "learning", "L3", "周计划分配", ""),
    EvalSample("L3-6", "设计一个小学四则运算练习系统，包含能自动随机出题、判分、反馈的完整方案",
               "learning", "L3", "出题判分反馈方案", ""),
)


ALL: tuple[EvalSample, ...] = L0 + L1 + L2 + LEARNING + L3

# 意图 → 本系统 effort 期望值（对齐 graph._effort_for_intent + route_gate 直答）
INTENT_TO_EFFORT: dict[str, str] = {
    "chitchat": "L0",
    "knowledge": "L1",
    "tool": "L2",
    "learning": "L2",
}


def by_effort(effort: str) -> list[EvalSample]:
    return [s for s in ALL if s.effort == effort]


def by_intent(intent: str) -> list[EvalSample]:
    return [s for s in ALL if s.intent == intent]


def stats() -> dict:
    return {
        "total": len(ALL),
        "by_intent": {i: len(by_intent(i)) for i in ("chitchat", "knowledge", "tool", "learning")},
        "by_effort": {e: len(by_effort(e)) for e in ("L0", "L1", "L2", "L3")},
    }