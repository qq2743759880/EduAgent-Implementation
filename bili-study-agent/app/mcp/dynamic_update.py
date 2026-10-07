# -*- coding: utf-8 -*-
"""task95 R3(5)：动态工具更新监听 —— server 推送工具变更 → 更新注册表，不重启会话。

修复 self-critique 维度 2 结构性缺陷：MCP 缺动态工具更新（需重连/重启才能感知工具变化）。

对标 Claude Code mcp.md：动态工具更新（server 上线/下线工具时自动同步，无需重连/重启）。
  URL: https://docs.claude.com/en/docs/claude-code/mcp

设计约束：
  - 纯内存索引 + diff 计算，无外部依赖，可直接单测。
  - 更新只改内存索引，不重启任何会话/连接（会话级连接由 reconnect 层托管）。
  - fetch_fn(server_id) -> list[tool meta] 可注入（真实场景轮询 tools/list 或监听推送）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class ToolChangeEvent:
    """一次工具集合变更的差异事件。"""

    server_id: int
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)


class DynamicToolRegistry:
    """按 server 维护工具名集合；notify_tools_changed 计算 diff 并发事件。"""

    def __init__(self, fetch_fn: Optional[Callable[[int], Any]] = None):
        self._fetch = fetch_fn
        self._index: dict[int, dict[str, Any]] = {}  # server_id -> {name: meta}
        self.events: list[ToolChangeEvent] = []

    def current(self, server_id: int) -> list[dict]:
        return [dict(m) for m in self._index.get(server_id, {}).values()]

    def notify_tools_changed(self, server_id: int, new_tools: list[dict]) -> ToolChangeEvent:
        """用新工具列表更新索引，返回 added/removed/updated 差异。

        幂等：连续两次相同输入 → 空差异事件。
        """
        old = self._index.get(server_id, {})
        old_names = set(old.keys())
        new_map: dict[str, Any] = {}
        for t in new_tools:
            n = str(t.get("tool_name") or t.get("name") or "").strip()
            if n:
                new_map[n] = t
        new_names = set(new_map.keys())
        added = sorted(new_names - old_names)
        removed = sorted(old_names - new_names)
        updated = sorted(n for n in (new_names & old_names) if new_map[n] != old[n])
        ev = ToolChangeEvent(server_id=server_id, added=added, removed=removed, updated=updated)
        self._index[server_id] = new_map
        self.events.append(ev)
        return ev

    async def poll(self, server_id: int) -> ToolChangeEvent:
        """拉取最新工具并应用变更（fetch_fn 可同步或异步）。"""
        if self._fetch is None:
            raise RuntimeError("DynamicToolRegistry 未配置 fetch_fn")
        res = self._fetch(server_id)
        if hasattr(res, "__await__"):
            res = await res
        tools = list(res or [])
        return self.notify_tools_changed(server_id, tools)
