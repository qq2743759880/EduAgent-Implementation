# -*- coding: utf-8 -*-
"""Agent 循环决策层单测：JSON 解析 / 失败回退 / run_agent_turn 编排（mock LLM）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.chat.flows import agent as agent_mod


# ============================================================
# _safe_json_extract
# ============================================================
def test_extract_plain_json():
    raw = '{"need_search": true, "query_rewrite": "x", "tool_plan": [], "answer_direct": ""}'
    assert agent_mod._safe_json_extract(raw)["need_search"] is True


def test_extract_codeblock_json():
    raw = '```json\n{"need_search": false, "answer_direct": "hi"}\n```'
    obj = agent_mod._safe_json_extract(raw)
    assert obj is not None
    assert obj["need_search"] is False
    assert obj["answer_direct"] == "hi"


def test_extract_with_noise():
    raw = 'Sure! Here is the result: {"need_search": true, "query_rewrite": "a b c", "tool_plan": [], "answer_direct": ""}  done.'
    obj = agent_mod._safe_json_extract(raw)
    assert obj["query_rewrite"] == "a b c"


def test_extract_invalid_returns_none():
    assert agent_mod._safe_json_extract("not json at all") is None
    assert agent_mod._safe_json_extract("") is None


# ============================================================
# decide_agent_plan（mock LLM）
# ============================================================
class _FakeClient:
    def __init__(self, raw_out):
        self.raw_out = raw_out
        self.calls = []

    def call_chat_with_retry(self, **kw):
        self.calls.append(kw)
        return self.raw_out


@pytest.mark.asyncio
async def test_decide_need_search(monkeypatch):
    fake = _FakeClient('{"need_search": true, "query_rewrite": "英语 音标 ENG-L1", "tool_plan": [], "answer_direct": ""}')
    monkeypatch.setattr(agent_mod, "_ChatClient", type("C", (), {"get": staticmethod(lambda: fake)}))

    plan = await agent_mod.decide_agent_plan("英语音标怎么学")
    assert plan.need_search is True
    assert plan.query_rewrite == "英语 音标 ENG-L1"
    assert plan.decision_error is None
    # 确认决策 prompt 里带了工具清单（[] 空列表）
    assert "可用 MCP 工具" in fake.calls[0]["messages"][0]["content"]
    assert "[]" in fake.calls[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_decide_no_search_direct(monkeypatch):
    fake = _FakeClient('{"need_search": false, "query_rewrite": "", "tool_plan": [], "answer_direct": "你好！我是 EduAgent，很高兴为你服务。"}')
    monkeypatch.setattr(agent_mod, "_ChatClient", type("C", (), {"get": staticmethod(lambda: fake)}))
    plan = await agent_mod.decide_agent_plan("你好")
    assert plan.need_search is False
    assert plan.answer_direct != ""


@pytest.mark.asyncio
async def test_decide_llm_failure_falls_back_to_search(monkeypatch):
    class Boom:
        @staticmethod
        def get():
            raise RuntimeError("LLM down")

    monkeypatch.setattr(agent_mod, "_ChatClient", Boom)
    plan = await agent_mod.decide_agent_plan("任意问题")
    # LLM 失败 → 保守回退检索
    assert plan.need_search is True
    assert plan.decision_error is not None


@pytest.mark.asyncio
async def test_decide_unparseable_falls_back(monkeypatch):
    fake = _FakeClient("抱歉，我无法理解你的问题。")
    monkeypatch.setattr(agent_mod, "_ChatClient", type("C", (), {"get": staticmethod(lambda: fake)}))
    plan = await agent_mod.decide_agent_plan("xxx")
    assert plan.need_search is True
    assert plan.decision_error == "decision_unparseable"


# ============================================================
# run_agent_turn（mock 决策 + mock 检索）
# ============================================================
@pytest.mark.asyncio
async def test_run_agent_turn_searches(monkeypatch):
    from app.chat.retriever import RetrievalBundle

    async def fake_retrieve(query, **kw):
        return RetrievalBundle(
            docs=[], raw_retrieved_count=3, graph_entities=[], rewrite_query=query, degraded_reason=None,
        )

    async def fake_decide(query, tool_metas=None, timeout=30.0):
        return agent_mod.AgentPlan(need_search=True, query_rewrite="rew", tool_plan=[], answer_direct="")

    monkeypatch.setattr(agent_mod, "decide_agent_plan", fake_decide)
    monkeypatch.setattr(agent_mod, "retrieve_three_channel", fake_retrieve)

    res = await agent_mod.run_agent_turn("原始问题", user_id=1, role="student")
    assert res["plan"].need_search is True
    assert res["bundle"].raw_retrieved_count == 3
    # 检索用改写后的 query
    assert res["bundle"].rewrite_query == "rew"


@pytest.mark.asyncio
async def test_run_agent_turn_no_search(monkeypatch):
    async def fake_decide(query, tool_metas=None, timeout=30.0):
        return agent_mod.AgentPlan(need_search=False, query_rewrite="", tool_plan=[], answer_direct="你好！")

    monkeypatch.setattr(agent_mod, "decide_agent_plan", fake_decide)

    called = {"retrieved": False}

    async def fake_retrieve(query, **kw):
        called["retrieved"] = True
        return None

    monkeypatch.setattr(agent_mod, "retrieve_three_channel", fake_retrieve)
    res = await agent_mod.run_agent_turn("闲聊", user_id=1, role="student")
    # 不需要检索 → 不调用检索
    assert called["retrieved"] is False
    assert res["bundle"].docs == []
    assert res["plan"].answer_direct == "你好！"
