# -*- coding: utf-8 -*-
"""task92 契约测试：R1 子代理独立上下文（GWT ①②③）。

执行方式：in-process + fake LLM + fake tool（不连真实 LLM/MCP），验证上下文隔离语义。

GWT：
① Given 2 个并行子代理，When 执行，Then 各自独立上下文（非共享 state），主 state 仅收 ≤ budget 蒸馏摘要
② Given 子代理检索 100 文档，When 完成，Then 原文在 artifact、主上下文只含摘要
③ Given 子代理崩溃，When 重试/并行，Then 不污染主上下文（独立会话隔离）
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.ai.subagents import (
    get_subagent_spec,
    run_subagent,
    run_subagents,
    artifact_store,
    SubagentTask,
)


def _run(coro):
    return asyncio.run(coro)


def make_llm_factory():
    """返回 (llm, seen)——llm 首轮发工具调用、次轮发 final；seen 记录每次收到的 messages（供隔离断言）。"""
    def factory(tag: str, final_text: str):
        seen: list[list[dict]] = []
        n = {"v": 0}

        async def llm(messages, model):
            seen.append([dict(m) for m in messages])   # 深拷贝当前会话 messages
            n["v"] += 1
            if n["v"] == 1:
                return json.dumps({"tool": "search_knowledge", "args": {"q": tag}})
            return json.dumps({"tool": None, "final": final_text})
        return llm, seen
    return factory


class TestSubagentIndependence:
    def test_parallel_isolated_context(self):
        """GWT①：2 并行子代理各自独立上下文（A 的工具输出不进入 B），主 state 只收摘要。"""
        factory = make_llm_factory()

        async def go():
            # 每个子代理独立 llm + 独立 tool 服务，返回各自专属 marker
            llmA, seenA = factory("SUB_A", "A 的摘要")
            llmB, seenB = factory("SUB_B", "B 的摘要")

            async def toolA(args=None):
                return {"docs": [{"id": 1, "content": "A_ONLY_MARKER"}]}

            async def toolB(args=None):
                return {"docs": [{"id": 2, "content": "B_ONLY_MARKER"}]}

            tasks = [
                SubagentTask(subagent="search", objective="目标A", input="问题A",
                             tool_services={"search_knowledge": toolA}, llm=llmA),
                SubagentTask(subagent="search", objective="目标B", input="问题B",
                             tool_services={"search_knowledge": toolB}, llm=llmB),
            ]
            res = await run_subagents(tasks)
            # 主 state 只应收蒸馏摘要，不含原文
            distilled = [r.as_distilled() for r in res]
            return res, distilled, seenA, seenB

        res, distilled, seenA, seenB = _run(go())
        assert len(res) == 2
        # 各自 ok 且摘要 ≤ 预算
        for r in res:
            assert r.ok
            assert r.summary_tokens <= 2000, f"摘要超预算 {r.summary_tokens}"
        # 主 state 载荷只有 subagent/summary/artifact_ref（无检索原文）
        assert set(distilled[0].keys()) == {"subagent", "summary", "artifact_ref", "summary_tokens"}
        # 上下文隔离：第二轮 messages（含工具结果）只含各自 marker
        textA = json.dumps(seenA[-1], ensure_ascii=False)
        textB = json.dumps(seenB[-1], ensure_ascii=False)
        assert "A_ONLY_MARKER" in textA and "B_ONLY_MARKER" not in textA, "A 上下文被 B 污染"
        assert "B_ONLY_MARKER" in textB and "A_ONLY_MARKER" not in textB, "B 上下文被 A 污染"

    def test_distilled_no_raw(self):
        """主上下文载荷不含工具原文，原文只进 artifact。"""
        spec = get_subagent_spec("search")

        async def llm(messages, model):
            return json.dumps({"tool": None, "final": "STABLE_SUMMARY"})

        async def go():
            r = await run_subagent(spec, objective="目标", input_text="问题",
                                   tool_services={}, llm=llm)
            return r

        r = _run(go())
        assert r.summary == "STABLE_SUMMARY"
        # artifact 读到完整 payload（messages 含 system + user + final）
        payload = _run(artifact_store().read(r.artifact_ref))
        assert payload["subagent"] == "search"
        assert payload["messages"][0]["role"] == "system"
        d = r.as_distilled()
        assert "STABLE_SUMMARY" in d["summary"] and "artifact_ref" in d


class TestSubagentArtifact:
    def test_100_docs_stay_in_artifact(self):
        """GWT②：检索 100 文档 → 原文在 artifact，主上下文摘要 ≤ 预算。"""
        spec = get_subagent_spec("search")

        def make_llm(final_text):
            n = {"v": 0}

            async def llm(messages, model):
                n["v"] += 1
                if n["v"] == 1:
                    return json.dumps({"tool": "search_knowledge", "args": {"q": "queries"}, })
                return json.dumps({"tool": None, "final": final_text})
            return llm

        llm = make_llm("命中主题X，3/100 强相关，结论……")

        async def go():
            docs = [{"i": i, "content": f"第{i}篇文档内容" + "x" * 200} for i in range(100)]  # ~21k 字

            async def tool(args=None):
                return {"docs": docs}

            r = await run_subagent(spec, objective="检索目标", input_text="查询",
                                   tool_services={"search_knowledge": tool}, llm=llm)
            return r, docs

        r, docs = _run(go())
        # 主上下文摘要受限
        assert r.summary_tokens <= 2000
        assert "x" * 200 not in r.summary, "主上下文不应含 100 篇原文"
        # 原文在 artifact
        payload = _run(artifact_store().read(r.artifact_ref))
        assert payload is not None
        blob = json.dumps(payload, ensure_ascii=False)
        assert len(docs) == 100
        assert f'"i": 99' in blob or '"i":99' in blob, "artifact 应含第100篇"


class TestSubagentCrashIsolation:
    def test_crash_retry_no_pollution(self):
        """GWT③：子代理崩溃重试不污染主上下文；并行健康子代理不受影响。"""
        factory = make_llm_factory()
        spec = get_subagent_spec("search")

        async def boom_llm(messages, model):
            raise RuntimeError("子代理 LLM 崩溃")

        async def go():
            # 崩溃子代理（连试失败 → ok=False，摘要回退到目标，不污染主上下文）
            rA = await run_subagent(spec, objective="崩溃目标", input_text="q",
                                    tool_services={}, llm=boom_llm)
            # 并行健康子代理
            llmB, _ = factory("B", "B OK")
            rB = await run_subagent(spec, objective="健康目标", input_text="q",
                                    tool_services={}, llm=llmB)
            # 崩溃重试：再次运行，仍独立起新会话，不累积崩溃痕迹到共享 state
            rA2 = await run_subagent(spec, objective="崩溃目标2", input_text="q2",
                                     tool_services={}, llm=boom_llm)
            # 模拟主 state 只合并摘要
            main_state = {"subagents": [rA.as_distilled(), rB.as_distilled(), rA2.as_distilled()]}
            return rA, rB, rA2, main_state

        rA, rB, rA2, main_state = _run(go())
        # 崩溃子代理：ok=False，turns=1（重试 2 次后放弃），摘要回退 = 目标（不泄露崩溃堆栈）
        assert not rA.ok and rA.turns == 1
        assert "崩溃" in rA.summary or rA.summary == ""  # 摘要无关崩溃内部
        # 健康子代理不受影响
        assert rB.ok and "B OK" in rB.summary
        # 重试同样干净失败，随后独立不积累
        assert not rA2.ok
        # 主 state 载荷不包含内部异常文本
        main_blob = json.dumps(main_state, ensure_ascii=False)
        assert "RuntimeError" not in main_blob and "崩溃" not in str(rB.summary)

    def test_unknown_subagent_and_batch_isolation(self):
        """加固：未知子代理名不抛异常（ok=False）；单子代理失败不取消整批。"""
        factory = make_llm_factory()
        llmOK, _ = factory("OK", "健康摘要")

        async def boom_llm(messages, model):
            raise RuntimeError("工具层崩溃")

        async def go():
            tasks = [
                SubagentTask(subagent="does_not_exist", objective="未知", input=""),
                SubagentTask(subagent="search", objective="健康", input="q",
                             tool_services={}, llm=llmOK),
                SubagentTask(subagent="tool", objective="崩溃", input="q",
                             tool_services={}, llm=boom_llm),
            ]
            return await run_subagents(tasks)

        res = _run(go())
        assert len(res) == 3
        # 未知子代理 → ok=False 摘要含提示，不抛
        assert res[0].subagent == "does_not_exist" and not res[0].ok
        assert "未知子代理" in res[0].summary
        # 健康子代理不受整批拖累
        assert res[1].ok and "健康摘要" in res[1].summary
        # 崩溃子代理 ok=False，且不污染他人
        assert not res[2].ok

    def test_summary_clamped_to_budget(self):
        """摘要超过预算时被裁剪到 ≤ budget。"""
        from app.ai.subagents.runner import _clamp_summary
        long_text = "学" * 6000  # 6000 CJK ≈ 6000 token > budget
        clamped = _clamp_summary(long_text, 500)
        from app.ai.subagents.runner import _token_approx
        assert _token_approx(clamped) <= 500, _token_approx(clamped)