# -*- coding: utf-8 -*-
"""task97 / R5（缓存监控）契约测试：命中率可验证 + 与 task96 上下文水位联合看板。

全部进程内 fake，零真实 LLM / 零真实 Redis（缓存降级路径已覆盖），可直接运行：
    cd edu-agent && .venv/Scripts/python.exe -m pytest tests/test_contract_task97.py -q

GWT：
① description_reviewer 改写存延迟加载层 + 摘要列表稳定 + per-server 熔断（task95 已实现，此处验证协同）
   + admin_only 过滤 + schema 版本告警 + 只读缓存 60s
② 多轮对话观察 /metrics：命中率持续上报 >50%（generator 真实上报入口）
③ MCP 变更 → 命中率不受影响（R3 deferred 生效）；模型切换 → 命中率下降且记录失效原因
④ 衔接 task96 ContextUsageMonitor → 形成「上下文水位 + 缓存命中」联合看板

批判承接：
- task95 批判③：deferred 接入 tool_specs 端到端（摘要列表稳定 / 完整定义按需 / schema 版本告警）
- task96 批判②：context_edit 真正接入 graph 决策链路（compact→context_edit→plan，结果被 plan 消费）
- task96 批判③：generator 真实多轮观测（_report_cache_usage 解析 usage 并上报 CacheMonitor）
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from app.ai import cache_monitor as cm
from app.ai.cache_monitor import CacheMonitor, HIT_RATE_ALERT_THRESHOLD, set_cache_monitor
from app.ai import graph as G
from app.mcp import deferred, description_reviewer
from app.mcp.description_reviewer import REVIEW_CACHE_TTL


# ============================================================
# 工具：隔离监控器，避免污染进程单例
# ============================================================
@pytest.fixture
def isolated_monitor(monkeypatch):
    """注入一个 clock 可控的空 CacheMonitor，并自动还原单例。"""
    m = CacheMonitor(clock=lambda: 1000.0)
    set_cache_monitor(m)
    yield m
    set_cache_monitor(CacheMonitor())


def _sample_tools():
    """tool_specs 形态的工具列表（含 server_id / server_code / input_schema）。"""
    t1 = {
        "tool_name": "search_docs",
        "description": "检索知识库文档。返回相关片段与出处。",
        "server_id": 1,
        "server_code": "kb",
        "category": "rag",
        "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
    }
    t2 = {
        "tool_name": "send_email",
        "description": "发送邮件通知。参数 to/subject/body。",
        "server_id": 2,
        "server_code": "mail",
        "category": "comm",
        "input_schema": {"type": "object", "properties": {"to": {"type": "string"}}, "required": ["to"]},
    }
    return [t1, t2]


# ============================================================
# GWT①：description_reviewer 改写存延迟层 + 摘要列表稳定 + admin_only 过滤 + schema 告警 + 60s 缓存
# ============================================================
class TestGwt1DeferredStability:
    def test_summary_listing_stable_after_full_rewrite(self):
        """完整描述被 FAST 重写（首句不变）→ 摘要列表 key 不变（保护前缀，deferred 核心）。"""
        tools = _sample_tools()
        k0 = deferred.stable_listing_key(tools)
        rewritten = [
            dict(t, description=(
                t["description"]
                + "（v2 重写）支持语义召回与重排，自动追加引用链接，处理更长上下文摘要与多语言片段。"
            )) if t["tool_name"] == "search_docs" else t
            for t in tools
        ]
        k1 = deferred.stable_listing_key(rewritten)
        assert k1 == k0, "完整描述重写不应改变摘要列表 key（否则前缀缓存失效）"

    def test_apply_rewrite_to_deferred_keeps_prefix_key(self):
        """apply_rewrite_to_deferred 把重写描述存进延迟层，但 summary_sentence 锚定原首句 → 该工具前缀 key 不变。"""
        idx = deferred.DeferredToolIndex()
        idx.set_tools([_sample_tools()[0]])  # 单工具索引：聚焦该工具的前缀稳定性
        k0 = idx.prefix_key()
        rewritten_text = (
            "检索知识库文档。返回相关片段与出处。"
            "（v2）支持语义召回、重排、多语言与引用链接，自动处理长上下文摘要。"
        )
        meta = dict(_sample_tools()[0])
        description_reviewer.apply_rewrite_to_deferred(idx, meta, rewritten_text)
        k1 = idx.prefix_key()
        assert k1 == k0, "apply_rewrite_to_deferred 必须保持前缀 key 不变（R3 deferred 生效）"
        full = idx.load_full("search_docs")
        assert full["description"] == rewritten_text

    def test_admin_only_filtered_from_prefix_by_default(self):
        """admin_only 工具默认不进前缀；include=True 才进。普通用户前缀不受 admin 工具增删影响。"""
        tools = _sample_tools() + [
            {"tool_name": "purge_all", "description": "管理员专用：清库。", "server_id": 9,
             "server_code": "admin", "admin_only": True},
        ]
        listing_default = deferred.build_summary_listing(tools, include_admin_only=False)
        listing_incl = deferred.build_summary_listing(tools, include_admin_only=True)
        assert "purge_all" not in listing_default
        assert "purge_all" in listing_incl
        # 普通用户前缀 key 不含 admin 工具：admin 工具变更不影响前缀
        k_without = deferred.stable_listing_key(tools, include_admin_only=False)
        tools2 = [t for t in tools if not t.get("admin_only")] + [
            {"tool_name": "purge_all", "description": "管理员专用：清库并重建索引。", "server_id": 9,
             "server_code": "admin", "admin_only": True},  # admin 描述重写
        ]
        k_without2 = deferred.stable_listing_key(tools2, include_admin_only=False)
        assert k_without == k_without2, "admin_only 工具变更不应影响普通用户前缀 key"

    def test_schema_version_change_alert(self):
        """DeferredToolIndex 检测单工具 input_schema 漂移 → schema_alerts 精确记录 1 条；新工具不误报。"""
        idx = deferred.DeferredToolIndex()
        idx.set_tools(_sample_tools())
        assert idx.schema_alerts == []
        # 改 search_docs 的 input_schema（新增可选字段）→ 结构漂移告警 1 条
        changed = _sample_tools()
        changed[0]["input_schema"]["properties"]["top_k"] = {"type": "integer"}
        idx.set_tools(changed)
        assert len(idx.schema_alerts) == 1
        assert idx.schema_alerts[0]["tool_name"] == "search_docs"
        assert idx.schema_alerts[0]["reason"] == "schema_structure"
        # 再新增一个全新工具（prev=None）→ 不应额外产生告警
        added = changed + [{"tool_name": "new_tool", "description": "新工具。",
                            "server_id": 3, "server_code": "extra",
                            "input_schema": {"type": "object", "properties": {"x": {"type": "string"}}}}]
        before = len(idx.schema_alerts)
        idx.set_tools(added)
        assert len(idx.schema_alerts) == before, "新工具（无上一版）不应触发 schema 告警"

    def test_detect_schema_version_change_unit(self):
        """detect_schema_version_change 单测：prev=None→None；字段变化→schema_structure；版本号变化→schema_version。"""
        cur = {"input_schema": {"properties": {"q": {"type": "string"}}}}
        assert deferred.detect_schema_version_change(None, cur) is None
        prev = {"input_schema": {"properties": {"q": {"type": "string"}}}}
        assert deferred.detect_schema_version_change(prev, cur) is None  # 相同
        changed = {"input_schema": {"properties": {"q": {"type": "string"}, "k": {"type": "integer"}}}}
        alert = deferred.detect_schema_version_change(prev, changed)
        assert alert is not None and alert["reason"] == "schema_structure"
        ver_cur = {"schema_version": 2, "input_schema": {"properties": {"q": {"type": "string"}}}}
        ver_prev = {"schema_version": 1, "input_schema": {"properties": {"q": {"type": "string"}}}}
        alert2 = deferred.detect_schema_version_change(ver_prev, ver_cur)
        assert alert2 is not None and alert2["reason"] == "schema_version"

    def test_review_readonly_cache_ttl_60s_and_fingerprint(self, monkeypatch):
        """run_description_review 走 60s 只读缓存：指纹变化才重算。验证 TTL 常量与 get_or_load 接线。"""
        assert REVIEW_CACHE_TTL == 60, "task97 GWT①：体检结果只读缓存 TTL 须为 60s"
        import unittest.mock as mock

        captured = {}

        async def fake_get_or_load(key, fn, ttl):
            captured["key"] = key
            captured["ttl"] = ttl
            captured["fn"] = fn
            return {"cache_hit": True, "scanned": 0, "items": []}

        # 用字符串形式确保命中 run_description_review 内部 `from app.core.cache import get_or_load` 的模块
        monkeypatch.setattr("app.core.cache.get_or_load", fake_get_or_load)
        # 兜底：即便缓存降级走 _do_review，也避免触达 MySQL（mock registry 读取）
        monkeypatch.setattr("app.mcp.registry.list_tools_for_review", mock.AsyncMock(return_value=[]))

        out = asyncio.run(description_reviewer.run_description_review(server_id=7))
        assert captured.get("ttl") == 60
        assert captured.get("key", "").startswith("mcp:desc-review:7:")
        assert out.get("cache_hit") is True


# ============================================================
# GWT②：多轮对话命中率持续上报 >50%（含 generator 真实上报入口 task96 批判③）
# ============================================================
class TestGwt2HitRateReporting:
    def test_overall_hit_rate_exceeds_50_percent(self, isolated_monitor: CacheMonitor):
        """多轮调用：cache_read 占绝对多数 → 整体命中率 > 50%，并记录到 Prometheus gauge。"""
        # 模拟 5 轮多轮对话：每轮 cache_read=800, cache_creation=0, prompt_total=1000 → 命中 80%
        for _ in range(5):
            isolated_monitor.record_llm_call_sync(
                cache_read=800, cache_creation=0, prompt_total=1000, model="deepseek-fast", tier="fast"
            )
        rate = isolated_monitor.overall_hit_rate()
        assert rate > 0.5, f"命中率应 >50%，实测 {rate}"
        # 导出到 /metrics 的 gauge 同步更新
        from app.monitoring.metrics import cache_hit_rate
        assert cache_hit_rate._value.get() == pytest.approx(rate, rel=1e-6)

    def test_per_conversation_hit_rate_tracked(self, isolated_monitor: CacheMonitor):
        """分会话累计：不同 conversation_id 命中率独立。"""
        isolated_monitor.record_llm_call_sync(
            cache_read=900, cache_creation=0, prompt_total=1000, model="m", tier="fast", conversation_id="c1"
        )
        isolated_monitor.record_llm_call_sync(
            cache_read=100, cache_creation=0, prompt_total=1000, model="m", tier="fast", conversation_id="c2"
        )
        r1 = asyncio.run(isolated_monitor.conversation_hit_rate("c1"))
        r2 = asyncio.run(isolated_monitor.conversation_hit_rate("c2"))
        assert r1 == pytest.approx(0.9)
        assert r2 == pytest.approx(0.1)
        assert isolated_monitor.overall_hit_rate() == pytest.approx(0.5)

    def test_generator_reports_cache_usage_to_monitor(self, isolated_monitor: CacheMonitor):
        """task96 批判③：generator._report_cache_usage 解析 usage 并上报 CacheMonitor（真实多轮观测入口）。"""
        from app.chat import generator as gen

        set_cache_monitor(isolated_monitor)
        inst = gen._ChatClient.__new__(gen._ChatClient)  # 绕过 __init__，方法仅用 settings

        data = {
            "usage": {
                "prompt_tokens": 1000,
                "prompt_tokens_details": {"cache_read_input_tokens": 700, "cache_creation_input_tokens": 0},
            }
        }
        inst._report_cache_usage(data, "fast")
        assert isolated_monitor.overall_hit_rate() == pytest.approx(0.7)
        assert isolated_monitor._global.calls == 1

    def test_generator_skips_when_no_usage(self, isolated_monitor: CacheMonitor):
        """usage 全 0（网关未回 usage / 本地兜底）→ 不上报，不污染命中率。"""
        from app.chat import generator as gen

        set_cache_monitor(isolated_monitor)
        inst = gen._ChatClient.__new__(gen._ChatClient)
        inst._report_cache_usage({"usage": {"prompt_tokens": 0}}, "fast")
        inst._report_cache_usage({}, "fast")
        assert isolated_monitor._global.calls == 0

    def test_metrics_endpoint_exposes_cache_dashboard(self):
        """GWT④ 端点接线：/metrics 与 /api/metrics/cache-context-dashboard 均注册。"""
        from app.monitoring import router

        paths = [getattr(r, "path", None) for r in router.router.routes]
        assert "/metrics" in paths
        assert "/api/metrics/cache-context-dashboard" in paths


# ============================================================
# GWT③：MCP 变更不影响命中率（R3 deferred）；模型切换 → 命中率下降且记录失效原因
# ============================================================
class TestGwt3Invalidation:
    def test_mcp_change_no_invalidation_when_deferred(self, isolated_monitor: CacheMonitor):
        """MCP 工具描述重写（经 apply_rewrite_to_deferred）→ 该工具前缀 key 不变 → 不应记 mcp_change 失效。"""
        idx = deferred.DeferredToolIndex()
        idx.set_tools([_sample_tools()[0]])  # 单工具索引：聚焦该工具前缀
        k0 = idx.prefix_key()
        meta = dict(_sample_tools()[0])
        description_reviewer.apply_rewrite_to_deferred(
            idx, meta,
            "检索知识库文档。返回相关片段与出处。（v2）新增语义重排与引用链接。"
        )
        assert idx.prefix_key() == k0
        # 缓存监控侧未收到任何 mcp_change 失效 → 命中率不受影响
        assert isolated_monitor.invalidation_count("mcp_change") == 0

    def test_model_switch_records_invalidation_and_drops_hit_rate(self, isolated_monitor: CacheMonitor):
        """模型切换（同 tier 内模型名变化）→ 记 model_switch 失效，且后续纯未命中使整体命中率下降。"""
        # 第一轮：高命中（cache_read 占 900/1000）
        isolated_monitor.record_llm_call_sync(
            cache_read=900, cache_creation=0, prompt_total=1000, model="deepseek-v3", tier="fast"
        )
        rate_before = isolated_monitor.overall_hit_rate()
        # 第二轮：模型切换 → 前缀失效，整段未命中（cache_read=0, cache_creation=0）
        isolated_monitor.record_llm_call_sync(
            cache_read=0, cache_creation=0, prompt_total=1000, model="deepseek-v4", tier="fast"
        )
        rate_after = isolated_monitor.overall_hit_rate()
        assert isolated_monitor.invalidation_count("model_switch") >= 1
        assert rate_after < rate_before, f"模型切换后命中率应下降：{rate_before} -> {rate_after}"

    def test_explicit_invalidation_recorded(self, isolated_monitor: CacheMonitor):
        """record_invalidation 显式记录前缀失效（compaction / context_edit 等），供定位根因。"""
        isolated_monitor.record_invalidation("compaction", layer="project", detail="over_threshold")
        assert isolated_monitor.invalidation_count("compaction") == 1
        reasons = isolated_monitor.invalidation_reasons()
        assert any(r["reason"] == "compaction" for r in reasons)


# ============================================================
# GWT④：衔接 task96 ContextUsageMonitor → 联合看板
# ============================================================
class TestGwt4JointDashboard:
    def test_joint_dashboard_merges_context_water_level(self, isolated_monitor: CacheMonitor):
        """joint_dashboard 同时返回『上下文水位(task96)』+『缓存命中(task97)』。"""
        from app.ai import context_edit as ce

        # 先让 task96 监控器有样本
        big = ce.measure_usage(
            [{"role": "system", "content": "p"}] + [{"role": "assistant", "content": "x" * 2000}],
            window_tokens=32000, edit_threshold=6000, warn_ratio=0.6,
        )
        ce.get_context_monitor().record(big, action="compaction", session_id="s1")

        # 让 task97 缓存监控有样本
        isolated_monitor.record_llm_call_sync(
            cache_read=800, cache_creation=0, prompt_total=1000, model="m", tier="fast"
        )

        board = asyncio.run(isolated_monitor.joint_dashboard(session_id="s1"))
        assert "cache" in board and "context" in board
        assert board["cache"]["overall_hit_rate"] > 0.5
        assert board["context"]["samples"] >= 1
        assert board["context"]["actions"].get("compaction", 0) >= 1


# ============================================================
# 批判承接：task95 批判③（deferred 接入 tool_specs 端到端）
# ============================================================
class TestCritique95DeferredToolSpecs:
    def test_tool_specs_end_to_end_prefix_stable(self):
        """tool_specs 形态输入 → 摘要列表稳定 + 完整定义按 (server_id,name) 独立缓存。"""
        tools = _sample_tools()
        listing = deferred.build_summary_listing(tools)
        assert deferred.contains_full_description(listing) is False  # 前缀不含完整描述
        # 完整定义按需拉取且含 input_schema
        full = deferred.load_full_spec(tools[0])
        assert full["description"].startswith("检索知识库文档")
        assert "input_schema" in full and "q" in full["input_schema"].get("properties", {})
        # 前缀 key 与每工具完整定义 key 解耦：新增工具不驱逐其他完整定义缓存
        k_a = deferred.full_spec_key(1, "search_docs")
        tools2 = tools + [{"tool_name": "new_tool", "description": "新工具。", "server_id": 3,
                           "server_code": "extra", "input_schema": {"type": "object"}}]
        assert deferred.listing_key(deferred.build_summary_listing(tools2)) != deferred.listing_key(listing)
        assert deferred.full_spec_key(1, "search_docs") == k_a

    def test_prefix_key_stable_under_rewrite(self):
        idx = deferred.DeferredToolIndex()
        idx.set_tools(_sample_tools())
        k0 = idx.prefix_key()
        idx.set_tools([
            dict(t, description=t["description"] + " 追加冗余内容以验证前缀稳定性。")
            for t in _sample_tools()
        ])
        assert idx.prefix_key() == k0


# ============================================================
# 批判承接：task96 批判②（context_edit 真正接入 graph 决策链）
# ============================================================
class TestCritique96ContextEditGraph:
    def test_graph_wires_compact_context_edit_plan(self):
        """build_graph 包含 context_edit 节点，且边 compact→context_edit→plan 成立。"""
        g = G.compile_graph()
        nodes = set(g.get_graph().nodes.keys())
        assert "context_edit" in nodes
        edges = [(e.source, e.target) for e in g.get_graph().edges]
        assert ("compact", "context_edit") in edges
        assert ("context_edit", "plan") in edges

    def test_context_edit_node_runs_and_plan_consumes(self):
        """context_edit_node 真正调用 apply_context_strategy（task96 批判②），结果被 plan_node 消费。"""
        from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
        import app.config as cfg

        # 降低阈值强制超阈值，验证 context_edit 真实编辑 + 记录水位
        old = cfg.settings.COMPACTION_TOKEN_THRESHOLD
        cfg.settings.COMPACTION_TOKEN_THRESHOLD = 1000
        try:
            msgs = []
            for i in range(20):
                msgs.append(HumanMessage(content=f"问题{i}"))
                msgs.append(AIMessage(content=f"调用工具{i}",
                                      tool_calls=[{"name": f"t{i}", "args": {}, "id": f"c{i}"}]))
                msgs.append(ToolMessage(content=f"[工具 t{i} 返回] 结果{'x' * 500}", tool_call_id=f"c{i}"))

            state = {"messages": msgs, "session_id": "crit", "compaction": None, "context_edit": None}
            res = asyncio.run(G.context_edit_node(state))
            ce_out = res["context_edit"]
            assert ce_out is not None
            assert len(ce_out["messages"]) < len(msgs), "context_edit 应真实删减消息"
            # 监控器被记录（联合看板数据源）
            from app.ai import context_edit as ce
            assert len(ce.get_context_monitor().records) >= 1

            plan = asyncio.run(G.plan_node({**state, "intent": "knowledge",
                                            "context_edit": ce_out, "skill_context": ""}))
            assert "历史上下文" in plan["tasks"][0]["input"], "plan_node 未消费 context_edit 输出"
        finally:
            cfg.settings.COMPACTION_TOKEN_THRESHOLD = old
