# -*- coding: utf-8 -*-
"""W-NEXT-LLMSWITCH-001（task29 批判② 收口）：DeepSeek 混合推理模型 thinking 开关。

三态盲测的单元层钉死（真实 API 盲测见 test-reports/WNEXTLLMSWITCH1-completion-report.md）：
- 状态① thinking disabled 生效：非流式 DeepSeek 请求体注入 {"thinking": {"type": "disabled"}}；
- 状态② 开关关闭 → 行为回推理态：请求体不含 thinking 字段（供应商默认=推理开启）；
- 状态③ 容错：非 deepseek-* 模型不注入（网关 4xx 防御）；网关对 thinking 返回 400 时
  剥除后同模型重试一次（不整链误降级 FAST）；流式路径一律不注入。

本文件全部为可独立运行的单元测试：LLM 网关用 stub session 模拟，无真实网络依赖。
"""
from __future__ import annotations

import json

import pytest

from app.chat.generator import _ChatClient
from app.config import settings


DEEPSEEK_OK_BODY = {
    "choices": [{"message": {"content": "牛顿第二定律：F=ma。"}}],
    "usage": {},
}


class _FakeResp:
    """非流式假响应。"""

    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.headers = {}

    def json(self):
        return self._payload


class _FakeStreamResp:
    """流式假响应（支持 with 上下文与 iter_lines）。"""

    status_code = 200
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_lines(self, decode_unicode=True):
        yield 'data: {"choices":[{"delta":{"content":"he"}}]}'
        yield 'data: {"choices":[{"delta":{"content":"llo"}}]}'
        yield "data: [DONE]"


class _StubSession:
    """记录每次请求体，按脚本依次返回响应。"""

    def __init__(self, responses):
        self._responses = list(responses)
        self.payloads: list[dict] = []
        self.urls: list[str] = []
        trust_env = False

    def post(self, url, headers=None, json=None, timeout=None, stream=False):
        self.payloads.append(json)
        self.urls.append(url)
        if stream:
            return _FakeStreamResp()
        return self._responses.pop(0)


