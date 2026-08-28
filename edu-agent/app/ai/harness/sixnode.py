# -*- coding: utf-8 -*-
"""task-A1 默认 Harness 实现：SixNodeHarness（= task24 现有 6 节点 DAG，行为零变化）。

实现方式（A1-② 真搬迁）：route / plan / fan_out / merge / reflect / answer 六节点的**真实编排逻辑**
全部迁入 SixNodeHarness 方法；graph.py 的对应模块级函数（route_node / plan_node / fan_out_node /
merge_node / reflect_node / answer_node）退化为「委托当前默认 harness 实例」的薄壳，仅保留模块级
函数名以兼容下列契约：
  - test_contract_task24：monkeypatch graph.answer_node 等后再 build_graph（红线）；
  - test_contract_task94 / test_contract_task97：直接调用 graph.plan_node / answer_node 等。

共享原语（_llm_call / _record / _extract_json / _effort_for_intent / _edited_context_block /
_build_tool_services / 常量 / 提示词 / run_subagents）仍由 app.ai.graph 提供；本实现通过 ``_graph.<name>``
调用时动态查表，确保对 graph 模块的 monkeypatch（_llm_call / run_subagents / answer_node /
skill_node / compact_node / context_edit_node）继续生效——这是行为零变化的关键。

对齐 task29 R8 keep_sixnode 裁定：默认实现 = 原 6 节点 DAG，开放接口不改变默认行为。
"""
from __future__ import annotations

import time

from langchain_core.messages import HumanMessage
from loguru import logger

from app.ai.graph import AgentState
from app.ai import graph as _graph
from app.ai.subagents import SubagentResult, SubagentTask
from app.config import settings
from app.ai.harness.base import Harness


