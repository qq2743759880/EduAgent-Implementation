# -*- coding: utf-8 -*-
"""task95 契约测试：MCP 增强 R3（延迟加载/认证/重连/动态更新/子代理隔离）。

纯内存 / 纯函数为主，网络与睡眠均可注入，无真实 LLM / 无真实 MCP server，
可直接运行（落在测试窗口外亦安全，零外部依赖）：
    cd edu-agent && .venv/Scripts/python.exe -m pytest tests/test_contract_task95.py -q

GWT：
① Given MCP 工具列表变更，When 会话中，Then 缓存前缀不受影响（deferred 语义）
② Given server 进程退出，When 检测，Then 自动重连（指数退避 ≤5）
③ Given 子代理配置 mcpServers 子集，When 解析，Then 仅该子代理可见，主上下文不含这些工具
④ Given OAuth 配置，When 启动，Then 自动走认证流程并注入请求
"""
from __future__ import annotations

import asyncio
import time

import pytest

from app.ai import prompt_cache as pc
from app.mcp import auth, deferred, dynamic_update, isolation, reconnect


# ============================================================
# GWT① 延迟加载：工具描述变更不破坏缓存前缀（deferred 语义）
# ============================================================
class TestDeferredToolLoading:
    def _sample_tools(self):
        return [
            {"tool_name": "search_docs", "description": "检索知识库文档。返回相关片段与出处。",
             "server_id": 1, "server_code": "kb", "category": "rag",
             "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}}},
            {"tool_name": "send_email", "description": "发送邮件通知。参数 to/subject/body。",
             "server_id": 2, "server_code": "mail", "category": "comm",
             "input_schema": {"type": "object", "properties": {"to": {"type": "string"}}}},
        ]

    def test_summary_listing_stable_after_full_rewrite(self):
        tools = self._sample_tools()
        l1 = deferred.build_summary_listing(tools)
        k1 = deferred.listing_key(l1)

        # task33 重写完整描述：首句不变、追加更长内容 → 延迟加载的「摘要列表」应不变
        rewritten = [
            dict(t, description=(
                "检索知识库文档。返回相关片段与出处。"  # 首句保持
                "（v2 重写）支持语义召回与重排，自动追加引用链接，处理更长的上下文摘要与多语言片段。"
            )) if t["tool_name"] == "search_docs" else t
            for t in tools
        ]
        l2 = deferred.build_summary_listing(rewritten)
        assert l1 == l2, "重写完整描述不应改变摘要列表（保护前缀）"
        assert deferred.listing_key(l2) == k1

    def test_cache_prefix_not_invalidated_on_rewrite(self):
        tools = self._sample_tools()
        l1 = deferred.build_summary_listing(tools)
        cache = pc.PromptCache()
        cache.set("project", l1, reason="init")
        # 重写完整描述（首句不变）→ 摘要列表 key 不变 → 不应产生失效事件
        rewritten = [dict(t, description=t["description"] + " 追加冗余内容以验证前缀稳定性。")
                     for t in tools]
        l2 = deferred.build_summary_listing(rewritten)
        cache.set("project", l2, reason="mcp_tool_change")
        assert cache.invalidations_list(layer="project") == [], \
            "deferred: 完整描述重写不应使前缀缓存失效"

    def test_full_spec_deferred_not_in_prefix(self):
        tools = self._sample_tools()
        listing = deferred.build_summary_listing(tools)
        # 前缀（摘要列表）不含完整描述长文本
        assert deferred.contains_full_description(listing) is False
        # 完整定义按需拉取，且包含原长描述
        full = deferred.load_full_spec(tools[0])
        assert full["description"].startswith("检索知识库文档")
        assert "input_schema" in full

    def test_per_tool_full_def_cache_independent_of_listing(self):
        # 每工具完整定义 key 独立于摘要列表：新增工具不驱逐其他工具的完整定义缓存
        k_a = deferred.full_spec_key(1, "search_docs")
        tools = self._sample_tools()
        tools.append({"tool_name": "new_tool", "description": "新增工具。",
                      "server_id": 3, "server_code": "extra"})
        l3 = deferred.build_summary_listing(tools)
        assert deferred.listing_key(l3) != deferred.listing_key(deferred.build_summary_listing(self._sample_tools()))
        # 但 search_docs 的完整定义缓存 key 不变
        assert deferred.full_spec_key(1, "search_docs") == k_a

    def test_index_prefix_key_stable(self):
        idx = deferred.DeferredToolIndex()
        idx.set_tools(self._sample_tools())
        k0 = idx.prefix_key()
        # 重写描述后重设
        idx.set_tools([dict(t, description=t["description"] + " 冗余") for t in self._sample_tools()])
        assert idx.prefix_key() == k0, "DeferredToolIndex 前缀 key 在描述重写后应保持稳定"


# ============================================================
# GWT② 自动重连：进程退出 → 指数退避重连（≤5）
# ============================================================
class _FakeSleep:
    def __init__(self):
        self.calls: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.calls.append(delay)


class _FlakyConnect:
    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.n = 0

    async def __call__(self):
        if self.n < self.fail_times:
            self.n += 1
            raise ConnectionError("server 进程已退出")
        return f"conn-ok@{self.n}"


class TestAutoReconnect:
    async def test_recovers_after_transient_failures(self):
        policy = reconnect.ReconnectPolicy(max_retries=5, base_delay_s=1.0, factor=2.0, max_delay_s=30.0)
        fs = _FakeSleep()
        conn = await reconnect.with_reconnect(_FlakyConnect(fail_times=3), policy=policy, sleep=fs)
        assert conn == "conn-ok@3"
        # 3 次失败 → 3 次退避睡眠：1, 2, 4
        assert fs.calls == [1.0, 2.0, 4.0], f"退避应为 [1,2,4]，实测 {fs.calls}"

    async def test_exhausts_after_max_retries(self):
        policy = reconnect.ReconnectPolicy(max_retries=5, base_delay_s=1.0, factor=2.0, max_delay_s=30.0)
        fs = _FakeSleep()
        with pytest.raises(reconnect.ReconnectExhausted):
            await reconnect.with_reconnect(_FlakyConnect(fail_times=99), policy=policy, sleep=fs)
        # 重试 5 次 → 5 次睡眠，最后延迟被 30s 上限钳制：1,2,4,8,16
        assert len(fs.calls) == 5, f"应睡眠 5 次（max_retries），实测 {fs.calls}"
        assert fs.calls == [1.0, 2.0, 4.0, 8.0, 16.0]
        assert all(d <= policy.max_delay_s for d in fs.calls)

    def test_backoff_delay_formula_and_cap(self):
        p = reconnect.ReconnectPolicy(base_delay_s=1.0, factor=2.0, max_delay_s=30.0)
        assert reconnect.backoff_delay(0, p) == 1.0
        assert reconnect.backoff_delay(1, p) == 2.0
        assert reconnect.backoff_delay(4, p) == 16.0
        # 超过上限被钳制
        assert reconnect.backoff_delay(10, p) == 30.0


# ============================================================
# GWT③ 子代理级 mcpServers 隔离 + per-tool 结果大小限制
# ============================================================
class TestSubagentIsolation:
    def _all_tools(self):
        return [
            {"tool_name": "kb_search", "server_code": "kb"},
            {"tool_name": "kb_summarize", "server_code": "kb"},
            {"tool_name": "mail_send", "server_code": "mail"},     # 子代理独占
            {"tool_name": "crm_upsert", "server_code": "crm"},      # 主+子代理共享
        ]

    def test_main_context_excludes_subagent_only_servers(self):
        tools = self._all_tools()
        # 主代理声明可见 server = kb, crm；mail 仅子代理使用
        main = isolation.filter_main_context_tools(tools, main_server_codes=["kb", "crm"])
        main_names = {t["tool_name"] for t in main}
        assert "kb_search" in main_names and "kb_summarize" in main_names
        assert "crm_upsert" in main_names
        assert "mail_send" not in main_names, "主上下文不应含子代理独占的 mail 工具"

    def test_subagent_resolves_its_own_subset(self):
        tools = self._all_tools()
        scope = isolation.MCPScope(name="sa-tool", mcp_servers=("mail", "crm"))
        sub = isolation.resolve_subagent_tools(tools, scope)
        sub_names = {t["tool_name"] for t in sub}
        assert sub_names == {"mail_send", "crm_upsert"}, "子代理只应看到其 mcpServers 子集"
        # 主上下文确实不含子代理独占工具（隔离闭环验收）
        main = isolation.filter_main_context_tools(tools, main_server_codes=["kb", "crm"])
        main_names = {t["tool_name"] for t in main}
        assert sub_names - main_names == {"mail_send"}, "子代理独占工具不应泄漏进主上下文"

    def test_per_tool_result_truncation(self):
        big = "x" * (isolation.PER_TOOL_RESULT_MAX_CHARS + 500)
        text, truncated = isolation.truncate_tool_result(big)
        assert truncated is True
        assert len(text) <= isolation.PER_TOOL_RESULT_MAX_CHARS + 60
        small = "ok"
        text2, truncated2 = isolation.truncate_tool_result(small)
        assert truncated2 is False and text2 == "ok"


# ============================================================
# GWT④ OAuth 认证：启动自动走认证流程并注入请求
# ============================================================
class TestOAuthAndApiKey:
    def test_api_key_header_injection(self):
        cfg = auth.AuthConfig(auth_type="api_key", api_key="k-123",
                              api_key_header="X-API-Key", api_key_prefix="")
        h = auth.build_auth_headers(cfg)
        assert h.get("X-API-Key") == "k-123"

    def test_oauth_bearer_injection(self):
        cfg = auth.AuthConfig(auth_type="oauth", access_token="tok-abc",
                              api_key_header="Authorization")
        h = auth.build_auth_headers(cfg)
        assert h.get("Authorization") == "Bearer tok-abc"

    def test_token_expiry_logic(self):
        assert auth.is_token_expired(auth.AuthConfig()) is True  # 无 token
        near = auth.AuthConfig(access_token="t", expires_at=time.time() + 5)  # 余量内→过期
        assert auth.is_token_expired(near, leeway_s=30) is True
        ok = auth.AuthConfig(access_token="t", expires_at=time.time() + 100)
        assert auth.is_token_expired(ok) is False

    async def test_oauth_refresh_grant(self):
        captured: dict = {}

        def fake_post(url, data, headers):
            captured.update({"url": url, "data": dict(data)})
            return {"access_token": "new-tok", "refresh_token": "new-ref", "expires_in": 3600}

        cfg = auth.AuthConfig(auth_type="oauth", token_url="https://srv/oauth/token",
                              refresh_token="r0", client_id="cid", client_secret="sec",
                              scopes=["mcp.read"])
        client = auth.OAuthClient(cfg, post_fn=fake_post)
        out = await client.refresh()
        assert out.access_token == "new-tok"
        assert out.expires_at > time.time()
        assert captured["data"]["grant_type"] == "refresh_token"

    def test_authorization_url_constructed(self):
        cfg = auth.AuthConfig(auth_type="oauth", auth_url="https://srv/authorize",
                              client_id="cid", redirect_uri="https://app/cb",
                              scopes=["mcp.read", "mcp.write"])
        url = auth.OAuthClient(cfg).authorization_url(state="xyz")
        assert url.startswith("https://srv/authorize?")
        assert "response_type=code" in url and "client_id=cid" in url
        assert "scope=mcp.read+mcp.write" in url and "state=xyz" in url

    async def test_ensure_token_refreshes_when_expired(self):
        calls = {"n": 0}

        def fake_post(url, data, headers):
            calls["n"] += 1
            return {"access_token": "fresh", "expires_in": 3600}

        cfg = auth.AuthConfig(auth_type="oauth", token_url="https://srv/t",
                              refresh_token="r", client_id="c", client_secret="s",
                              expires_at=0)  # 已过期（无有效 token）
        client = auth.OAuthClient(cfg, post_fn=fake_post)
        out = await client.ensure_token()
        assert out.access_token == "fresh" and calls["n"] == 1


# ============================================================
# 动态工具更新监听（R3(5)）
# ============================================================
class TestDynamicToolUpdate:
    def test_diff_added_removed_updated(self):
        reg = dynamic_update.DynamicToolRegistry()
        reg.notify_tools_changed(1, [{"tool_name": "a"}, {"tool_name": "b"}])
        ev = reg.notify_tools_changed(1, [{"tool_name": "a"}, {"tool_name": "c"}])
        assert ev.added == ["c"] and ev.removed == ["b"] and ev.updated == []
        # 更新：a 的 meta 变化
        ev2 = reg.notify_tools_changed(1, [{"tool_name": "a", "description": "v2"}, {"tool_name": "c"}])
        assert ev2.updated == ["a"] and ev2.added == [] and ev2.removed == []

    def test_idempotent_on_same_input(self):
        reg = dynamic_update.DynamicToolRegistry()
        reg.notify_tools_changed(1, [{"tool_name": "a"}, {"tool_name": "b"}])
        ev = reg.notify_tools_changed(1, [{"tool_name": "a"}, {"tool_name": "b"}])
        assert ev.added == [] and ev.removed == [] and ev.updated == []

    async def test_poll_applies_change(self):
        state = [{"tool_name": "x"}]
        reg = dynamic_update.DynamicToolRegistry(fetch_fn=lambda sid: state)
        await reg.poll(1)
        state.append({"tool_name": "y"})
        ev = await reg.poll(1)
        assert ev.added == ["y"]
        assert {t["tool_name"] for t in reg.current(1)} == {"x", "y"}
