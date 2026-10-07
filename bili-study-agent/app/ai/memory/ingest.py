"""三层记忆 - 显式触发 + 会话结束 ingest（task25 R7）。

对齐 Claude Code memory / R7 修订：
1. **显式触发（新增强信号）**：用户在对话中「记住 X / 请记住 X」✅、纠正「我不学 Java 学 Python」
   、明确目标偏好「我想考雅思/我要考雅思」→ 立即产出高价值记忆（importance≥4）。
2. **会话结束补充（保留原有）**：session 落库后扫描本期用户消息，抽离高价值事实。

`detect_memories(text)` 为**纯规则触发**（零 LLM、零 I/O），可单测确定性。
输出 `list[MemoryCandidate]`；由 `MemoryWriteQueue.enqueue_candidates` 异步入库（GWT①④）。
"""
from __future__ import annotations

import re
from typing import Any

from app.ai.memory.schemas import MemoryCandidate


# ---------------------------------------------------------------------------
# 显式触发规则（中英双语，正则确定性匹配）
# ---------------------------------------------------------------------------
# 1) 明确要求记住：记住/请记住/记住啦/remember that / remember
_RE_EXPLICIT = re.compile(
    r"(记住|请记住|牢记|remember\s+(that\s+)?)", re.IGNORECASE
)

# 2) 纠正信号：我不学…(学…) / 别学 / 其实我… / 我不想…(我想…) / 改成…
_RE_CORRECTION = re.compile(
    r"(我不学|我其实|我不想|别学|别考|改成|转而学|其实我想学)", re.IGNORECASE
)

# 3) 目标/偏好：我想考/我要考/我在准备/目标是考/我要冲/打算考
_RE_GOAL = re.compile(
    r"(我想考|我要考|我在准备|我的目标是|争取考|目标是考|打算考|打算学|想学)", re.IGNORECASE
)

# 4) 偏好直接声明：我喜欢/我更偏好/偏爱/prefer
_RE_PREFERENCE = re.compile(r"(我喜欢|我更偏好|偏爱|prefer|hobby|爱好是)", re.IGNORECASE)

# 5) [FEAT-WIRE-V2 #11] 姓名自述：「我叫X / 我的名字叫X / 我的名字是X / 叫我X」
#    高精度窄匹配（不带「是/叫」泛化，避免「我是学生」类误伤）。
_RE_NAME = re.compile(
    r"(?:我(?:的名字|姓名)(?:叫|是)|我叫|叫我)(?P<name>[^\s，。！？,.!?；;]{1,20})"
)

# 用于提取「想学/想考 什么」的捕获
_RE_GOAL_SUBJECT = re.compile(
    r"(我想考|我要考|我在准备|目标是考|打算考|打算学|想学|我准备)[：:\s]*(?P<subject>[^，。！？,.!?]{1,40})"
)

# 雅思/托福/六级等考试关键词 → importance 更高
_RE_HIGH_IMP_KW = re.compile(r"(雅思|托福|六级|四级|考研|公务员|高考|中考|教师资格|GRE|GMAT|期末|期中)", re.IGNORECASE)


def _importance_for(text: str, base: int) -> int:
    if _RE_HIGH_IMP_KW.search(text):
        return 5
    return max(3, min(5, base))


def detect_memories(text: str) -> list[MemoryCandidate]:
    """从一段用户文本规则抽离记忆候选（importance≥4 才可能返回）。

    纯函数，无副作用。若无可抽取信号返回 []。
    """
    if not (text or "").strip():
        return []
    text = text.strip()
    cands: list[MemoryCandidate] = []
    seen: set[str] = set()

    def _add(content: str, mtype: str, topic: str, source: str, importance: int) -> None:
        content = re.sub(r"\s+", " ", content).strip().lstrip("：:,，")
        if not content or len(content) < 2 or content in seen:
            return
        seen.add(content)
        cands.append(
            MemoryCandidate(
                content=content, memory_type=mtype, topic=topic,
                importance=importance, source=source,
            )
        )

    # 1) 明确「记住 X」
    if _RE_EXPLICIT.search(text):
        # [FEAT-WIRE-V2 #11] 旧写法只取「记住」之后的尾巴：「我叫小明，请记住我的名字」
        # → content=「我的名字」，事实值（在关键词之前）被整段丢弃。改为记整句原话，
        # 保证「记住 X」中 X 在句中任意位置都能落库。
        _add(text, "preference" if _RE_PREFERENCE.search(text) else "profile",
             "preferences", "explicit", _importance_for(text, 5))

    # 1b) [FEAT-WIRE-V2 #11] 姓名自述（高价值 profile，立即写）
    nm = _RE_NAME.search(text)
    if nm:
        name = nm.group("name").strip()
        # 疑问词守卫：「我叫什么名字？」的「什么名字」不是姓名（#11 E2E 实测误报）
        if name and len(name) >= 1 and not re.search(r"(什么|啥|谁|哪|吗|呢|怎么)", name):
            _add(f"用户名字：{name}", "profile", "preferences", "profile", 5)

    # 2) 目标：我想考/要考/在准备…
    gm = _RE_GOAL.search(text)
    if gm:
        subject_m = _RE_GOAL_SUBJECT.search(text)
        subject = subject_m.group("subject") if subject_m else text[gm.start():][:40]
        _add(f"目标：{subject}", "goal", "learning-goals", "goal", _importance_for(subject, 5))

    # 3) 纠正信号（高价值：立即写，非会话结束）
    if _RE_CORRECTION.search(text):
        # 提取「我不学 Java，学 Python」→ 记录最终倾向
        final = text[_RE_CORRECTION.search(text).start():][:60]
        _add(f"纠正：{final}", "correction", "corrections", "correction", 5)

    # 4) 偏好直接声明
    if _RE_PREFERENCE.search(text):
        rest = _RE_PREFERENCE.split(text, maxsplit=1)[-1]
        _add(f"偏好：{rest}", "preference", "preferences", "preference",
             _importance_for(rest, 4))
    return cands


