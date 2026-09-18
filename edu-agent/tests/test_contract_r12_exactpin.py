# -*- coding: utf-8 -*-
"""R12 契约测试：子代理工具调用 exact-pin（对标 hermes 范式，kb-deep-1-orchestration.md §5/TOP10 #9）。

执行方式：in-process + fake LLM + fake tool（不连真实 LLM/MCP/DB），纯单测级证据。

验收面（kickoff C-01 对齐实现三项）：
① 精确 pin 过：白名单内工具 + 精确字段 → 正常派发执行
② 模糊拒：缺必填/未知字段/类型不符/空白工具名/前后缀空白 → EXACT_PIN_REJECTED 结构化错误，
   不派发、记账入 artifact、回灌 LLM 自纠错
③ 未知工具拒：白名单外工具 → 结构化错误携 allowed_tools；连续 2 次模糊 → fail-closed 终止
④ q 精确绑定：_direct_tool_args 从 plan 任务串提取「问题本体」（R20-b 残差 18 条根因修复）
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.ai.subagents import (
    artifact_store,
    get_subagent_spec,
    run_subagent,
)
from app.ai.subagents.runner import _direct_tool_args, _parse_action
from app.ai.subagents.tool_schemas import (
    ERROR_CODE,
    MAX_CONSECUTIVE_VAGUE_REJECTS,
    TOOL_ARG_SCHEMAS,
    validate_tool_args,
)


@pytest.fixture(autouse=True)
def _disable_prefetch(monkeypatch: pytest.MonkeyPatch):
    """本文件测的是 LLM 决策循环的 exact-pin 语义——关闭单工具确定性预执行（生产默认开）。"""
    from app.config import settings

    monkeypatch.setattr(settings, "SUBAGENT_DIRECT_TOOL_ENABLED", False)


def _run(coro):
    return asyncio.run(coro)


def _final_llm(text: str = "最终摘要"):
    n = {"v": 0}

    async def llm(messages, model):
        n["v"] += 1
        if n["v"] == 1:
            return json.dumps({"tool": None, "final": text})
        return json.dumps({"tool": None, "final": text})

    return llm


class TestExactPinPass:
    """验收面①：精确 pin 过——白名单内工具 + 精确字段正常派发。"""

    def test_exact_call_dispatches(self):
        """search 子代理 {"tool":"search_knowledge","args":{"q":...}} → handler 收到精确 q。"""
        spec = get_subagent_spec("search")
        got: list[dict] = []

        async def tool(args=None):
            got.append(dict(args or {}))
            return {"docs": [{"id": 1}]}

        turns = {"v": 0}

        async def llm(messages, model):
            turns["v"] += 1
            if turns["v"] == 1:
                return json.dumps({"tool": "search_knowledge", "args": {"q": "特征值是什么"}})
            return json.dumps({"tool": None, "final": "摘要"})

        r = _run(run_subagent(spec, objective="检索", input_text="（问题：特征值是什么）",
                              tool_services={"search_knowledge": tool}, llm=llm))
        assert r.ok and r.tool_calls == 1
        assert got == [{"q": "特征值是什么"}], "handler 必须收到逐字段精确绑定的 args"

    def test_exact_call_tool_nested(self):
        """tool 子代理 call_tool 精确嵌套 {tool_name, args} → 透传 executor 形态。"""
        spec = get_subagent_spec("tool")
        got: list[dict] = []

        async def call_tool(args=None):
            got.append(dict(args or {}))
            return {"status": "SUCCESS"}

        turns = {"v": 0}

        async def llm(messages, model):
            turns["v"] += 1
            if turns["v"] == 1:
                return json.dumps({"tool": "call_tool",
                                   "args": {"tool_name": "add", "args": {"a": 1, "b": 2}}})
            return json.dumps({"tool": None, "final": "结果 3"})

        r = _run(run_subagent(spec, objective="计算", input_text="（问题：3+4）",
                              tool_services={"call_tool": call_tool}, llm=llm))
        assert r.ok and r.tool_calls == 1
        assert got == [{"tool_name": "add", "args": {"a": 1, "b": 2}}]

    def test_schema_registry_matches_spec_tools(self):
        """白名单内每个单工具子代理的工具有登记 schema（定义/校验双侧不漂移）。"""
        for name in ("search", "memory", "learning", "tool"):
            spec = get_subagent_spec(name)
            for t in spec.tools:
                assert t in TOOL_ARG_SCHEMAS, f"{name} 白名单工具 {t} 缺 exact-pin schema 登记"


class TestVagueReject:
    """验收面②：模糊拒——fail-closed 返结构化错误，不派发。"""

    def test_missing_required_rejected_no_dispatch(self):
        """缺必填 q → EXACT_PIN_REJECTED，handler 零调用，结构化错误回灌。"""
        spec = get_subagent_spec("search")
        dispatched = {"n": 0}

        async def tool(args=None):
            dispatched["n"] += 1
            return {"docs": []}

        outputs = [
            json.dumps({"tool": "search_knowledge", "args": {}}),
            json.dumps({"tool": "search_knowledge", "args": {"q": "修正后的查询"}}),
            json.dumps({"tool": None, "final": "摘要"}),
        ]
        seen_rejects: list[str] = []
        idx = {"v": 0}

        async def llm(messages, model):
            i = idx["v"]
            idx["v"] += 1
            if i > 0:
                # 捕获回灌给 LLM 的结构化错误
                user_texts = [m["content"] for m in messages if m["role"] == "user"]
                seen_rejects.extend(t for t in user_texts if ERROR_CODE in str(t))
            return outputs[min(i, len(outputs) - 1)]

        r = _run(run_subagent(spec, objective="检索", input_text="（问题：x）",
                              tool_services={"search_knowledge": tool}, llm=llm))
        assert dispatched["n"] == 1, "模糊调用绝不能派发，修正后恰好派发一次"
        assert r.ok and r.tool_calls == 1
        assert seen_rejects and ERROR_CODE in seen_rejects[0]
        payload = json.loads(seen_rejects[0])
        assert payload["reason"].startswith("invalid_args:")
        assert "args_schema" in payload, "结构化错误必须携带 schema 提示（ACI 当 HCI）"

    def test_unknown_field_rejected(self):
        """未知字段（search_knowledge 塞 top_k）→ unknown_field 拒绝。"""
        ok, reason, detail = validate_tool_args("search_knowledge", {"q": "x", "top_k": 5})
        assert not ok and reason == "unknown_field" and "top_k" in detail

    def test_alias_field_rejected(self):
        """别名字段（recall_memory 用 query 而非 q）→ exact-pin 只认契约字段。"""
        ok, reason, _ = validate_tool_args("recall_memory", {"query": "x"})
        assert not ok and reason == "unknown_field"

    def test_wrong_type_and_domain_rejected(self):
        ok, reason, _ = validate_tool_args("call_tool", {"tool_name": 123})
        assert not ok and reason == "wrong_type"
        ok, reason, _ = validate_tool_args("recall_memory", {"q": "x", "top_k": 500})
        assert not ok and reason == "out_of_domain"
        ok, reason, _ = validate_tool_args("search_knowledge", "q=x")
        assert not ok and reason == "not_an_object"

    def test_empty_tool_name_with_final_graceful(self):
        """tool 空值但携带 final → 完成意图优雅接受（final 契约路径，非模糊调用）。"""
        spec = get_subagent_spec("search")

        async def llm(messages, model):
            return json.dumps({"tool": "", "final": "纯文本摘要"})

        r = _run(run_subagent(spec, objective="检索", input_text="（问题：x）",
                              tool_services={"search_knowledge": lambda a: None}, llm=llm))
        assert r.ok and "纯文本摘要" in r.summary

    def test_plain_text_final_accepted(self):
        """纯文本（非 JSON）终答 → final 契约优雅接受（设计内完成路径）。"""
        spec = get_subagent_spec("search")

        async def llm(messages, model):
            return "这是一段不带 JSON 的总结"

        r = _run(run_subagent(spec, objective="检索", input_text="（问题：x）",
                              tool_services={}, llm=llm))
        assert r.ok and "不带 JSON 的总结" in r.summary


class TestUnknownToolReject:
    """验收面③：未知工具拒 + fail-closed 终止。"""

    def test_unknown_tool_structured_reject(self):
        """白名单外工具 → unknown_tool 结构化错误（携 allowed_tools），不派发、可自纠错。"""
        spec = get_subagent_spec("search")
        dispatched = {"n": 0}

        async def tool(args=None):
            dispatched["n"] += 1
            return {"docs": []}

        idx = {"v": 0}

        async def llm(messages, model):
            i = idx["v"]
            idx["v"] += 1
            if i == 0:
                return json.dumps({"tool": "web_search", "args": {"q": "x"}})
            if i == 1:
                # 断言回灌错误里有 allowed_tools
                users = [m["content"] for m in messages if m["role"] == "user"]
                assert any("allowed_tools" in str(u) and "search_knowledge" in str(u) for u in users)
                return json.dumps({"tool": None, "final": "已纠正"})
            return json.dumps({"tool": None, "final": "已纠正"})

        r = _run(run_subagent(spec, objective="检索", input_text="（问题：x）",
                              tool_services={"search_knowledge": tool}, llm=llm))
        assert dispatched["n"] == 0, "未知工具绝不派发"
        assert r.ok and r.tool_calls == 0

    def test_non_string_tool_name_rejected(self):
        """tool 为非字符串（dict/list/int）→ invalid_tool_name 拒绝。"""
        spec = get_subagent_spec("search")
        idx = {"v": 0}

        async def llm(messages, model):
            i = idx["v"]
            idx["v"] += 1
            if i == 0:
                return json.dumps({"tool": {"name": "search_knowledge"}, "args": {}})
            return json.dumps({"tool": None, "final": "摘要"})

        r = _run(run_subagent(spec, objective="检索", input_text="（问题：x）",
                              tool_services={"search_knowledge": lambda a: None}, llm=llm))
        assert r.ok, "自纠错后应正常收口"

    def test_consecutive_vague_fail_closed(self):
        """连续 2 次模糊调用 → fail-closed 终止：ok=False，summary=结构化错误，不烧剩余轮次。"""
        spec = get_subagent_spec("search")
        assert spec.maxTurns > MAX_CONSECUTIVE_VAGUE_REJECTS, "前提：maxTurns 大于拒绝上限"
        llm_calls = {"n": 0}

        async def llm(messages, model):
            llm_calls["n"] += 1
            return json.dumps({"tool": "not_in_whitelist", "args": {"q": "x"}})

        r = _run(run_subagent(spec, objective="检索", input_text="（问题：x）",
                              tool_services={"search_knowledge": lambda a: None}, llm=llm))
        assert not r.ok, "fail-closed 必须 ok=False"
        assert ERROR_CODE in r.summary, "结构化错误作 summary 上交主上下文"
        assert llm_calls["n"] == MAX_CONSECUTIVE_VAGUE_REJECTS, (
            f"达上限即终止，不烧剩余轮次（实际 LLM 调用 {llm_calls['n']} 次）")
        payload = json.loads(r.summary)
        assert payload["reason"] == "unknown_tool"
        assert payload["allowed_tools"] == list(spec.tools)

    def test_streak_resets_on_success(self):
        """模糊→纠正成功→再模糊：成功重置连续计数（不误杀可自纠错会话）。"""
        spec = get_subagent_spec("tool")  # maxTurns=5，容纳 5 步序列
        dispatched = {"n": 0}

        async def call_tool(args=None):
            dispatched["n"] += 1
            return {"status": "SUCCESS"}

        outputs = [
            json.dumps({"tool": "call_tool", "args": {}}),                                      # 模糊1（缺 tool_name）
            json.dumps({"tool": "call_tool", "args": {"tool_name": "calc", "args": {}}}),       # 纠正成功（重置）
            json.dumps({"tool": "call_tool", "args": {}}),                                      # 模糊2（streak=1，不终止）
            json.dumps({"tool": "call_tool", "args": {"tool_name": "calc2", "args": {}}}),      # 再成功
            json.dumps({"tool": None, "final": "摘要"}),
        ]
        idx = {"v": 0}

        async def llm(messages, model):
            i = idx["v"]
            idx["v"] += 1
            return outputs[min(i, len(outputs) - 1)]

        r = _run(run_subagent(spec, objective="计算", input_text="（问题：x）",
                              tool_services={"call_tool": call_tool}, llm=llm))
        assert r.ok and r.tool_calls == 2 and dispatched["n"] == 2

    def test_rejections_recorded_in_artifact(self):
        """拒绝事件入 artifact（exact_pin_rejections），验收/排查有证据链。"""
        spec = get_subagent_spec("search")

        async def llm(messages, model):
            return json.dumps({"tool": "not_in_whitelist", "args": {"q": "x"}})

        r = _run(run_subagent(spec, objective="检索", input_text="（问题：x）",
                              tool_services={"search_knowledge": lambda a: None}, llm=llm))
        payload = _run(artifact_store().read(r.artifact_ref))
        assert payload is not None and payload.get("exact_pin_rejections"), "拒绝必须记账入 artifact"
        assert payload["exact_pin_rejections"][0]["error"].startswith("{"), "记账为结构化 JSON"


class TestQuestionBodyPin:
    """验收面④：q 精确绑定问题本体（R20-b 残差 18 条根因修复）。"""

    REAL_PLAN_INPUT = (
        "基于问题给出检索要点（问题：请介绍雅思听力备考的三种有效方法）\n\n"
        "[历史上下文（经 context_edit 编辑，前缀稳定（prompt cache 可命中））]\n"
        "请介绍雅思听力备考的三种有效方法"
    )

    def test_extracts_question_body_with_context_block(self):
        """plan 串含尾缀 context_edit 块 → q=问题本体（修复前=整段任务串）。"""
        args = _direct_tool_args("search", self.REAL_PLAN_INPUT)
        assert args == {"q": "请介绍雅思听力备考的三种有效方法"}

    def test_extracts_with_skill_block_first(self):
        args = _direct_tool_args("search",
                                 "基于问题给出检索要点（问题：计算 5 加 12 请给出结果）\n\n"
                                 "[相关 skill 指引，请遵循]\nxx\n\n[历史上下文]\nyy")
        assert args == {"q": "计算 5 加 12 请给出结果"}

    def test_question_with_parens(self):
        args = _direct_tool_args("search",
                                 "模板（问题：什么是检索增强生成（RAG）技术？）\n\n[历史上下文]")
        assert args == {"q": "什么是检索增强生成（RAG）技术？"}

    def test_legacy_tail_form(self):
        args = _direct_tool_args("search", "基于问题给出检索要点（问题：你好）")
        assert args == {"q": "你好"}

    def test_no_marker_fallback_whole_input(self):
        """无标记 → 整段兜底（行为下限不劣于修复前）。"""
        args = _direct_tool_args("search", "没有标记的输入")
        assert args == {"q": "没有标记的输入"}

    def test_learning_uses_profile_query(self):
        args = _direct_tool_args("learning", self.REAL_PLAN_INPUT)
        assert args == {"profile_query": "请介绍雅思听力备考的三种有效方法"}

    def test_prefetch_args_pass_schema(self):
        """确定性预执行参数必须过 exact-pin schema（含真实 plan 串形态）。"""
        for sub, tool in (("search", "search_knowledge"), ("memory", "recall_memory"),
                          ("learning", "recall_profile")):
            args = _direct_tool_args(sub, self.REAL_PLAN_INPUT)
            ok, reason, detail = validate_tool_args(tool, args)
            assert ok, f"{sub} 预执行参数未过 schema: {reason}: {detail}"

    def test_parse_action_contract(self):
        """解析与校验分离：围栏 JSON / 纯文本 / 破损 JSON 三态。"""
        assert _parse_action('```json\n{"tool": "search_knowledge", "args": {"q": "x"}}\n```') == {
            "tool": "search_knowledge", "args": {"q": "x"}}
        assert _parse_action("普通文本") == {"tool": None, "final": "普通文本"}
        broken = _parse_action("{broken json")
        assert broken["tool"] is None and "final" in broken
