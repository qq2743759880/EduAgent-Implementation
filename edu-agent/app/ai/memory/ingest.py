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
        rest = _RE_EXPLICIT.split(text, maxsplit=1)[-1]
        _add(rest, "preference" if _RE_PREFERENCE.search(rest) else "profile",
             "preferences", "explicit", _importance_for(rest, 5))

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