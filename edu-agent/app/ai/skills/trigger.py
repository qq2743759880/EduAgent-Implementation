"""Skill 触发：description 匹配 + paths 条件触发 + 手动 /skill。

对齐 Claude Code skills 文档三种触发方式：
1. 自动触发：模型依据 description 判断何时调用（本模块提供确定性启发式，可插拔 llm 决策）
2. 条件触发：用户正在 paths glob 匹配的文件上工作时自动建议（paths 字段）
3. 手动触发：用户输入 /skill-name

另外实现 Claude Code 行为细节：disable-model-invocation=true 的 skill **不参加自动 description
匹配**（仅手动 /skill 可触发），避免模型自作主张调用 lookup 类技能。
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import PurePosixPath
from typing import Callable

from app.ai.skills.runtime import Skill


# ── 分词（中英文混合，CJK 取 unigram+bigram）──────────────────────
_CJK = re.compile(r"[一-鿿]+")
_TOKEN = re.compile(r"[a-z0-9]+|[一-鿿]+")


def _tokenize(text: str) -> set[str]:
    text = (text or "").lower()
    out: set[str] = set()
    for tok in _TOKEN.findall(text):
        if _CJK.fullmatch(tok):
            for ch in tok:
                out.add(ch)
            for i in range(len(tok) - 1):
                out.add(tok[i:i + 2])
        else:
            out.add(tok)
    return out


# ── 手动 /skill 触发 ───────────────────────────────────────────
def match_by_slash(skills: list[Skill], message: str) -> list[Skill]:
    """识别消息中的 /skill-name 手动触发。"""
    found: list[Skill] = []
    for m in re.finditer(r"(?:^|\s)/([A-Za-z0-9_\-]+)", message or ""):
        name = m.group(1)
        for s in skills:
            if s.name == name or s.name.replace("-", "").lower() == name.lower():
                found.append(s)
                break
    return found


# ── paths 条件触发 ─────────────────────────────────────────────
def match_by_paths(skills: list[Skill], active_paths: list[str]) -> list[Skill]:
    """当前工作文件命中 skill.paths 任一 glob → 触发。

    active_paths 为当前打开/涉及的相对或绝对路径列表（兼容 Windows 反斜杠）。
    """
    if not active_paths:
        return []
    norm = [PurePosixPath(p.replace("\\", "/")) for p in active_paths]
    triggered: list[Skill] = []
    for s in skills:
        if not s.paths:
            continue
        for pat in s.paths:
            pg = PurePosixPath(pat.replace("\\", "/"))
            pat_str = str(pg)
            name_str = pg.name
            hit = False
            for np in norm:
                if fnmatch.fnmatch(str(np), pat_str) or fnmatch.fnmatch(np.name, name_str):
                    hit = True
                    break
            if hit:
                triggered.append(s)
                break
    return triggered


# ── description 自动匹配 ───────────────────────────────────────
def match_by_description(
    skills: list[Skill], message: str, *, threshold: float = 0.10
) -> list[Skill]:
    """message 与 description 的词重叠（Jaccard）。无 LLM，确定性。

    disable-model-invocation=true 的 skill 不参加自动匹配（仅手动触发）。
    返回按相关度降序的 skill 列表。
    """
    if not message:
        return []
    msg_tokens = _tokenize(message)
    if not msg_tokens:
        return []
    scored: list[tuple[float, Skill]] = []
    for s in skills:
        if s.disable_model_invocation or not s.description:
            continue
        desc_tokens = _tokenize(s.description)
        if not desc_tokens:
            continue
        union = msg_tokens | desc_tokens
        overlap = len(msg_tokens & desc_tokens)
        score = overlap / len(union) if union else 0.0
        if score >= threshold:
            scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored]


# ── 综合决策（可插拔真实 LLM 决策）──────────────────────────────
def decide(
    skills: list[Skill],
    message: str,
    active_paths: list[str] | None = None,
    *,
    llm: Callable[[str, list[Skill]], list[str]] | None = None,
) -> list[Skill]:
    """综合触发：paths + /skill + description，去重按触发顺序返回。

    若提供 llm(message, candidates) -> list[name]，则在启发式候选基础上叠加模型决策
    （对齐 Claude Code「模型依据 description 决策」），最终结果以模型决策为准（仍去重）。
    """
    result: list[Skill] = []
    seen: set[str] = set()

    def _push(s: Skill) -> None:
        if s.name not in seen:
            seen.add(s.name)
            result.append(s)

    for s in match_by_slash(skills, message):
        _push(s)
    for s in match_by_paths(skills, active_paths or []):
        _push(s)
    heuristic = match_by_description(skills, message)

    if llm is not None:
        try:
            chosen = llm(message, heuristic) or []
        except Exception:  # noqa: BLE001 — 模型决策失败则回落启发式
            chosen = []
        by_name = {s.name: s for s in skills}
        for name in chosen:
            if name in by_name:
                _push(by_name[name])
        # 模型未覆盖的强启发式结果仍保留（保底）
        for s in heuristic:
            _push(s)
        return result
    for s in heuristic:
        _push(s)
    return result
