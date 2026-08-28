"""Skill registry：扫描 AI-Hub skills + 项目 .claude/skills，构建内存索引。

对齐 Claude Code：skills 在 agent 启动时**一次性扫描并索引**（name/description/paths 可查），
body 不进前缀（见 loader.py 渐进式披露）。索引键 = skill 目录（保证每个 SKILL.md 唯一计入，
即使 name 重名也不丢索引，满足 self-critique 维度4「全部索引」验收）。

默认 roots：
- 环境变量 AI_HUB_SKILLS_DIR 或 D:\\.ai-hub\\skills（AI-Hub 中心库）
- 项目 .claude/skills（可能不存在，缺失则跳过）
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from loguru import logger

from app.ai.skills.runtime import Skill, parse_skill_md

DEFAULT_AI_HUB = os.environ.get(
    "AI_HUB_SKILLS_DIR", r"D:\.ai-hub\skills"
)
PROJECT_SKILLS = r"E:\stu\project\stu\EduAgent实施手册\.claude\skills"


class SkillRegistry:
    """内存 skill 注册表：按目录索引全部 skill，按 name 提供首义查找。"""

    def __init__(self) -> None:
        self._by_dir: dict[str, Skill] = {}
        self._by_name: dict[str, Skill] = {}
        self._roots: list[str] = []

    # ── 构建 ──────────────────────────────────────────────
    @classmethod
    def from_roots(cls, roots: Iterable[str | Path]) -> "SkillRegistry":
        reg = cls()
        reg.scan(roots)
        return reg

    @classmethod
    def default(cls) -> "SkillRegistry":
        """扫描默认 roots（AI-Hub + 项目 .claude/skills）。"""
        return cls.from_roots([DEFAULT_AI_HUB, PROJECT_SKILLS])

    def scan(self, roots: Iterable[str | Path]) -> int:
        """扫描多个 root 下所有 SKILL.md，逐个索引。返回本次新增索引数。

        设计要点：每个 SKILL.md 必产生一个索引条目（解析失败也降级计入），
        因此 registry.count() == 独立枚举到的 SKILL.md 文件数 → 「全部索引」可验证。
        """
        added = 0
        for root in roots:
            root = Path(root)
            if not root.exists():
                logger.debug(f"[SkillRegistry] root 不存在，跳过: {root}")
                continue
            self._roots.append(str(root))
            for skill_md in sorted(root.rglob("SKILL.md")):
                try:
                    skill = parse_skill_md(skill_md)
                except Exception as exc:  # noqa: BLE001 — 极端情况下也不丢索引
                    skill = Skill(
                        name=skill_md.parent.name, description="",
                        source_dir=str(skill_md.parent), source_file=str(skill_md),
                        parse_error=f"parse: {exc}",
                    )
                key = str(skill.source_dir)
                if key in self._by_dir:
                    continue  # 同目录重复 SKILL.md 仅记一次
                self._by_dir[key] = skill
                if skill.name not in self._by_name:
                    self._by_name[skill.name] = skill
                added += 1
        logger.info(
            f"[SkillRegistry] 扫描完成，索引 {len(self._by_dir)} 个 skills"
            f"（来自 {len(self._roots)} 个 root，本次新增 {added}）"
        )
        return added

    # ── 访问 ──────────────────────────────────────────────
    def all(self) -> list[Skill]:
        return list(self._by_dir.values())

    def get(self, name: str) -> Skill | None:
        return self._by_name.get(name)

    def get_by_dir(self, directory: str) -> Skill | None:
        return self._by_dir.get(directory)

    def count(self) -> int:
        return len(self._by_dir)

    def roots(self) -> list[str]:
        return list(self._roots)

    def names(self) -> list[str]:
        return [s.name for s in self._by_dir.values()]

    def stats(self) -> dict:
        """索引统计（供验收/报告读取）。"""
        fork = sum(1 for s in self._by_dir.values() if s.is_fork)
        dmi = sum(1 for s in self._by_dir.values() if s.disable_model_invocation)
        with_paths = sum(1 for s in self._by_dir.values() if s.paths)
        with_allowed = sum(1 for s in self._by_dir.values() if s.allowed_tools)
        parse_errs = sum(1 for s in self._by_dir.values() if s.parse_error)
        return {
            "total": self.count(),
            "context_fork": fork,
            "disable_model_invocation": dmi,
            "with_paths_trigger": with_paths,
            "with_allowed_tools": with_allowed,
            "parse_errors": parse_errs,
        }
