# -*- coding: utf-8 -*-
"""task95 R3(6)(7)：子代理级 mcpServers 隔离 + per-tool 结果大小限制。

修复 self-critique 维度 2 结构性缺陷：MCP 仅 admin_only 过滤，缺子代理级隔离。

对标 Claude Code sub-agents 文档：子代理通过 frontmatter `mcpServers` 字段隔离工具，
工具不进主上下文。
  URL: https://docs.claude.com/en/docs/claude-code/sub-agents

设计：
  - 主代理声明可见的 mcpServers（main_server_codes）。
  - 子代理通过 MCPScope.mcp_servers 声明其子集；子代理独占（主代理未声明）的 server
    工具不进主上下文。
  - per-tool 结果大小限制：超限截断 + 标记（避免单工具巨量返回撑爆上下文）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


# per-tool 结果大小上限（字符）；超限截断 + 告警。
PER_TOOL_RESULT_MAX_CHARS = 4000


@dataclass(frozen=True)
class MCPScope:
    """子代理的 MCP 可见域：仅列出的 server_code 可见。"""

    name: str
    mcp_servers: tuple[str, ...] = ()


def resolve_subagent_tools(all_tools: Iterable[Mapping[str, Any]],
                           scope: MCPScope) -> list[dict]:
    """解析某子代理可见工具集：仅 scope.mcp_servers 内 server 的工具。"""
    allowed = set(scope.mcp_servers)
    out: list[dict] = []
    for t in all_tools:
        sc = str(t.get("server_code") or "")
        if sc in allowed:
            out.append(dict(t))
    return out


def filter_main_context_tools(all_tools: Iterable[Mapping[str, Any]],
                             *, main_server_codes: Iterable[str]) -> list[dict]:
    """主上下文工具集 = 全量工具中 server_code 属于 main_server_codes 的工具。

    子代理独占（只在其 scope、不在 main_server_codes）的 server 工具自然被排除 →
    主上下文不含子代理专属工具（隔离验收）。
    """
    main = set(main_server_codes)
    return [dict(t) for t in all_tools if str(t.get("server_code") or "") in main]


def truncate_tool_result(result: Any, *,
                        max_chars: int = PER_TOOL_RESULT_MAX_CHARS) -> tuple[str, bool]:
    """per-tool 结果大小限制：超限截断 + 返回是否截断。

    返回 (text, truncated)。空/非字符串原样转字符串。
    """
    text = result if isinstance(result, str) else ("" if result is None else str(result))
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars] + f"\n…[截断，原 {len(text)} 字，上限 {max_chars}]", True
