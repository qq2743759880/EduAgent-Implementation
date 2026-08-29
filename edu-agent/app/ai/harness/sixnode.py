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

    # task-P1L 优化C：route / reflect judge 的 system prompt 均为纯静态常量 → ensure_min_prefix
    # 撑到 ≥2048 token（跨请求/跨用户字节一致），火山 ark prompt cache 命中（实测 2048 分块），
    # 降低主链路调用延迟。结果确定性（CACHE_FILLER_BLOCK 逐字节稳定），模块级缓存避免每请求重复填充。
    _route_system_prefix: str | None = None
    _reflect_system_prefix: str | None = None

    @classmethod
    def _route_prefix(cls) -> str:
        if cls._route_system_prefix is None:
            from app.ai.prompt_cache import ensure_min_prefix

            cls._route_system_prefix = ensure_min_prefix(_graph.ROUTE_SYSTEM_PROMPT)
        return cls._route_system_prefix

    @classmethod
    def _reflect_prefix(cls) -> str:
        if cls._reflect_system_prefix is None:
            from app.ai.prompt_cache import ensure_min_prefix

            cls._reflect_system_prefix = ensure_min_prefix(_graph.REFLECT_SYSTEM_PROMPT)
        return cls._reflect_system_prefix

    async def route(self, state: AgentState) -> dict:
        query = ""
        for m in state.get("messages", []):
            if isinstance(m, HumanMessage):
                query = str(m.content)
        # task-P1L 优化H1：规则路由先行（0-LLM 决策，对齐 Anthropic Building Effective Agents——
        # 高频确定性意图用 workflow（正则）分流，LLM 仅兜底开放场景）。
        # 命中（learning/tool/chitchat/knowledge 覆盖语料）→ 0 次 LLM 定档，主链路第 1 次串行
        # 调用直接省掉（task39 实测单次 1.4~5.0s，白天 7~13s）；未覆盖样本 → 默认 knowledge 0-LLM 兜底。
        # 仅当 RULE_ROUTING_ENABLED=False 才回退 LLM 路由（契约测试/异常回退开关）。
        if getattr(settings, "RULE_ROUTING_ENABLED", True):
            from app.ai.rule_router import classify_intent

            rule_intent = classify_intent(query)
            intent = rule_intent if rule_intent is not None else "knowledge"
            effort = "L0" if intent == "chitchat" else "L1"
            logger.info(
                f"[sixnode.route] 规则路由命中（0-LLM）: intent={intent}, effort={effort}"
                f"{'（未覆盖→knowledge 兜底）' if rule_intent is None else ''}"
            )
            return {"intent": intent, "effort": effort} | _graph._record(state, "route")

        intent = "knowledge"  # 兜底默认
        messages = [
            {"role": "system", "content": self._route_prefix()},
            {"role": "user", "content": query},
        ]
        # 鲁棒性（task-P1L 优化A）：fast 模型偶发返回空串/不可解析 → 重试 1 次（共 2 次）；
        # LLM 异常 → **立即降级 knowledge 不再重试**。原 for _ in range(3) 在 LLM 抖动/宕机时
        # 3 连败 = 3 倍串行延迟，route 是主链路第 1 次调用，直接拖爆 P95（task39 实测 25~32s 根因之一）。
        attempts = 2
        for i in range(attempts):
            try:
                raw = await _graph._llm_call(messages, model="fast", max_tokens=30)
                obj = _graph._extract_json(raw) or {}
                cand = str(obj.get("intent") or "").strip().lower()
                if cand in _graph._FAST_INTENTS:
                    intent = cand
                    break
            except Exception as exc:
                logger.warning(
                    f"[sixnode.route] 意图路由 LLM 异常（第 {i + 1}/{attempts} 次）→ 立即降级 knowledge: "
                    f"{type(exc).__name__}: {exc}"
                )
                break
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

        # task-P1L 优化H2：knowledge 直连检索快路径（0 子代理 LLM）。
        # knowledge 意图的 2 个子代理（search/memory）都只依赖确定性工具 → 在 fan_out 层直接执行：
        #   search = 三通道检索（同 search_knowledge 工具参数，role=None 对齐 _build_tool_services），
        #   memory = recall_topk 确定性召回；
        # 主链路 L1 从「route(1)+子代理(4)+judge(1)+answer(1)」降为「answer(1)」单次 LLM。
        # 任何异常 → 回退原 run_subagents 路径（行为不降级）。
        intent = state.get("intent", "")
        if getattr(settings, "KNOWLEDGE_DIRECT_RETRIEVAL_ENABLED", True) and intent == "knowledge":
            try:
                from app.ai.subagents import runner as _runner
                from app.chat.retriever import retrieve_three_channel

                query = ""
                for m in state.get("messages", []):
                    if isinstance(m, HumanMessage):
                        query = str(m.content)
                t0 = time.perf_counter()
                bundle = await retrieve_three_channel(
                    query, user_id=user_id, role=None,
                    use_hyde=False, enable_graph=True,
                    top_k=8, final_max_k=5, cutoff_drop_ratio=0.2,
                )
                # search 摘要：每文档一行（来源 + 内容片段），token 预算与子代理一致
                parts = []
                for i, d in enumerate(bundle.docs, 1):
                    snippet = (d.content or "").replace("\n", " ").strip()[:120]
                    src = (d.source_file or "") or d.doc_id or "未知来源"
                    parts.append(f"[{i}]（来源 {src}）{snippet}")
                search_summary = _runner._clamp_summary(
                    "\n".join(parts) or "（未检索到相关文档）",
                    budget=settings.SUBAGENT_SUMMARY_BUDGET,
                )
                # memory 直连：无 LLM 的确定性召回
                memory_summary = "（无历史记忆）"
                memory_calls = 0
                try:
                    from app.ai.memory.service import recall_topk

                    top = await recall_topk(int(user_id), query, top_k=3)
                    mem_texts = []
                    for m in (top or []):
                        if isinstance(m, dict):
                            val = m.get("content") or m.get("text") or m.get("memory")
                            if val is None:
                                val = str(m)
                        else:
                            val = str(m)
                        if val:
                            mem_texts.append(str(val).replace("\n", " ").strip()[:100])
                    if mem_texts:
                        memory_summary = "用户记忆：" + "；".join(mem_texts)
                        memory_calls = 1
                except Exception as exc:
                    logger.warning(f"[sixnode.fanout] memory 直连召回失败（降级占位）: {type(exc).__name__}: {exc}")
                results = [
                    _runner.SubagentResult(
                        subagent="search", summary=search_summary, artifact_ref="",
                        ok=True, turns=0, tool_calls=1,
                        summary_tokens=_runner._token_approx(search_summary),
                    ),
                    _runner.SubagentResult(
                        subagent="memory", summary=memory_summary, artifact_ref="",
                        ok=True, turns=0, tool_calls=memory_calls,
                        summary_tokens=_runner._token_approx(memory_summary),
                    ),
                ]
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                logger.info(f"[sixnode.fanout] knowledge 直连检索快路径（0 子代理 LLM）完成，耗时 {elapsed_ms}ms，docs={len(bundle.docs)}")
                distilled = [r.as_distilled() for r in results]
                return {"subagent_results": distilled, "degraded_reason": None} | _graph._record(state, "fan_out")
            except Exception as exc:
                logger.warning(f"[sixnode.fanout] knowledge 直连检索失败 → 回退子代理路径: {type(exc).__name__}: {exc}")

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
        # task-P1L 优化B：启发式先行 —— 所有子代理均产出非空摘要且综合上下文非空 →
        # 直接 sufficient=true，**跳过 judge LLM 调用**（主链路省 1 次串行调用，task39 实测
        # 单次调用 1.4~5.0s，P95 直接受益）。仅当上下文明显不足（有子代理空摘要/兜底占位）时
        # 才走 LLM judge 二次确认（judge 返回 false 仍可回 plan 补检索，保留质量兜底）。
        distilled = state.get("subagent_results", [])
        all_have_summary = bool(distilled) and all((r.get("summary") or "").strip() for r in distilled)
        context_ready = bool((context or "").strip()) and context.strip() != "（子代理未产出有效摘要）"
        if all_have_summary and context_ready:
            return {"reflect_count": reflect_count + 1, "sufficient": True,
                    "degraded_reason": None} | _graph._record(state, "reflect")
        sufficient = True
        try:
            messages = [
                {"role": "system", "content": self._reflect_prefix()},
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
