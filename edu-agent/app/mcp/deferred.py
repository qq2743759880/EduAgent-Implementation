# -*- coding: utf-8 -*-
"""task95 R3(1)：MCP 工具延迟加载（deferred tool search）。

修复 self-critique 维度 2/9 结构性缺陷：MCP 工具描述全量进 system prompt →
随 server 数增长，前缀变化导致缓存失效（且 task33 描述重写会加剧失效）。

对标 Claude Code prompt-caching 官方文档（deferred tools 默认开启）：
  "Tools loaded into the prefix: any change to them invalidates the cache.
   Deferred tools, the default on supported models: a server connecting,
   disconnecting, or changing its tool list only appends new content and
   doesn't disturb anything already cached."
  URL: https://docs.claude.com/en/docs/claude-code/prompt-caching

设计要点：
  - 主上下文（缓存前缀 project 层）只放「工具摘要列表」= name + 一句话摘要（极小、确定）。
  - 完整描述 + input_schema 在决策 LLM 选定工具后「按需拉取」（不进前缀）。
  - 摘要列表 key 只依赖 name + 首句摘要 → 重写完整描述（task33）不改变 key → 缓存前缀不受影响。
  - 每工具完整定义按 (server_id, name) 独立缓存 → 新增/移除工具不驱逐其他工具的完整定义缓存。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

# 摘要（进前缀）的单条最大字符；首句超长截断。保持小以稳定前缀。
SUMMARY_MAX_CHARS = 80


@dataclass(frozen=True)
class ToolSummary:
    """常驻前缀的工具摘要（稳定、确定）。"""

    name: str
    summary: str
    server_id: int = 0
    server_code: str = ""
    category: str = ""


def _first_sentence(desc: str) -> str:
    """取描述首句（用于稳定摘要）。

    以中文/英文句末标点或显式换行分割；无标点则取前 N 字。
    首句是「做什么」的概括，改写完整描述时它通常保持不变 → 摘要稳定。
    """
    d = (desc or "").strip()
    if not d:
        return ""
    # 优先句末标点
    m = re.split(r"(?<=[。！？!?])", d, maxsplit=1)
    if len(m) > 1 and m[0].strip():
        return m[0].strip()
    # 换行分隔
    if "\n" in d:
        return d.split("\n", 1)[0].strip()
    return d


def summarize(tool: Mapping[str, Any]) -> ToolSummary:
    """从一个 tool meta（dict，含 name/description/server_id/server_code/category）派生稳定摘要。"""
    name = str(tool.get("tool_name") or tool.get("name") or "").strip()
    desc = str(tool.get("description") or "")
    sentence = _first_sentence(desc)
    if len(sentence) > SUMMARY_MAX_CHARS:
        sentence = sentence[: SUMMARY_MAX_CHARS - 1] + "…"
    return ToolSummary(
        name=name,
        summary=sentence,
        server_id=int(tool.get("server_id") or 0),
        server_code=str(tool.get("server_code") or ""),
        category=str(tool.get("category") or ""),
    )


def build_summary_listing(tools: Iterable[Mapping[str, Any]]) -> str:
    """构建常驻前缀的「工具摘要列表」。按 name 稳定排序 → 同输入逐字节一致。

    形如：
        # MCP 工具（摘要）
        - name: 一句话摘要
        - name2: 一句话摘要
    """
    summaries = sorted(
        (summarize(t) for t in tools if str(t.get("tool_name") or t.get("name") or "").strip()),
        key=lambda s: s.name,
    )
    lines = ["# MCP 工具（摘要）"]
    for s in summaries:
        line = f"- {s.name}: {s.summary}" if s.summary else f"- {s.name}:"
        lines.append(line)
    return "\n".join(lines)


def listing_key(listing: str) -> str:
    """摘要列表的稳定缓存 key（sha256）。前缀是否失效由它决定。"""
    return hashlib.sha256((listing or "").encode("utf-8")).hexdigest()


def full_spec_key(server_id: int, name: str) -> str:
    """每工具完整定义的独立缓存 key（与摘要列表无关 → 列变化不驱逐其他工具缓存）。"""
    return hashlib.sha256(f"{int(server_id)}:{name}".encode("utf-8")).hexdigest()


def load_full_spec(tool: Mapping[str, Any]) -> dict:
    """按需拉取完整工具定义（描述 + input_schema），不进前缀。"""
    name = str(tool.get("tool_name") or tool.get("name") or "").strip()
    desc = str(tool.get("description") or "")
    schema = tool.get("input_schema") or tool.get("input_schema_json") or {}
    if isinstance(schema, str):
        try:
            schema = json.loads(schema)
        except Exception:
            schema = {}
    return {
        "tool_name": name,
        "description": desc,
        "input_schema": schema if isinstance(schema, dict) else {},
    }


def contains_full_description(listing: str) -> bool:
    """断言辅助：缓存前缀（摘要列表）绝不包含完整描述长文本（用于自检）。"""
    for line in (listing or "").splitlines():
        if len(line) > SUMMARY_MAX_CHARS * 3:
            return True
    return False


class DeferredToolIndex:
    """维护延迟加载索引：摘要列表（进前缀）+ 每工具完整定义（按需）。

    核心不变量（deferred 语义）：
      - 前缀 key = listing_key(build_summary_listing(tools))
      - 完整定义 key = full_spec_key(server_id, name)（独立，不受列表变化影响）
    """

    def __init__(self) -> None:
        self._tools: dict[str, Mapping[str, Any]] = {}  # name -> meta

    def set_tools(self, tools: Iterable[Mapping[str, Any]]) -> None:
        for t in tools:
            n = str(t.get("tool_name") or t.get("name") or "").strip()
            if n:
                self._tools[n] = t

    def prefix_listing(self) -> str:
        return build_summary_listing(self._tools.values())

    def prefix_key(self) -> str:
        return listing_key(self.prefix_listing())

    def load_full(self, name: str) -> dict:
        t = self._tools.get(name)
        return load_full_spec(t) if t is not None else {}
