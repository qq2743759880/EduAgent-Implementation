"""SKILL.md 解析器（task93 R2 落地）。

对齐 **agentskills.io 开放标准** + **Claude Code skills 官方文档**（code.claude.com/docs/en/skills，
self-critique §〇 已全文抓取）：

- frontmatter 字段：name / description / paths / context / disable-model-invocation / allowed-tools
  （另兼容 argument-hint / agent / user-invokable / metadata / args）
- description 在 skill listing 中被**截断到 1,536 字符**（渐进式披露，保护 prompt cache）
- body（SKILL.md 正文）**仅在 skill 被触发时按需加载**，不进入系统前缀

本模块无重依赖（仅 yaml + 标准库），可被 registry/loader/trigger/fork_exec 安全导入。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Claude Code skills 文档原文：
# "description truncated at 1,536 characters in the skill listing to reduce context usage"
SKILL_DESCRIPTION_MAX = 1536
PATHS_FRONTMATTER = "paths"
CONTEXT_FORK = "fork"


@dataclass(frozen=True)
class Skill:
    """一个被索引的 skill（agentskills.io 标准 SKILL.md）。"""

    name: str
    description: str
    paths: tuple[str, ...] = ()                       # 条件触发 glob 列表（paths 字段）
    context: str | None = None                        # e.g. "fork" → 在子代理上下文执行
    disable_model_invocation: bool = False           # true → 仅手动 /skill 触发，不自动匹配
    allowed_tools: tuple[str, ...] = ()               # 该轮预授权工具（allowed-tools 字段）
    agent: str | None = None                          # 委托的子代理（agent: supervisor 等）
    argument_hint: str | None = None                  # 调用参数提示
    body: str = ""                                    # SKILL.md 正文（lazy，不进前缀）
    source_dir: str = ""                              # skill 目录
    source_file: str = ""                             # SKILL.md 绝对路径
    raw_frontmatter: dict = field(default_factory=dict)
    parse_error: str | None = None                   # 解析告警（不丢索引，继续计入）

    @property
    def is_fork(self) -> bool:
        return self.context == CONTEXT_FORK


def _split_frontmatter(text: str) -> tuple[dict, str, str | None]:
    """切分 YAML frontmatter 与 body。返回 (frontmatter, body, error)。

    frontmatter 缺失/损坏均不抛异常——降级为 ({} , 全文, error)，由上层继续计入索引。
    """
    if not text.startswith("---"):
        return {}, text.strip(), None
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        return {}, text, "missing-closing-delimiter"
    fm_raw, body = m.group(1), m.group(2)
    try:
        fm = yaml.safe_load(fm_raw) or {}
        if not isinstance(fm, dict):
            return {}, body.strip(), "frontmatter-not-mapping"
        return fm, body.strip(), None
    except Exception as exc:  # noqa: BLE001 — 解析失败仍要保留索引
        return {}, body.strip(), f"yaml: {exc}"


def _as_str_list(value: Any) -> tuple[str, ...]:
    """归一化 frontmatter 的标量/列表字段为字符串元组。"""
    if value is None:
        return ()
    if isinstance(value, str):
        # allowed-tools 可能是 "Read Write Edit" 空格分隔
        return tuple(value.split())
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value if v is not None)
    return (str(value),)


def parse_skill_md(path: str | Path) -> Skill:
    """解析单个 SKILL.md → Skill。永不抛异常语义上致命错误（解析问题写入 parse_error）。"""
    p = Path(path)
    src_dir = str(p.parent)
    default_name = p.parent.name if p.name == "SKILL.md" else p.stem

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return Skill(
            name=default_name, description="", source_dir=src_dir,
            source_file=str(p), parse_error=f"read: {exc}",
        )

    fm, body, err = _split_frontmatter(text)
    fm_name = fm.get("name")
    skill_name = str(fm_name).strip() if fm_name else default_name
    desc = str(fm.get("description") or "").strip()

    paths = _as_str_list(fm.get(PATHS_FRONTMATTER))
    context = fm.get("context")
    dmi = bool(fm.get("disable-model-invocation", False))
    allowed = _as_str_list(fm.get("allowed-tools"))
    agent = fm.get("agent")
    arg_hint = fm.get("argument-hint") or fm.get("argument-hint")

    return Skill(
        name=skill_name,
        description=desc,
        paths=paths,
        context=str(context) if context else None,
        disable_model_invocation=dmi,
        allowed_tools=allowed,
        agent=str(agent) if agent else None,
        argument_hint=arg_hint,
        body=body,
        source_dir=src_dir,
        source_file=str(p),
        raw_frontmatter=fm,
        parse_error=err,
    )
