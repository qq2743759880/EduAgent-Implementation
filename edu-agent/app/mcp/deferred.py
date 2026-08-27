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
    """从一个 tool meta（dict，含 name/description/server_id/server_code/category）派生稳定摘要。

    summary_sentence 优先：若 meta 显式携带稳定摘要句（如描述重写前的首句），则用它作为前缀摘要，
    保证「完整描述被 FAST 重写」不会改变缓存前缀 key（task97 GWT①：改写存延迟加载层 + 摘要列表稳定）。
    """
    name = str(tool.get("tool_name") or tool.get("name") or "").strip()
    desc = str(tool.get("description") or "")
    sentence = str(tool.get("summary_sentence") or "").strip() or _first_sentence(desc)
    if len(sentence) > SUMMARY_MAX_CHARS:
        sentence = sentence[: SUMMARY_MAX_CHARS - 1] + "…"
    return ToolSummary(
        name=name,
        summary=sentence,
        server_id=int(tool.get("server_id") or 0),
        server_code=str(tool.get("server_code") or ""),
        category=str(tool.get("category") or ""),
    )


def build_summary_listing(tools: Iterable[Mapping[str, Any]], *, include_admin_only: bool = False) -> str:
    """构建常驻前缀的「工具摘要列表」。按 name 稳定排序 → 同输入逐字节一致。

    形如：
        # MCP 工具（摘要）
        - name: 一句话摘要
        - name2: 一句话摘要

    include_admin_only=False（默认）：admin_only 工具不进前缀 —— 普通用户决策前缀不含管理类工具，
    避免 admin_only 工具的增删改触发普通用户前缀失效（R3 deferred 关键不变量）。
    """
    kept = []
    for t in tools:
        name = str(t.get("tool_name") or t.get("name") or "").strip()
        if not name:
            continue
        if not include_admin_only and bool(t.get("admin_only")):
            continue
        kept.append(t)
    summaries = sorted((summarize(t) for t in kept), key=lambda s: s.name)
    lines = ["# MCP 工具（摘要）"]
    for s in summaries:
        line = f"- {s.name}: {s.summary}" if s.summary else f"- {s.name}:"
        lines.append(line)
    return "\n".join(lines)


def stable_listing_key(tools: Iterable[Mapping[str, Any]], *, include_admin_only: bool = False) -> str:
    """摘要列表的稳定缓存 key（sha256）。前缀是否失效由它决定。

    admin_only 默认过滤，确保普通用户前缀不受 admin 工具变更影响（task97 GWT① / R3 协同）。
    """
    return listing_key(build_summary_listing(tools, include_admin_only=include_admin_only))


def detect_schema_version_change(prev: Mapping[str, Any] | None, cur: Mapping[str, Any]) -> dict | None:
    """检测单工具 input_schema 版本变化（task97 GWT① schema 版本告警）。

    规则：cur 含显式 schema_version（int/str）且与 prev 不同 → 返回告警 dict；
    否则对比 input_schema 结构指纹（字段名集合 + required），变化即版本漂移告警。
    返回 None 表示无变化（无需告警）。
    """
    cur_schema = cur.get("input_schema") or cur.get("input_schema_json") or {}
    if not isinstance(cur_schema, dict):
        cur_schema = {}
    cur_fields = tuple(sorted(cur_schema.get("properties", {}).keys())) if isinstance(cur_schema.get("properties"), dict) else ()
    cur_required = tuple(sorted(cur_schema.get("required", []))) if isinstance(cur_schema.get("required"), list) else ()

    # 全新工具（无上一版）→ 无变更可对比，不告警
    if prev is None:
        return None

    # 显式版本号优先
    cur_ver = cur.get("schema_version")
    if prev is not None:
        prev_ver = prev.get("schema_version")
        if cur_ver is not None and prev_ver is not None and str(cur_ver) != str(prev_ver):
            return {
                "changed": True,
                "reason": "schema_version",
                "prev_version": prev_ver,
                "cur_version": cur_ver,
            }
    # 结构指纹对比
    prev_schema = prev.get("input_schema") or prev.get("input_schema_json") or {} if prev is not None else {}
    if not isinstance(prev_schema, dict):
        prev_schema = {}
    prev_fields = tuple(sorted(prev_schema.get("properties", {}).keys())) if isinstance(prev_schema.get("properties"), dict) else ()
    prev_required = tuple(sorted(prev_schema.get("required", []))) if isinstance(prev_schema.get("required"), list) else ()
    if (cur_fields, cur_required) != (prev_fields, prev_required):
        return {
            "changed": True,
            "reason": "schema_structure",
            "prev_fields": list(prev_fields),
            "cur_fields": list(cur_fields),
        }
    return None


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
      - GWT①：admin_only 工具默认不进前缀；含显式 schema_version 或结构漂移时记录告警。
    """

    def __init__(self, include_admin_only: bool = False) -> None:
        self.include_admin_only = include_admin_only
        self._tools: dict[str, Mapping[str, Any]] = {}      # name -> meta
        self._prev_by_name: dict[str, Mapping[str, Any]] = {}  # 上一版快照（schema 版本对比）
        self.schema_alerts: list[dict] = []                  # schema 版本告警事件

    def set_tools(self, tools: Iterable[Mapping[str, Any]]) -> None:
        """装载工具集，并检测 schema 版本 / 结构漂移（相对上一次 set_tools）。"""
        new: dict[str, Mapping[str, Any]] = {}
        for t in tools:
            n = str(t.get("tool_name") or t.get("name") or "").strip()
            if not n:
                continue
            alert = detect_schema_version_change(self._prev_by_name.get(n), t)
            if alert is not None:
                alert = {"tool_name": n, **alert}
                self.schema_alerts.append(alert)
            new[n] = t
        self._prev_by_name = {k: dict(v) for k, v in new.items()}
        self._tools = new

    def prefix_listing(self) -> str:
        return build_summary_listing(self._tools.values(), include_admin_only=self.include_admin_only)

    def prefix_key(self) -> str:
        return listing_key(self.prefix_listing())

    def load_full(self, name: str) -> dict:
        t = self._tools.get(name)
        return load_full_spec(t) if t is not None else {}
