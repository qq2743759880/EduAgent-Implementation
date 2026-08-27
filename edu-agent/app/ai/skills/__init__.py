"""Skill 运行时（task93 R2 落地）—— 对齐 agentskills.io + Claude Code skills 标准。

公开 API：
- runtime.Skill / parse_skill_md            SKILL.md 解析（frontmatter + body）
- registry.SkillRegistry                    扫描 + 全索引（AI-Hub + 项目 skills）
- loader.build_description_listing/load_body 渐进式披露（description 常驻 / body 按需）
- trigger.decide/match_by_*                 description / paths / /skill 触发
- fork_exec.exec_skill/PermissionGate       context:fork 执行 + allowed-tools 免授权
"""
from app.ai.skills.runtime import Skill, parse_skill_md, SKILL_DESCRIPTION_MAX
from app.ai.skills.registry import SkillRegistry
from app.ai.skills import loader, trigger, fork_exec, verify

__all__ = [
    "Skill",
    "parse_skill_md",
    "SKILL_DESCRIPTION_MAX",
    "SkillRegistry",
    "loader",
    "trigger",
    "fork_exec",
    "verify",
]