# ---------------------------------------------------------------------------
# R01-b：对话窗（mem0 式最近 N 条，用户 query + assistant 回复成对）
# ---------------------------------------------------------------------------
def _canon_role(role: str) -> str | None:
    """角色归一：user/human → user；assistant/ai/bot → assistant；其余（system/tool）→ None。"""
    r = (role or "").strip().lower()
    if r.startswith("user") or r == "human":
        return "user"
    if r.startswith("assistant") or r in ("ai", "bot"):
        return "assistant"
    return None


def normalize_window(
    messages: list[dict] | None = None,
    *,
    text: str | None = None,
    assistant_reply: str | None = None,
    limit: int = 10,
) -> list[dict[str, str]]:
    """把输入归一为对话窗 `[{"role":"user"|"assistant","content":...}]`。

    - 显式 messages：逐条约简（角色非法/内容空/非 str 丢弃），取最近 `limit` 条；
    - 或 text（+可选 assistant_reply）：合成「用户问→助手答」最小窗口；
    - 纯函数、零 I/O；单条内容截断 2000 字（与入队载荷上限一致）。
    """
    window: list[dict[str, str]] = []
    if messages:
        for m in messages:
            if not isinstance(m, dict):
                continue
            role = _canon_role(str(m.get("role") or ""))
            content = m.get("content")
            if role is None or not isinstance(content, str) or not content.strip():
                continue
            window.append({"role": role, "content": content.strip()[:2000]})
    elif text and str(text).strip():
        window.append({"role": "user", "content": str(text).strip()[:2000]})
        if assistant_reply and str(assistant_reply).strip():
            window.append({"role": "assistant", "content": str(assistant_reply).strip()[:2000]})
    n = max(1, int(limit or 10))
    return window[-n:]


# ---------------------------------------------------------------------------
# [REWORK P0-1] 记忆槽位（同槽位事实只保留最新 HEAD，事件溯源 update 语义）
# ---------------------------------------------------------------------------
_SLOT_PATTERNS: dict[str, re.Pattern] = {
    # 名字槽位：规则路径「用户名字：X」、整句「我叫X…」、旧数据「我的名字」、
    # LLM 抽取变体「用户的名字（昵称）是…」（REWORK P0-1 实测漏网变体）
    "user_name": re.compile(r"^(用户名字|用户的名字|用户姓名|我的名字|我叫|昵称)"),
}


def detect_memory_slot(content: str) -> str | None:
    """识别记忆内容的槽位 key（同槽位新事实应关闭旧 HEAD）。无槽位语义返回 None。"""
    c = (content or "").strip()
    for slot, pat in _SLOT_PATTERNS.items():
        if pat.search(c):
            return slot
    return None


def slot_like_patterns(slot: str) -> tuple[str, ...]:
    """槽位对应 SQL LIKE 模式（close_slot_heads 用，参数绑定）。"""
    if slot == "user_name":
        return ("用户名字：%", "用户的名字%", "用户姓名%", "我的名字%", "我叫%", "昵称%")
    return ()


def detect_memories_window(messages: list[dict]) -> list[MemoryCandidate]:
    """规则路径窗口抽取：仅扫**用户**发言（高精度信号），跨条去重。

    助手侧事实性陈述由 LLM 抽取（extract_llm）覆盖——规则不扫助手文本以免噪音入库。
    """
    cands: list[MemoryCandidate] = []
    seen: set[str] = set()
    for m in messages or []:
        if not isinstance(m, dict) or _canon_role(str(m.get("role") or "")) != "user":
            continue
        for c in detect_memories(str(m.get("content") or "")):
            if c.content in seen:
                continue
            seen.add(c.content)
            cands.append(c)
    return cands


async def ingest_turn(text: str, user_id: int, enqueue: Any) -> int:
    """单轮显式触发：抽出候选并异步入队（GWT①：不阻塞应答链路）。

    Args:
        enqueue: 可调用 `await enqueue(user_id, MemoryCandidate)`（通常为 MemoryWriteQueue 方法）。

    Returns:
        入队候选数。
    """
    cands = detect_memories(text)
    pushed = 0
    for c in cands:
        c.source_user_id = int(user_id)
        try:
            r = enqueue(int(user_id), c)
            if hasattr(r, "__await__"):
                await r
            pushed += 1
        except Exception:
            # 入队失败绝不向应答链路抛错（异步隔离，GWT④）
            pass
    return pushed