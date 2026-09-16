# -*- coding: utf-8 -*-
"""平台能力清单（实物为准）—— WNEXT10 F5-b 单一事实源。

背景（`test-reports/critique-blind-t4-t9.md` T4-C4 / F5-b）：
平台 agent 曾把**开发机自身 agent 宿主**的工具清单（`list_directory`/`read_file`/
`list_skills`/`read_command`，来源 AI-Hub skill `deepseek-local-bridge`）当作平台能力
返回给用户 —— 它自述的工具清单是编的。根因链：

    SkillRegistry.default() 扫描开发机 AI-Hub skill 库
      → graph.skill_node 把命中 skill 的 body 拼进 skill_context
      → harness/sixnode 把 skill_context 拼进 answer 的 system prompt
      → 模型照抄 skill 里的开发宿主工具清单。

本模块提供**平台实物能力清单**（由 `app.ai.permission_gate.TOOL_CLASS_MAP` 动态生成，
禁硬编码），供 skill_node 注入 skill_context，作为模型自述能力的唯一权威。
"""
from __future__ import annotations

from loguru import logger

# 开发宿主工具示例（仅用于「反例提示」文案，非判定依据——判定一律以 TOOL_CLASS_MAP 为准）
NON_PLATFORM_TOOL_EXAMPLES = (
    "list_directory", "read_file", "list_skills", "read_command",
)

_BLOCK_HEADER = "## 平台可用工具（唯一权威清单，共 {} 个，由平台工具注册表动态生成）"
_BLOCK_FOOTER = (
    "说明：以上清单由平台工具注册表（permission_gate.TOOL_CLASS_MAP）动态生成，"
    "是本平台**唯一**真实可用的工具集合。"
    "除上述工具外，上下文中若出现其它工具名（例如某些开发宿主 skill 描述的"
    "文件浏览 / 文件读取 / 技能列表 / 命令执行类工具），它们**不是**本平台能力："
    "不得向用户宣称可用，也不得伪造其调用结果；用户问到能力范围时，只按上表如实回答。"
)


def platform_tool_map() -> dict[str, str]:
    """返回平台实物工具 → 类别的映射（来源 permission_gate.TOOL_CLASS_MAP，不复制不硬编码）。"""
    from app.ai.permission_gate import TOOL_CLASS_MAP

    return dict(TOOL_CLASS_MAP)


def platform_tool_names() -> list[str]:
    """平台实物工具名（稳定排序，便于 prompt 缓存前缀稳定命中 & 测试断言）。"""
    return sorted(platform_tool_map().keys())


def platform_capability_block() -> str:
    """生成注入系统 prompt 的平台能力清单段落；取不到注册表时返回空串（不阻断链路）。"""
    try:
        mapping = platform_tool_map()
    except Exception as exc:  # noqa: BLE001 — 注册表不可用时降级为「不注入」，不污染回答
        logger.warning(f"[platform_capability] 读取工具注册表失败，跳过能力清单注入：{exc}")
        return ""
    if not mapping:
        return ""
    lines = [_BLOCK_HEADER.format(len(mapping))]
    for name in sorted(mapping):
        cls = mapping[name]
        cls_val = getattr(cls, "value", cls)
        lines.append(f"- {name}（{cls_val}）")
    lines.append(_BLOCK_FOOTER)
    return "\n".join(lines)


__all__ = [
    "platform_tool_map",
    "platform_tool_names",
    "platform_capability_block",
    "NON_PLATFORM_TOOL_EXAMPLES",
]