class SixNodeHarness(Harness):
    """默认实现：原 6 节点 DAG 的真实编排逻辑（A1-② 由 graph.py 迁入，行为逐字节一致）。"""

    async def route(self, state: AgentState) -> dict:
        query = ""
        for m in state.get("messages", []):
            if isinstance(m, HumanMessage):
                query = str(m.content)
        intent = "knowledge"  # 兜底默认
        messages = [
            {"role": "system", "content": _graph.ROUTE_SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]
        # 鲁棒性：fast 模型偶发返回空串/不可解析，重试避免空输出被错误兜底 knowledge
        for _ in range(3):
            try:
                raw = await _graph._llm_call(messages, model="fast", max_tokens=30)
                obj = _graph._extract_json(raw) or {}
                cand = str(obj.get("intent") or "").strip().lower()
                if cand in _graph._FAST_INTENTS:
                    intent = cand
                    break
            except Exception as exc:
                logger.warning(f"[sixnode.route] 意图路由重试，当前默认 knowledge: {type(exc).__name__}: {exc}")
        # 诚实 effort：chitchat 走 route→answer 直连，定档 L0；其余由 plan 按意图定档 L1/L2
        effort = "L0" if intent == "chitchat" else "L1"
        return {"intent": intent, "effort": effort} | _graph._record(state, "route")

    async def plan(self, state: AgentState) -> dict:
        intent = state.get("intent", "knowledge")
        level, tasks = _graph._effort_for_intent(intent)
        query = ""
        for m in state.get("messages", []):
            if isinstance(m, HumanMessage):
                query = str(m.content)
        # task94 GWT③：消费 skill_node 注入的 skill_context，使命中 skill 的 body 指引进入子代理任务
        skill_context = state.get("skill_context") or ""
        # task97(task#25)：消费 context_edit_node 输出的已编辑上下文（闭合 task96 批判②）
        ctx_block = ""
        prefix_stable = None
        edited = state.get("context_edit") or {}
        if isinstance(edited, dict):
            ctx_block = _graph._edited_context_block(edited)
            prefix_stable = edited.get("prefix_stable")
        plan_tasks = []
        for t in tasks:
            inp = t["input"] + f"（问题：{query}）"
            if skill_context:
                inp = inp + f"\n\n[相关 skill 指引，请遵循]\n{skill_context}"
            if ctx_block:
                if prefix_stable is True:
                    flag = "前缀稳定（prompt cache 可命中）"
                elif prefix_stable is False:
                    flag = "前缀已变（prompt cache 将失效）"
                else:
                    flag = "前缀未定"
                inp = inp + f"\n\n[历史上下文（经 context_edit 编辑，{flag}）]\n{ctx_block}"
            plan_tasks.append({"subagent": t["subagent"], "objective": t["objective"], "input": inp})
        return {"tasks": plan_tasks, "effort": level} | _graph._record(state, "plan")

    async def fan_out(self, state: AgentState) -> dict:
        tasks = state.get("tasks", [])
        # user_id 由 service 注入（_empty_state），禁止兜底默认 1（R4 安全红线：缺失即报错而非降级越权）
        user_id = int(state["user_id"])
        thread_id = state.get("session_id") or None

        services = _graph._build_tool_services(user_id=user_id, thread_id=thread_id)
        sub_tasks: list[SubagentTask] = []
        for t in tasks:
            sub_tasks.append(
                SubagentTask(
                    subagent=t.get("subagent", "search"),
                    objective=t.get("objective", ""),
                    input=t.get("input", ""),
                    tool_services=services,
                    user_id=user_id,
                    thread_id=thread_id,
                )
            )

        # fan-out：task92 runner 内 asyncio.gather 并行，独立上下文；主 state 只收蒸馏摘要
        t0 = time.perf_counter()
        results: list[SubagentResult] = await _graph.run_subagents(sub_tasks)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(f"[sixnode.fanout] 并行 {len(sub_tasks)} 个子代理完成，耗时 {elapsed_ms}ms")

        distilled = [r.as_distilled() for r in results]
        return {"subagent_results": distilled, "degraded_reason": None} | _graph._record(state, "fan_out")

    async def merge(self, state: AgentState) -> dict:
        distilled = state.get("subagent_results", [])
        merged = []
        seen: set[str] = set()
        for r in distilled:
            summary = (r.get("summary") or "").strip()
            if not summary:
                continue
            key = summary[:40]
            if key in seen:            # 去重
                continue
            seen.add(key)
            merged.append(f"- [{r.get('subagent')}] {summary}")
        context = "\n".join(merged) or "（子代理未产出有效摘要）"
        return {"merged_context": context} | _graph._record(state, "merge")

    async def reflect(self, state: AgentState) -> dict:
        reflect_count = int(state.get("reflect_count", 0))
        context = state.get("merged_context", "")
        # 达到迭代上限 → 强制放行（answer 时标 degraded_reason="reflect_max_iter"），不无限循环
        if reflect_count >= _graph.MAX_REFLECT_ITERATIONS:
            return {"reflect_count": reflect_count + 1, "sufficient": True,
                    "degraded_reason": "reflect_max_iter"} | _graph._record(state, "reflect")
        sufficient = True
        try:
            messages = [
                {"role": "system", "content": _graph.REFLECT_SYSTEM_PROMPT},
                {"role": "user", "content": f"综合上下文：\n{context}\n\n判断是否足够。若关键信息缺失需再检索，输出 sufficient=false。"},
            ]
            raw = await _graph._llm_call(messages, model="fast", max_tokens=20)
            obj = _graph._extract_json(raw) or {}
            sufficient = bool(obj.get("sufficient", True))
        except Exception:
            sufficient = True  # judge 失败保守放行
        return {"reflect_count": reflect_count + 1, "sufficient": sufficient,
                "degraded_reason": None} | _graph._record(state, "reflect")

    async def answer(self, state: AgentState) -> dict:
        query = ""
        for m in state.get("messages", []):
            if isinstance(m, HumanMessage):
                query = str(m.content)
        context = state.get("merged_context", "")
        skill_context = state.get("skill_context") or ""

        system_content = _graph.ANSWER_SYSTEM_PROMPT + "\n\n## 综合上下文\n" + (context or "（无）")
        # task94 GWT③：skill_context 进入最终回答上下文（命中 skill 的 body 指引被决策链消费）
        if skill_context:
            system_content += "\n\n## 相关 skill 指引\n" + skill_context

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": query},
        ]
        try:
            answer = await _graph._llm_call(messages, model="strong", temperature=settings.LLM_TEMPERATURE, max_tokens=settings.LLM_MAX_TOKENS)
        except Exception as exc:
            logger.warning(f"[sixnode.answer] strong 生成失败，降级 fast: {type(exc).__name__}: {exc}")
            try:
                answer = await _graph._llm_call(messages, model="fast", temperature=settings.LLM_TEMPERATURE, max_tokens=settings.LLM_MAX_TOKENS)
            except Exception as exc2:
                answer = f"抱歉，AI 服务暂时不可用（{type(exc2).__name__}），请稍后重试。"
                return {"final_answer": answer, "degraded_reason": "llm_failed"} | _graph._record(state, "answer")
        return {"final_answer": answer, "degraded_reason": None} | _graph._record(state, "answer")
