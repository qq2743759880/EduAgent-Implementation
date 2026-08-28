"""
task24：AI 助手 LangGraph 图重构（route→plan→fan-out→merge→reflect→answer）。

设计依据（.opencode/plans/tech-source-audit.md §二）：
- LangGraph 1.2 保留升级 + AsyncRedisSaver 做 durable execution（Redis checkpoint）。
- orchestrator-worker 多 agent：plan_node 产出子代理任务清单 → fan-out 用 task92 runner
  （run_subagents，独立上下文 + asyncio.gather 并行）→ merge → reflect → answer。
- effort scaling 四档（对齐 Anthropic 官方数字：L0 直答 / L1 2-4 / L2 5-8 / L3 10+ 调用）。
- 子代理结果只回蒸馏摘要（≤ SUBAGENT_SUMMARY_BUDGET token）+ artifact 引用，原文落 Redis artifact。

图拓扑：
  START → route_node
            ├─ chitchat ──────────────→ answer_node（1 次 fast 调用，直连）
            └─ knowledge/tool/learning → plan_node → fan_out_node（并行子代理）
                                          → merge_node（汇总/去重/冲突标注）
                                          → reflect_node（LLM-as-judge；不足则回 plan，≤MAX_REFLECT）
                                          → answer_node → END

GWT② durable execution：编译时挂 AsyncRedisSaver(checkpointer)，同一 thread_id 下 node 执行
结果随状态写入 Redis checkpoint；进程 kill 后同 thread_id 重新 ainvoke 从最近 checkpoint 续跑，
已完成节点记录于 state.nodes_executed（随 checkpoint 持久化），续跑不重复执行。
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, HumanMessage
from loguru import logger

from app.ai.subagents import SubagentResult, SubagentTask, run_subagents
from app.ai import compaction as ai_compaction
from app.config import settings
# task94 R2 接入：skill registry 接入对话决策链（而非仅独立可调用）
from app.ai.skills.registry import SkillRegistry
from app.ai.skills import loader, trigger


# ============================================================
# 常量
# ============================================================
if getattr(settings, "MAX_REFLECT_ITERATIONS", None) is not None:
    MAX_REFLECT_ITERATIONS = int(settings.MAX_REFLECT_ITERATIONS)
else:
    MAX_REFLECT_ITERATIONS = 2
_LLM_TIMEOUT = 60.0


# ============================================================
# Agent State
# ============================================================
class AgentState(TypedDict):
    """LangGraph AI 助手状态。

    - messages：对话历史（add_messages reducer 自动追加）
    - user_id / session_id：真实用户上下文（由 service 注入，禁止硬编码为固定值）
    - intent：四类意图 chitchat / knowledge / tool / learning
    - effort：L0~L3 保守判定
    - tasks：plan_node 产出的子代理任务清单 [{subagent, objective, input}]
    - subagent_results：fan-out 后主 state 合并的蒸馏摘要列表
    - merged_context：merge 后的综合上下文
    - reflect_count：LLM-as-judge 轮数
    - sufficient：LLM-as-judge 判定结果（false 时回 plan 再检索）
    - final_answer：answer_node 产出
    - degraded_reason：降级说明
    - nodes_executed：已执行节点 trace（随 checkpoint 持久化，供 durable execution 验证）
    """
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: int
    session_id: str | None
    intent: str
    effort: str
    tasks: list[dict]
    subagent_results: list[dict]
    merged_context: str
    reflect_count: int
    sufficient: bool
    final_answer: str
    degraded_reason: str | None
    nodes_executed: list[str]
    compaction: dict | None
    skill_context: str                       # task94：命中的 skill body 按需注入（不进前缀，动态注入当前轮）
    active_paths: list[str]                  # 当前工作文件路径（驱动 paths 条件触发）
    context_edit: dict | None                # task97(task#25)：context_edit 决策链输出（编辑后 messages + 水位快照），供 plan 消费


def _empty_state(query: str, *, user_id: int, session_id: str | None) -> AgentState:
    return AgentState(
        messages=[HumanMessage(content=query)],
        user_id=int(user_id),
        session_id=session_id,
        intent="",
        effort="L1",
        tasks=[],
        subagent_results=[],
        merged_context="",
        reflect_count=0,
        sufficient=False,
        final_answer="",
        degraded_reason=None,
        nodes_executed=[],
        compaction=None,
        skill_context="",
        active_paths=[],
        context_edit=None,
    )


# ============================================================
# LLM 客户端（统一走 app.chat.generator._ChatClient；测试可 monkeypatch _llm_call）
# ============================================================
async def _llm_call(
    messages: list[dict],
    *,
    model: str,
    temperature: float = 0.0,
    max_tokens: int = 500,
    timeout: float = _LLM_TIMEOUT,
) -> str:
    from app.chat.generator import _ChatClient

    client = _ChatClient.get()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: client.call_chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        ),
    )


def _extract_json(raw: str) -> dict | None:
    if not raw:
        return None
    text = raw.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    else:
        a, b = text.find("{"), text.rfind("}")
        if a >= 0 and b > a:
            text = text[a : b + 1]
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _record(state: AgentState, node: str) -> None:
    """在 checkpoint 中追加「已执行节点」trace（持久化，续跑不再追加）。"""
    executed = list(state.get("nodes_executed") or [])
    executed.append(node)
    return {"nodes_executed": executed}


# ============================================================
# Skill registry（task94 R2 接入）：进程内单例，供 skill_node 消费
# ============================================================
_skill_registry_cache: "SkillRegistry | None" = None


def get_skill_registry() -> "SkillRegistry":
    """返回进程内缓存的 skill 注册表（首次调用扫描默认 roots，之后复用，避免每请求重扫 124 文件）。"""
    global _skill_registry_cache
    if _skill_registry_cache is None:
        _skill_registry_cache = SkillRegistry.default()
    return _skill_registry_cache


def set_skill_registry(reg: "SkillRegistry") -> None:
    """注入注册表（测试 / 嵌入场景用，避免依赖外部 AI-Hub 路径）。"""
    global _skill_registry_cache
    _skill_registry_cache = reg


# ============================================================
# Node 1b: skill_node —— task94 GWT③（registry 接入对话决策链）
# ============================================================
async def skill_node(state: AgentState) -> dict:
    """在 route 之后、plan 之前，把 skill registry 接入对话决策。

    依据用户消息 + 当前工作文件，用 trigger.decide 综合触发（/skill + paths + description 重叠），
    命中的 skill 通过 loader.load_body 按需加载 body（渐进式披露，不进前缀），拼接进
    state.skill_context，供 plan_node（子代理任务输入）与 answer_node（最终回答上下文）消费。

    这是「registry 被对话决策消费」而非「仅独立可调用」的关键落点。
    """
    query = ""
    for m in state.get("messages", []):
        if isinstance(m, HumanMessage):
            query = str(m.content)
    active_paths = state.get("active_paths") or []
    reg = get_skill_registry()
    matched = trigger.decide(reg.all(), query, active_paths)
    parts = []
    for s in matched:
        body = loader.load_body(s)  # 按需加载（progressive disclosure）
        if body.strip():
            parts.append(f"[skill:{s.name}]\n{body}")
    skill_context = "\n\n".join(parts)
    return {"skill_context": skill_context} | _record(state, "skill")


# ============================================================
# Node 1: route_node —— 四类意图路由
# ============================================================
_FAST_INTENTS = ("chitchat", "knowledge", "tool", "learning")

ROUTE_SYSTEM_PROMPT = """你是 EduAgent 的意图路由器。把用户的一条消息归类为四类之一，只输出 JSON {"intent": "<类别>"}：

