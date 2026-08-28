"""渐进式披露（progressive disclosure）：description 列表常驻前缀，body 按需加载。

对齐 Claude Code skills 文档（self-critique §〇 抓取原文）：

- "a skill's body loads only when it's used" —— body 不进系统前缀
- "description truncated at 1,536 characters in the skill listing to reduce context usage"
  —— 常驻清单中每条 description 截断到 1536 字符，保护 prompt cache 命中率（R5 联动）

本模块提供：
- build_description_listing()   构建常驻前缀的 skill 清单（不含 body）
- load_body()                  触发时按需返回 body（仅注入当前轮）
- 1536 截断 + 轻量 token 估算（与 subagents.runner._token_approx 同口径）
"""
from __future__ import annotations

from app.ai.skills.runtime import SKILL_DESCRIPTION_MAX, Skill


def _token_approx(text: str) -> int:
    """与 task92 runner 同口径的 token 估算（中文/全角≈1 token/字，ASCII≈1/4）。"""
    cjk = ascii_cnt = 0
    for ch in text:
        o = ord(ch)
        if 0x2E80 <= o <= 0x9FFF or 0x3000 <= o <= 0x303F:
            cjk += 1
        elif ch != "\n":
            ascii_cnt += 1
    return cjk + ascii_cnt // 4 + 1


def truncate_description(text: str, limit: int = SKILL_DESCRIPTION_MAX) -> str:
    """将 description 截断到 limit 字符（末尾加省略号，避免被吞半字）。"""
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def build_description_listing(
    skills: list[Skill], limit: int = SKILL_DESCRIPTION_MAX
) -> str:
    """常驻系统前缀的 skill 清单：每条 `name: 截断description`。

    关键不变量：返回字符串**不含任何 skill 的 body**——body 永不在前缀中，
    触发时由 load_body() 单独注入当前轮（动态 context injection）。
    """
    lines = []
    for s in skills:
        d = truncate_description(s.description, limit)
        lines.append(f"- {s.name}: {d}")
    return "\n".join(lines)


def load_body(skill: Skill) -> str:
    """按需加载 body（仅触发时调用，注入当前轮，不进前缀）。"""
    return skill.body


def listing_tokens(skills: list[Skill], limit: int = SKILL_DESCRIPTION_MAX) -> int:
    """估算常驻清单的 token 体量（用于缓存前缀稳定性观测）。"""
    return _token_approx(build_description_listing(skills, limit))


def contains_body(listing: str, skill: Skill) -> bool:
    """断言辅助：清单中是否意外混入了某 skill 的 body（应恒为 False）。"""
    body = (skill.body or "").strip()
    if not body:
        return False
    # 取 body 中一个稳定片段做存在性判定（避免整段比对噪声）
    probe = body[:80]
    return probe in listing