@pytest.fixture()
def deepseek_env(monkeypatch):
    """钉住双源环境：STRONG=deepseek-flash（DeepSeek 官方），FAST=minimax-m3（ark）。"""
    monkeypatch.setattr(settings, "LLM_MODEL_STRONG", "deepseek-flash")
    monkeypatch.setattr(settings, "LLM_MODEL_FAST", "minimax-m3")
    monkeypatch.setattr(settings, "LLM_THINKING_DISABLED", True)
    monkeypatch.setattr(settings, "LLM_STRONG_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setattr(settings, "LLM_FAST_BASE_URL", "https://ark.cn-beijing.volces.com/api/plan/v3")
    return settings


# ════════════════════════════════════════════════════════════
# 状态①：开关开启 + deepseek-* 模型 → 注入 thinking=disabled
# ════════════════════════════════════════════════════════════
class TestThinkingDisabledInjected:
    def test_nonstream_deepseek_body_has_thinking_disabled(self, deepseek_env):
        """非流式 STRONG（deepseek-flash）请求体必须带 {"thinking": {"type": "disabled"}}。"""
        client = _ChatClient.get()
        stub = _StubSession([_FakeResp(200, DEEPSEEK_OK_BODY)])
        client._session = stub
        answer = client.call_chat(messages=[{"role": "user", "content": "hi"}], model="strong",
                                  temperature=0.0, max_tokens=100)
        assert answer == "牛顿第二定律：F=ma。"
        assert stub.payloads[0]["thinking"] == {"type": "disabled"}
        assert stub.payloads[0]["model"] == "deepseek-flash"

    def test_gate_helpers_return_true(self, deepseek_env):
        client = _ChatClient.get()
        body: dict = {}
        assert client._inject_thinking_disabled(body, "strong") is True
        assert body["thinking"] == {"type": "disabled"}


# ════════════════════════════════════════════════════════════
# 状态②：开关关闭 → 不注入（供应商默认 = 推理态，行为回退）
# ════════════════════════════════════════════════════════════
class TestThinkingSwitchOff:
    def test_switch_off_no_thinking_key(self, deepseek_env):
        deepseek_env.LLM_THINKING_DISABLED = False
        client = _ChatClient.get()
        stub = _StubSession([_FakeResp(200, DEEPSEEK_OK_BODY)])
        client._session = stub
        client.call_chat(messages=[{"role": "user", "content": "hi"}], model="strong",
                         temperature=0.0, max_tokens=100)
        assert "thinking" not in stub.payloads[0]

    def test_gate_helper_off_returns_false(self, deepseek_env):
        deepseek_env.LLM_THINKING_DISABLED = False
        client = _ChatClient.get()
        assert client._inject_thinking_disabled({}, "strong") is False


# ════════════════════════════════════════════════════════════
# 状态③：容错——非 deepseek 模型不注入；400 提及 thinking → 剥除重试；流式不注入
# ════════════════════════════════════════════════════════════
class TestThinkingTolerance:
    def test_non_deepseek_model_not_injected(self, deepseek_env):
        """生效模型名非 deepseek-*（如 qwen-plus / minimax-m3）→ 一律不注入（网关 4xx 防御）。"""
        client = _ChatClient.get()
        for tier, name in (("strong", "qwen-plus"), ("fast", "minimax-m3")):
            deepseek_env.LLM_MODEL_STRONG = name
            deepseek_env.LLM_MODEL_FAST = name
            body: dict = {}
            assert client._inject_thinking_disabled(body, tier) is False
            assert "thinking" not in body
        deepseek_env.LLM_MODEL_STRONG = "deepseek-flash"

    def test_deepseek_400_thinking_strips_and_retries_same_model(self, deepseek_env):
        """DeepSeek 网关对 thinking 返回 400 → 剥除后同模型重试一次并成功（不切 FAST 档）。"""
        client = _ChatClient.get()
        err = json.dumps({"error": {"message": "Invalid parameter: thinking",
                                    "type": "invalid_request_error"}}, ensure_ascii=False)
        stub = _StubSession([
            _FakeResp(400, text=err),
            _FakeResp(200, DEEPSEEK_OK_BODY),
        ])
        client._session = stub
        answer = client.call_chat(messages=[{"role": "user", "content": "hi"}], model="strong",
                                  temperature=0.0, max_tokens=100)
        assert answer == "牛顿第二定律：F=ma。"
        assert len(stub.payloads) == 2
        assert stub.payloads[0].get("thinking") == {"type": "disabled"}
        assert "thinking" not in stub.payloads[1]
        # 同模型重试：两次都打到 STRONG 源（deepseek 官方），未误降级 FAST
        assert stub.payloads[0]["model"] == "deepseek-flash"
        assert stub.payloads[1]["model"] == "deepseek-flash"
        assert all(u.startswith("https://api.deepseek.com") for u in stub.urls)

    def test_400_unrelated_reason_raises_normally(self, deepseek_env):
        """400 与 thinking 无关（如模型不存在）→ 不剥除重试，正常抛出走既有重试链。"""
        from app.core import retry as retry_mod

        client = _ChatClient.get()
        err = json.dumps({"error": {"message": "Model Not Exist",
                                    "type": "invalid_request_error"}})
        stub = _StubSession([_FakeResp(400, text=err)])
        client._session = stub
        with pytest.raises(RuntimeError, match="LLM HTTP 400"):
            client.call_chat(messages=[{"role": "user", "content": "hi"}], model="strong",
                             temperature=0.0, max_tokens=100)
        assert len(stub.payloads) == 1
        # 既有容错链：invalid_request_error → MODEL_ERROR → 立即切源
        assert retry_mod.should_switch_model(retry_mod.classify_error(
            RuntimeError(f"LLM HTTP 400: {err}")))
        assert retry_mod.switch_model_source("strong") == "fast"

    def test_stream_path_never_injects_thinking(self, deepseek_env):
        """流式路径保持 reasoning 流式语义：请求体一律不含 thinking 字段。"""
        client = _ChatClient.get()
        stub = _StubSession([])
        client._session = stub
        tokens = list(client.call_chat_stream(messages=[{"role": "user", "content": "hi"}],
                                              model="strong", temperature=0.0, max_tokens=100))
        assert tokens == ["he", "llo"]
        assert len(stub.payloads) == 1
        assert "thinking" not in stub.payloads[0]
        assert stub.payloads[0]["stream"] is True
