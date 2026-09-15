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

import asyncio
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
                # R02 检索参数对齐（R20-b 根因修复）：原硬编码 use_hyde=False/top_k=8 与旧路径
                # 生产默认 use_hyde=True/top_k=12 漂移 → docs Jaccard 0.641。现由
                # sixnode_retrieval_params() 从 settings 读取（默认对齐 retrieve_three_channel 现值）。
                params = _graph.sixnode_retrieval_params()
                # R02-tail：memory 召回与三通道检索并行（两者输入独立：query/user_id，
                # 产物独立：search_summary / memory_summary）——原串行实现下 recall_topk 的
                # 嵌入+向量库查询全额叠加在检索之后（profile 实测 warm 80~120ms，冷态 600~1200ms）。
                # 并行不改变任一侧的调用参数与产出 → 检索/记忆语义零变化。
                async def _memory_direct() -> tuple[str, int]:
                    """memory 直连召回（与原串行块同语义：失败→占位+warning，恒返回元组）。

                    R01：注入文本走 memory.service 序号映射（[M1]…，真实 memory_id 不进
                    prompt，附「只能引用列出序号」指令——mem0 同款防幻觉）。
                    """
                    memory_summary_ = "（无历史记忆）"
                    memory_calls_ = 0
                    try:
                        from app.ai.memory.service import recall_topk, format_memories_for_prompt

                        top = await recall_topk(int(user_id), query, top_k=3)
                        mapped_text, _ref_map = format_memories_for_prompt(top or [])
                        if mapped_text:
                            memory_summary_ = mapped_text
                            memory_calls_ = 1
                    except Exception as exc:
                        logger.warning(f"[sixnode.fanout] memory 直连召回失败（降级占位）: {type(exc).__name__}: {exc}")
                    return memory_summary_, memory_calls_

                _t_mem = time.perf_counter()
                mem_task = asyncio.ensure_future(_memory_direct())
                _t_ret = time.perf_counter()
                bundle = await retrieve_three_channel(
                    query, user_id=user_id, role=None,
                    use_hyde=params["use_hyde"], enable_graph=params["enable_graph"],
                    top_k=params["top_k"], final_max_k=params["final_max_k"],
                    cutoff_drop_ratio=params["cutoff_drop_ratio"],
                )
                _retrieval_ms = int((time.perf_counter() - _t_ret) * 1000)
                try:
                    memory_summary, memory_calls = await mem_task
                except Exception as exc:  # noqa: BLE001 — 任务级异常同样降级占位（与原串行语义一致）
                    logger.warning(f"[sixnode.fanout] memory 召回任务异常（降级占位）: {type(exc).__name__}: {exc}")
                    memory_summary, memory_calls = "（无历史记忆）", 0
                _memory_ms = int((time.perf_counter() - _t_mem) * 1000)
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
                # R02-tail profile：直连快路径内部分段。R02-tail 起 memory 与 retrieval 并行
                # （mem_par_await 为重叠收口窗口，不叠加在关键路径上），summary=总-retrieval。
                logger.info(
                    "[sixnode.fanout-profile] total={}ms retrieval={:.0f}ms mem_par_await={:.0f}ms "
                    "summary={:.0f}ms docs={}".format(
                        elapsed_ms, (_retrieval_ms or 0), (_memory_ms or 0),
                        max(0, (time.perf_counter() - t0) * 1000 - (_retrieval_ms or 0)),
                        len(bundle.docs))
                )
                logger.info(f"[sixnode.fanout] knowledge 直连检索快路径（0 子代理 LLM）完成，耗时 {elapsed_ms}ms，docs={len(bundle.docs)}")
                distilled = [r.as_distilled() for r in results]
                # R02（audit P1-5 回填）：真实检索产物写入 state.retrieval，供 run_agent 返回体
                # 回填与流式适配层 retrieval 帧消费（纯 dict/list，checkpoint pickle 安全）。
                return {
                    "subagent_results": distilled,
                    "degraded_reason": None,
                    "retrieval": {
                        "docs": [d.model_dump() for d in bundle.docs],
                        "graph_entities": [g.model_dump() for g in bundle.graph_entities],
                        "retrieved_count": int(bundle.raw_retrieved_count or 0),
                        "rewrite_query": bundle.rewrite_query,
                        "degraded_reason": bundle.degraded_reason,
                    },
                } | _graph._record(state, "fan_out")
            except Exception as exc:
                logger.warning(f"[sixnode.fanout] knowledge 直连检索失败 → 回退子代理路径: {type(exc).__name__}: {exc}")

        # 子代理路径：capture 闭包捕获 search_knowledge 真实检索产物（P1-5 回填）
        capture: dict = {}
        services = _graph._build_tool_services(user_id=user_id, thread_id=thread_id, capture=capture)
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
        # R02（P1-5 回填）：子代理路径经 capture 取 search_knowledge 真实产物（未触发检索则空）
        cap_ret = capture.get("retrieval") if isinstance(capture.get("retrieval"), dict) else {}
        return {
            "subagent_results": distilled,
            "degraded_reason": None,
            "retrieval": {
                "docs": list(cap_ret.get("docs") or []),
                "graph_entities": list(cap_ret.get("graph_entities") or []),
                "retrieved_count": int(cap_ret.get("retrieved_count") or 0),
                "rewrite_query": cap_ret.get("rewrite_query"),
                "degraded_reason": cap_ret.get("degraded_reason"),
            },
        } | _graph._record(state, "fan_out")

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

        # R02：流式吐 token 分支——仅当上层适配层经 configurable.stream_tokens=True 显式请求
        # 且全局开关 GRAPH_ANSWER_STREAMING 开启时启用。普通 run_agent/ainvoke 不带该键，
        # 走下方原阻塞路径（行为逐字节一致，零变化）。
        if self._stream_tokens_requested():
            writer = None
            try:
                from langgraph.config import get_stream_writer

                writer = get_stream_writer()
            except Exception:
                writer = None
            if writer is not None:
                try:
                    answer = await self._stream_answer_tokens(messages, writer)
                    return {"final_answer": answer, "degraded_reason": None} | _graph._record(state, "answer")
                except Exception as exc:
                    # 流式已吐部分 token → 不重试（防重复输出），异常上抛由适配层转 error 事件
                    if getattr(exc, "stream_tokens_emitted", False):
                        raise
                    logger.warning(
                        f"[sixnode.answer] 流式生成失败（未吐 token，回退阻塞 strong→fast）: {type(exc).__name__}: {exc}"
                    )
                    # 落到下方阻塞降级链（strong 失败语义与原实现一致）

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

    # ──────────────────────────────────────────────
    # R02：answer 流式支原语（门控判定 + token 桥接）
    # ──────────────────────────────────────────────
    @staticmethod
    def _stream_tokens_requested() -> bool:
        """是否处于「流式吐 token」请求上下文（适配层经 configurable.stream_tokens 门控）。"""
        if not getattr(settings, "GRAPH_ANSWER_STREAMING", True):
            return False
        try:
            from langgraph.config import get_config

            cfg = get_config()
            return bool((cfg.get("configurable") or {}).get("stream_tokens"))
        except Exception:
            return False

    @staticmethod
    async def _stream_answer_tokens(messages: list[dict], writer) -> str:
        """strong 模型流式生成：token 增量经 LangGraph custom stream writer 推给适配层（SSE token 帧）。

        - 阻塞生成器 → 线程池 queue 桥接（与 generator.generate_stream 同构，60s 无增量超时）；
        - 复用 call_chat_stream_with_retry：未吐 token 前按错误类型重试 + FAST↔STRONG 互切；
        - 已吐 token 后失败 → 标记 stream_tokens_emitted 后上抛（不静默、不重复输出）；
        - 异常统一 record_degraded("llm")（对齐 graph._llm_call 口径）。
        """
        import asyncio as _asyncio
        import queue as _queue
        import threading as _threading

        from app.chat.generator import _ChatClient

        client = _ChatClient.get()
        loop = _asyncio.get_running_loop()
        q: _queue.Queue = _queue.Queue()

        def _worker():
            try:
                for tok in client.call_chat_stream_with_retry(
                    messages=messages,
                    model="strong",
                    temperature=settings.LLM_TEMPERATURE,
                    max_tokens=settings.LLM_MAX_TOKENS,
                ):
                    q.put(tok)
                q.put(None)
            except BaseException as e:  # noqa: BLE001 — 桥接线程把异常原样带回事件循环
                q.put(e)

        _threading.Thread(target=_worker, daemon=True).start()

        emitted = False
        parts: list[str] = []
        while True:
            try:
                item = await loop.run_in_executor(None, q.get, True, 60.0)
            except _queue.Empty:
                exc = TimeoutError("LLM stream 60s 无增量，超时降级")
                if emitted:
                    exc.stream_tokens_emitted = True  # type: ignore[attr-defined]
                try:
                    from app.monitoring.metrics import record_degraded
                    record_degraded("llm", f"sixnode_answer_stream:{type(exc).__name__}")
                except Exception:  # noqa: BLE001
                    pass
                raise exc
            if item is None:
                return "".join(parts)
            if isinstance(item, BaseException):
                if emitted:
                    item.stream_tokens_emitted = True  # type: ignore[attr-defined]
                try:
                    from app.monitoring.metrics import record_degraded
                    record_degraded("llm", f"sixnode_answer_stream:{type(item).__name__}")
                except Exception:  # noqa: BLE001
                    pass
                raise item
            emitted = True
            parts.append(str(item))
            writer({"type": "token", "delta": str(item)})