- chitchat: 闲聊/打招呼/自我介绍/问候/系统功能询问，与学科知识无关
- knowledge: 具体学科知识问题（英语语法/编程/数学/物理等），需要查知识库
- tool: 明确可调用工具解决（计算/实时查询/代码执行等），工具列表能匹配
- learning: 学习方法/路径规划/考试策略等引导性建议，无需查具体知识库

严格只输出 JSON，不要多余文字。"""


# ============================================================
# 六核心节点：A1-② 真搬迁后的「薄壳」
# 真实编排逻辑已迁入 app.ai.harness.sixnode.SixNodeHarness；此处仅保留模块级函数名，
# 委托当前默认 harness 实例，以兼容：
#   - test_contract_task24：monkeypatch graph.answer_node 等后再 build_graph（红线）；
#   - test_contract_task94 / test_contract_task97：直接调用 graph.plan_node / answer_node 等。
# 自定义 harness（build_graph(harness=...)）由 build_graph 用闭包捕获，不写入 _CURRENT_HARNESS，
# 以免对其它测试的 graph.<node> 直接调用造成状态串扰。
# ============================================================
async def route_node(state: AgentState) -> dict:
    """A1-② 薄壳：真实逻辑见 SixNodeHarness.route。"""
    return await _default_harness().route(state)


def route_gate(state: AgentState) -> Literal["answer", "plan"]:
    """条件边：chitchat 直连 answer_node（1 次 fast 调用）；其余进 plan。"""
    intent = state.get("intent", "")
    if intent == "chitchat":
        return "answer"
    return "plan"


# ============================================================
# Node 2: plan_node —— 按意图 + effort 产出子代理任务清单
# ============================================================
def _effort_for_intent(intent: str) -> tuple[str, list[dict]]:
    """保守 effort scaling（对齐 Anthropic 数字）。
    返回 (level, tasks)。tasks 每项 {subagent, objective, input}。
    """
    base = {
        "search": {
            "subagent": "search",
            "objective": "检索知识库并蒸馏结论",
            "input": "基于问题给出检索要点",
        },
        "tool": {
            "subagent": "tool",
            "objective": "调用工具得到计算结果",
            "input": "明确要计算/查询的内容",
        },
        "learning": {
            "subagent": "learning",
            "objective": "分析画像并给出学习路径",
            "input": "用户当前学习诉求",
        },
        "memory": {
            "subagent": "memory",
            "objective": "召回用户记忆/偏好",
            "input": "供主代理决策的画像上下文",
        },
    }
    if intent == "knowledge":        # L1：2 子代理
        return "L1", [base["search"], base["memory"]]
    if intent == "tool":             # L2：3 子代理，含 memory 兜底
        return "L2", [base["tool"], base["search"], base["memory"]]
    if intent == "learning":         # L2：3 子代理（learning 走 strong 模型）
        return "L2", [base["learning"], base["search"], base["memory"]]
    return "L1", [base["search"]]    # 兜底


async def plan_node(state: AgentState) -> dict:
    """A1-② 薄壳：真实逻辑见 SixNodeHarness.plan。"""
    return await _default_harness().plan(state)


# ============================================================
# Node 2b: compact_node —— plan_node 前上下文压缩（task26 R4 + GWT①）
# ============================================================
def _flatten_state_context(state: AgentState) -> list[dict]:
    """把图 state 里的可压缩上下文拍平成 [{role, content}] 消息流。

    构成：对话 messages（HumanMessage）+ 子代理蒸馏摘要（伪 tool 消息）+ 上一轮综合上下文。
    """
    flat: list[dict] = []
    for m in state.get("messages", []):
        if isinstance(m, HumanMessage):
            flat.append({"role": "user", "content": str(m.content)})
        elif isinstance(m, BaseMessage):
            flat.append({"role": getattr(m, "type", "user"), "content": str(m.content)})
    for r in state.get("subagent_results", []):
        flat.append({"role": "tool", "content": f"[{r.get('subagent')}] {r.get('summary') or ''}"})
    prior = state.get("merged_context") or ""
    if prior:
        flat.append({"role": "assistant", "content": prior})
    return flat


async def compact_node(state: AgentState) -> dict:
    """plan_node 前按触发策略压缩上下文：优先 context_edit（轻量）→ 仍超才 compaction（重量）。

    GWT①：消息流 >6000 token → 压缩至 ≤6000；summary 保留结构化决策语义；最近 K=6 轮原文保留。
    压缩后的精简流（summary + 最近 K 轮原文）写入 `state.compaction["messages"]`，
    供下游（plan / fan_out 子代理上下文装配）**真正使用**压缩后上下文，而非仅观测快照。
    原始 messages 数组不动（前缀缓存友好）。
    """
    flat = _flatten_state_context(state)
    if not flat:
        return {"compaction": None} | _record(state, "compact")
    # task-C1-②（P0 批判落实）：装配增强压缩 feature flag
    #   anchor_round=ANCHOR_ROUND → 锚定闸门（闸门前字节零改动，保护前缀缓存）
    #   llm=make_fast_llm()        → 窗口内注入 FAST 动态选片段（未注入/失败自动回退规则选片段）
    # 仅窗口内/LLM 可用时注入 llm；不可用时 None，走规则选片段（向后兼容，零回归）。
    llm = None
    if getattr(settings, "COMPACTION_LLM_SELECT", True):
        try:
            llm = ai_compaction.make_fast_llm()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[graph] make_fast_llm 不可用，回退规则选片段: {exc}")
            llm = None
    result = ai_compaction.compact_messages(
        flat,
        anchor_round=settings.ANCHOR_ROUND,
        llm=llm,
    )
    # 压缩生效 → 暴露精简流供下游消费；仅观测时不改下游输入
    if result.get("applied") and result.get("kept_messages"):
        result["messages"] = result.get("kept_messages")
    return {"compaction": result} | _record(state, "compact")


# ============================================================
# Node 2c: context_edit_node —— 接入 context_edit 决策链（闭合 task96 批判②）
# ============================================================
def _edited_context_block(edited: "dict | None", limit: int = 2000) -> str:
    """从 context_edit 结果取出编辑后消息的可读文本摘要（去 system 前缀、截断），供子代理输入装配。

    只取非 system 消息正文，避免把已缓存的 system 前缀重复塞进子代理上下文；截断上限
    `limit` 防止把长历史整段灌入每个子代理任务的 input（token 控制）。
    """
    if not isinstance(edited, dict):
        return ""
    msgs = edited.get("messages") or []
    parts: list[str] = []
    total = 0
    for m in msgs:
        role = m.get("role") if isinstance(m, dict) else getattr(m, "role", "msg")
        if role == "system":
            continue
        text = str(m.get("content") if isinstance(m, dict) else getattr(m, "content", "")).strip()
        if not text:
            continue
        if total + len(text) > limit:
            parts.append(text[: max(0, limit - total)])
            break
        parts.append(text)
        total += len(text)
    return "\n".join(parts)


async def context_edit_node(state: AgentState) -> dict:
    """在 compact（重量压缩，第一道）之后、plan 之前接入 task96 的阈值策略链 apply_context_strategy
    （context_edit 轻量删消息保前缀 → 仍超阈值才 compaction 重量）。

    这是「context_edit 真正进入对话决策链路被调用」的落点（task96 批判②：此前仅观测未调用）：
    - 以 compact_node 的精简流为基底（其产出此前未被下游消费，此处首次真正消费）；
      若 compact 未产出 messages 则回退到 _flatten_state_context；
    - 调 apply_context_strategy 得到编辑后 messages（前缀签名稳定）并写入 state.context_edit；
    - 调 get_context_monitor().record 把上下文水位快照写入 task96 监控器，
      供 task97 缓存监控 joint_dashboard 串联「上下文水位 + 缓存命中」联合看板（GWT④）。
    """
    comp = state.get("compaction") or {}
    base = None
    if comp.get("applied") and comp.get("messages"):
        base = comp["messages"]
    if not base:
        base = _flatten_state_context(state)
    if not base:
        return {"context_edit": None} | _record(state, "context_edit")

    from app.ai.context_edit import apply_context_strategy, get_context_monitor

    result = apply_context_strategy(
        base,
        monitor=get_context_monitor(),
        session_id=state.get("session_id"),
    )
    return {"context_edit": result} | _record(state, "context_edit")


# ============================================================
# Node 3: fan_out_node —— 并行子代理（task92 runner，独立上下文 + asyncio.gather）
# ============================================================
def _build_tool_services(*, user_id: int, thread_id: str | None) -> dict[str, Any]:
    """把真实后端能力包装成子代理工具服务（search=检索 / tool=MCP）。

    工具服务在 fan_out_node 内、以「该请求的 user_id/thread_id」闭包绑定，禁止模块级共享状态
    （否则并发请求会串号）。GWT③ 要求 user_id 真实——此处由 state.user_id 注入。
    """
    services: dict[str, Any] = {}

    async def search_knowledge(args: dict | None = None):
        from app.chat.retriever import retrieve_three_channel as _retrieve

        q = (args or {}).get("q", "")
        if not q:
            return {"docs": [], "graph_entities": [], "error": "缺少查询词 q"}
        try:
            bundle = await _retrieve(
                q, user_id=int(user_id), role=None,
                use_hyde=False, enable_graph=True,
                top_k=8, final_max_k=5, cutoff_drop_ratio=0.2,
            )
            return {"docs": [d.model_dump() for d in bundle.docs], "graph_entities": [g.model_dump() for g in bundle.graph_entities], "retrieved_count": bundle.raw_retrieved_count}
        except Exception as exc:
            return {"docs": [], "graph_entities": [], "error": str(exc)[:200]}

    async def call_tool(args: dict | None = None):
        from app.mcp import executor as _mcp_executor

        args = args or {}
        # task-T1：路由到工具调用闭环（换参→换工具→熔断→人工指南）
        return await _mcp_executor.call_tool_with_retry(
            tool_name=args.get("tool_name", ""),
            args=args.get("args", {}),
            operator_user_id=int(user_id),
            session_id=thread_id or "",
            trace_id=thread_id or "",
        )

    async def recall_memory(args: dict | None = None):
        """GWT②：向量召回 top-3 记忆，供 memory 子代理蒸馏进 lead plan prompt。"""
        from app.ai.memory.service import recall_topk

        args = args or {}
        q = (args.get("q") or args.get("query") or "").strip()
        if not q:
            return {"memories": [], "error": "缺少查询词 q"}
        try:
            top = await recall_topk(int(user_id), q, top_k=int(args.get("top_k") or 3))
            return {"memories": top, "count": len(top)}
        except Exception as exc:
            return {"memories": [], "error": str(exc)[:200]}

    async def recall_profile(args: dict | None = None):
        """学习画像：以「画像/偏好/目标」关键词召回 top-3 记忆，供 learning 子代理规划。"""
        from app.ai.memory.service import recall_topk

        args = args or {}
        q = (args.get("profile_query") or args.get("q") or "学习画像 目标 偏好 规划").strip()
        try:
            top = await recall_topk(int(user_id), q, top_k=int(args.get("top_k") or 3))
            return {"profile": top, "count": len(top)}
        except Exception as exc:
            return {"profile": [], "error": str(exc)[:200]}

    services["search_knowledge"] = search_knowledge
    services["call_tool"] = call_tool
    services["recall_memory"] = recall_memory
    services["recall_profile"] = recall_profile
    return services


async def fan_out_node(state: AgentState) -> dict:
    """A1-② 薄壳：真实逻辑见 SixNodeHarness.fan_out。"""
    return await _default_harness().fan_out(state)


# ============================================================
# Node 4: merge_node —— 汇总 / 去重 / 冲突标注
# ============================================================
async def merge_node(state: AgentState) -> dict:
    """A1-② 薄壳：真实逻辑见 SixNodeHarness.merge。"""
    return await _default_harness().merge(state)


# ============================================================
# Node 5: reflect_node —— LLM-as-judge 判断是否充分
# ============================================================
REFLECT_SYSTEM_PROMPT = """你是研究质检员。判断子代理产出的综合上下文是否已能支撑最终回答。
只输出 JSON {"sufficient": true|false}。若关键信息缺失、需要进一步检索/验证，则为 false。"""


async def reflect_node(state: AgentState) -> dict:
    """A1-② 薄壳：真实逻辑见 SixNodeHarness.reflect。"""
    return await _default_harness().reflect(state)


def reflect_gate(state: AgentState) -> Literal["answer", "plan"]:
    """LLM-as-judge：sufficient=true → answer；false 且还有轮次 → 回 plan 再 fan-out。
    次数由 reflect_node 的 MAX_REFLECT_ITERATIONS 上限约束（到顶强制 sufficient=true）。"""
    sufficient = bool(state.get("sufficient", False))
    if sufficient:
        return "answer"
    return "plan"


# ============================================================
# Node 6: answer_node —— 最终回答（strong 模型，整合综合上下文 + 历史）
# ============================================================
ANSWER_SYSTEM_PROMPT = """你是 EduAgent 智能学习助手。基于以下综合上下文与用户问题，给出准确、结构化、友好的最终回答。
- 优先引用综合上下文中的结论；未覆盖时用自身知识并标注「基于通用知识」。
- 若存在降级情况，可简要说明。"""


async def answer_node(state: AgentState) -> dict:
    """A1-② 薄壳：真实逻辑见 SixNodeHarness.answer。"""
    return await _default_harness().answer(state)


# ============================================================
# 默认 harness 解析（供六核心薄壳委托；自定义 harness 走 build_graph 闭包，不污染此全局）
# ============================================================
_CURRENT_HARNESS: "Harness | None" = None


def _default_harness() -> "Harness":
    """返回默认 harness 单例（按 HARNESS_IMPL 取 SixNodeHarness）。

    被六核心薄壳 route_node/plan_node/.../answer_node 调用，既服务「默认 build_graph」也服务
    「graph.<node> 直接调用」场景。自定义 harness 由 build_graph 用闭包捕获，不写入此全局，
    以避免对其它测试 / 调用路径造成状态串扰。
    """
    global _CURRENT_HARNESS
    if _CURRENT_HARNESS is None:
        from app.ai.harness.registry import build_harness

        _CURRENT_HARNESS = build_harness()
    return _CURRENT_HARNESS


# ============================================================
# task-A1 批判④：拓扑锁定常量化 + 启动 fail-fast 自检
# （取代仅依赖测试硬断言；改边/改节点漏改时启动时立即暴露，而非运行时才失败）
# ============================================================
EXPECTED_SIXNODE_NODES = (
    "answer", "compact", "context_edit", "fan_out",
    "merge", "plan", "reflect", "route", "skill",
)
EXPECTED_SIXNODE_EDGES = (
    ("__start__", "route"),
    ("answer", "__end__"),
    ("compact", "context_edit"),
    ("context_edit", "plan"),
    ("fan_out", "merge"),
    ("merge", "reflect"),
    ("plan", "fan_out"),
    ("skill", "compact"),
)
EXPECTED_SIXNODE_BRANCHES = ("route", "reflect")


def _selfcheck_sixnode_topology() -> None:
    """启动 fail-fast：编译默认图并校验拓扑 == EXPECTED_SIXNODE_* 常量；不一致立即抛错。"""
    g = build_graph()  # 默认 harness（未编译），仅取 nodes/edges/branches
    nodes = tuple(sorted(g.nodes.keys()))
    edges: list[tuple[str, str]] = []
    for e in g.edges:
        if isinstance(e, tuple) and len(e) >= 2:
            edges.append((e[0], e[1]))
        else:
            edges.append((getattr(e, "source"), getattr(e, "target")))
    edges = tuple(sorted(edges))
    if nodes != EXPECTED_SIXNODE_NODES:
        raise RuntimeError(f"[graph] 拓扑节点集与 EXPECTED_SIXNODE_NODES 不符：{nodes}")
    if edges != EXPECTED_SIXNODE_EDGES:
        raise RuntimeError(f"[graph] 拓扑边集与 EXPECTED_SIXNODE_EDGES 不符：{edges}")
    if set(g.branches.keys()) != set(EXPECTED_SIXNODE_BRANCHES):
        raise RuntimeError(
            f"[graph] 条件分支应与 {EXPECTED_SIXNODE_BRANCHES} 一致：{set(g.branches.keys())}"
        )


# ============================================================
# 构建 & 编译图（挂 AsyncRedisSaver durable execution）
# ============================================================
def build_graph(harness: "Harness | None" = None) -> StateGraph:
    """编译 9 节点 DAG（route→skill→compact→context_edit→plan→fan_out→merge→reflect→answer）。

    harness：可插拔编排实现（task-A1）。默认按 HARNESS_IMPL 取 SixNodeHarness（=重构前行为零变化）。
    图拓扑（节点名 + 边）固定，不随 harness 切换改变（keep_sixnode）。

    A1-② 接线规则：
    - 默认 harness：六核心节点接线「模块级薄壳」route_node/plan_node/.../answer_node，使
      test_contract_task24 对 graph.answer_node 等的 monkeypatch 与 graph.<node> 直接调用契约继续生效。
    - 自定义 harness（harness=...）：用闭包捕获该实例接线，避免污染模块级 _CURRENT_HARNESS，
      保证其它测试的 graph.<node> 直接调用仍走默认 harness（无状态串扰）。
    skill/compact/context_edit 为稳定支持节点（所有 harness 共享），始终接线模块级真实实现。

    注意：本模块不 import harness（避免与 app.ai.harness.base 的循环依赖），
    默认 harness 延迟在 _default_harness 内解析。
    """
    if harness is None:
        h = _default_harness()
        core = {
            "route": route_node,
            "plan": plan_node,
            "fan_out": fan_out_node,
            "merge": merge_node,
            "reflect": reflect_node,
            "answer": answer_node,
        }
    else:
        h = harness

        async def _route(state, _h=h):
            return await _h.route(state)

        async def _plan(state, _h=h):
            return await _h.plan(state)

        async def _fan_out(state, _h=h):
            return await _h.fan_out(state)

        async def _merge(state, _h=h):
            return await _h.merge(state)

        async def _reflect(state, _h=h):
            return await _h.reflect(state)

        async def _answer(state, _h=h):
            return await _h.answer(state)

        core = {
            "route": _route,
            "plan": _plan,
            "fan_out": _fan_out,
            "merge": _merge,
            "reflect": _reflect,
            "answer": _answer,
        }

    workflow = StateGraph(AgentState)

    if h.has_preprocess:
        workflow.add_node("preprocess", h.preprocess)
    workflow.add_node("route", core["route"])
    workflow.add_node("skill", skill_node)
    workflow.add_node("compact", compact_node)
    workflow.add_node("context_edit", context_edit_node)
    workflow.add_node("plan", core["plan"])
    workflow.add_node("fan_out", core["fan_out"])
    workflow.add_node("merge", core["merge"])
    workflow.add_node("reflect", core["reflect"])
    workflow.add_node("answer", core["answer"])

    # 可选预处理钩子（A1-①）：仅当 harness 真正覆盖 preprocess 才插入节点，默认拓扑零变化
    if h.has_preprocess:
        workflow.add_edge(START, "preprocess")
        workflow.add_edge("preprocess", "route")
    else:
        workflow.add_edge(START, "route")
    # 非 chitchat 意图 → 先 skill（registry 接入决策，按需注入 body）→ compact（重量压缩第一道）
    # → context_edit（task96 阈值策略链：context_edit 轻量保前缀 → 仍超才 compaction；记录水位快照）→ plan
    workflow.add_conditional_edges("route", route_gate, {"answer": "answer", "plan": "skill"})
    workflow.add_edge("skill", "compact")
    workflow.add_edge("compact", "context_edit")
    workflow.add_edge("context_edit", "plan")
    workflow.add_edge("plan", "fan_out")
    workflow.add_edge("fan_out", "merge")
    workflow.add_edge("merge", "reflect")
    # reflect 回 plan 也先 compact（随迭代上下文增长的压缩，≤MAX_REFLECT 终止）
    workflow.add_conditional_edges("reflect", reflect_gate, {"answer": "answer", "plan": "compact"})
    workflow.add_edge("answer", END)
    return workflow


def _make_checkpointer():
    """创建原生 Redis durable checkpointer。

    本环境 Redis(6379) 为原生 Redis，无 RediSearch/RedisJSON 模块；LangGraph 自带的
    AsyncRedisSaver 依赖 redisvl 向量索引（FT.INFO/FT.CREATE），无法在原生 Redis 上建索引。
    因此使用自定义 PlainRedisSaver（复用 InMemorySaver 语义 + 逐线程 pickle 快照落 Redis），
    满足 GWT②「中途 kill 后同 thread_id 恢复、不重复已完成节点」的 Redis durable execution。
    Redis 不可用时降级为 None（本地开发不阻塞）。
    """
    try:
        from app.ai.checkpoint_redis import PlainRedisSaver

        return PlainRedisSaver(redis_url=settings.REDIS_URL, ttl=getattr(settings, "CHECKPOINT_TTL", 3600))
    except Exception as exc:
        logger.warning(f"[graph] Redis checkpointer 不可用（降级无 checkpoint）: {type(exc).__name__}: {exc}")
        return None


_checkpointer_lock: asyncio.Lock | None = None
_agent_graph: Any = None
_topo_checked: bool = False


async def _ensure_agent_graph() -> "Any":
    """惰性初始化并编译图（AsyncRedisSaver 需 asetup）。

    - 持久化可用：编译时挂 AsyncRedisSaver，node 结果随 checkpoint 写入 Redis（durable execution）。
    - Redis 不可用：降级为不带 checkpointer 的图（本地开发/打靶不阻塞）。
    - 首次调用后缓存编译结果；并发调用由 Lock 串行化。
    - 启动 fail-fast（task-A1 批判③④）：拓扑自检 + HARNESS_IMPL 配置校验。
    """
    global _agent_graph, _checkpointer_lock, _topo_checked
    if _agent_graph is not None:
        return _agent_graph
    if _checkpointer_lock is None:
        _checkpointer_lock = asyncio.Lock()
    async with _checkpointer_lock:
        if _agent_graph is not None:
            return _agent_graph
        # 启动 fail-fast：拓扑自检（批判④）+ harness 配置校验（批判③），仅首次执行
        if not _topo_checked:
            _selfcheck_sixnode_topology()
            _topo_checked = True
        try:
            from app.ai.harness.registry import validate_harness_config

            cfg_err = validate_harness_config()
            if cfg_err:
                logger.warning(f"[graph] {cfg_err}（build_harness 已回退 sixnode）")
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[graph] harness 配置校验跳过：{type(exc).__name__}: {exc}")
        saver = _make_checkpointer()
        try:
            if saver is not None:
                await saver.asetup()
        except Exception as exc:
            logger.warning(f"[graph] AsyncRedisSaver asetup 失败，降级无 checkpoint: {type(exc).__name__}: {exc}")
            saver = None
        compiled = build_graph().compile(checkpointer=saver)
        _agent_graph = compiled
        return compiled


def compile_graph():
    """同步编译（供测试复刻图，不挂持久化）。返回 compiled graph。"""
    return build_graph().compile()


# 全局单例（惰性 async 初始化）
agent_graph: "Any" = None


async def run_agent(query: str, *, user_id: int, session_id: str | None = None, active_paths: list[str] | None = None) -> dict:
    """运行 AI 助手图。返回与旧 langgraph_agent.run_agent 兼容的 dict。

    task26 防过载：入口 acquire 全局 LLM 并发闸 + 单用户并发槽（第 3 个并发被拒、
    全局闸满排队 >10s 返回友好提示）；出口 finally release。Redis 不可用时 fail-open（不阻塞本地/打靶）。
    active_paths：当前工作文件路径（task94 GWT④，驱动 skill paths 条件触发）。
    """
    g = await _ensure_agent_graph()
    state = _empty_state(query, user_id=user_id, session_id=session_id)
    state["active_paths"] = list(active_paths or [])
    config = {"configurable": {"thread_id": session_id or f"task24-{user_id}"}}

    # —— task26 防过载准入 ——
    guard_entry: dict | None = None
    try:
        from app.ai.guard import default_guard
        from app.config import settings as _gcfg
        # 传入 request_meta 提升 token 预估精度（避免静默回退默认 ESTIMATE_DEFAULT_TOKENS）
        _request_meta = {
            "query": (query or "")[:4000],
            "max_tokens": int(_gcfg.LLM_MAX_TOKENS),
        }
        guard_entry = await default_guard().acquire(int(user_id), request_meta=_request_meta)
    except Exception as exc:
        logger.warning(f"[graph.guard] 防过载闸异常，fail-open: {type(exc).__name__}: {exc}")
        guard_entry = None
    if guard_entry is not None and not guard_entry.get("ok"):
        return {
            "answer": guard_entry.get("message", "服务繁忙，请稍后重试"),
            "docs": [], "graph_entities": [], "tool_results": [], "loop_count": 0,
            "latency_ms": 0, "intent": "", "effort": "L1", "subagents": [],
            "nodes_executed": [], "degraded_reason": guard_entry.get("reason"),
        }

    t0 = time.perf_counter()
    try:
        try:
            final = await g.ainvoke(state, config)
        finally:
            if guard_entry is not None:
                try:
                    from app.ai.guard import default_guard
                    await default_guard().release(int(user_id))
                except Exception:
                    pass
    except Exception as exc:
        logger.error(f"[graph.run] 图执行异常: {type(exc).__name__}: {exc}")
        return {"answer": f"AI 服务异常（{type(exc).__name__}），请稍后重试", "docs": [], "graph_entities": [], "tool_results": [], "loop_count": 0, "latency_ms": int((time.perf_counter() - t0) * 1000), "degraded_reason": str(exc)[:120]}
    latency_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "answer": final.get("final_answer", ""),
        "docs": [],
        "graph_entities": [],
        "tool_results": [],
        "loop_count": int(final.get("reflect_count", 0)),
        "latency_ms": latency_ms,
        "intent": final.get("intent", ""),
        "effort": final.get("effort", "L1"),
        "subagents": final.get("subagent_results", []),
        "nodes_executed": final.get("nodes_executed", []),
        "degraded_reason": final.get("degraded_reason"),
    }