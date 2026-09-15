"""
LangGraph Agent 闭环流程图（Phase 4 Agent 架构重构）

流程：
  User Input
    → agent_node（LLM 决策：chat / search_knowledge / call_tool / generate）
    → 如果是 search_knowledge → retrieve_node（Milvus + Neo4j） → 回到 agent_node
    → 如果是 call_tool → tool_node（MCP 工具） → 回到 agent_node
    → 如果是 generate → generate_node（LLM 生成最终回答） → END

面试考点：
- 为什么用 LangGraph？LangGraph 提供了有向图 + 条件边 + 状态管理 + Checkpoint
- 与普通代码的区别：普通代码是线性三步（决策→检索→生成），LangGraph 可以循环（LLM 思考→调用工具→收到结果→再思考→生成）
- StateGraph 的核心：State（共享状态） + Node（执行节点） + Edge（条件边）
- 中间件集成：在 node 执行前注入 pre-hook（限流/鉴权/脱敏/日志）
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from loguru import logger

from app.chat.retriever import RetrievalBundle, retrieve_three_channel
from app.chat.generator import _ChatClient, format_docs_for_prompt, format_graph_for_prompt
from app.chat.schemas import RetrievedDoc, GraphEntity
from app.config import settings


# ============================================================
# Agent State（在图中流转的共享状态）
# ============================================================
class AgentState(TypedDict):
    """LangGraph Agent 状态。

    字段说明：
    - messages: 对话历史（LangChain 消息列表），用 add_messages reducer 自动追加
    - docs: 检索到的文档列表
    - graph_entities: 图谱实体列表
    - tool_results: MCP 工具执行结果
    - loop_count: 循环次数（防止无限循环）
    - next_action: 下一步动作（agent_node 决策结果）
    - final_answer: 最终回答（generate_node 产出）
    - tool_name / tool_args: agent_node 决策 call_tool 时的目标工具与参数
    - query_rewrite: agent_node 决策 search_knowledge 时的改写检索词

    W-NEXT-2 步骤2b（T4-C3 同源根因）：`tool_name/tool_args/query_rewrite` **必须显式声明**——
    LangGraph 只为声明过的键建 channel，未声明的键在 agent_node → tool_node 流转时被直接丢弃，
    于是 tool_node 永远读到空 tool_name → 恒返回「未指定工具名/error」（工具执行链路结构不可达）。
    """
    messages: Annotated[list[BaseMessage], add_messages]
    docs: list[dict]
    graph_entities: list[dict]
    tool_results: list[dict]
    loop_count: int
    next_action: str
    final_answer: str
    tool_name: str
    tool_args: dict
    query_rewrite: str
    user_id: int
    user_role: str


# ============================================================
# Agent System Prompt（LangGraph 版）
# ============================================================
_TOOL_CATALOG_CACHE: str | None = None


def _agent_tool_catalog() -> str:
    """按权限门实物清单动态生成「已注册工具」清单。

    单一事实源 = app.ai.permission_gate（REGISTERED_BUILTIN_TOOLS ∪ REGISTERED_MCP_TOOLS），
    禁止在 prompt 中硬编码工具名——否则 LLM 会宣称调用不存在的工具（幻觉式成功，T8-C2/W2-G6）。
    """
    global _TOOL_CATALOG_CACHE
    if _TOOL_CATALOG_CACHE is not None:
        return _TOOL_CATALOG_CACHE
    try:
        from app.ai import permission_gate as _pg
        names = sorted(set(_pg.REGISTERED_BUILTIN_TOOLS) | set(_pg.REGISTERED_MCP_TOOLS))
    except Exception as exc:
        logger.warning(f"[Agent] 工具清单加载失败，按空清单处理: {type(exc).__name__}")
        names = []
    _TOOL_CATALOG_CACHE = "、".join(names) if names else "（当前无已注册工具）"
    return _TOOL_CATALOG_CACHE


AGENT_SYSTEM_PROMPT = """你是 EduAgent 智能学习助手，你可以使用以下能力来回答用户问题：

## 可用能力
1. **search_knowledge**：搜索知识库（向量检索 + 图谱查询），获取课程/知识点/题库相关内容
2. **call_tool**：调用 MCP 工具（当前已注册：{tool_catalog}）
3. **generate**：基于已有信息生成最终回答

## 决策规则
- 用户问学科知识（英语/编程/数学/物理等）→ 先 search_knowledge，再 generate
- 用户问需要计算/执行代码的问题 → 先 call_tool，再 generate
- 用户闲聊/打招呼 → 直接 generate
- 用户问"怎么学"等学习方法 → 直接 generate（不需要检索知识库）
- 如果 search_knowledge 返回空结果 → 用自身知识 generate，标注"基于通用知识"
- 如果 call_tool 失败 → 告知用户工具不可用，用自身知识 generate

## 输出格式
你必须输出一个 JSON 对象：
```json
{"action": "search_knowledge", "query_rewrite": "改写后的检索词", "reason": "决策理由"}
```
或
```json
{"action": "call_tool", "tool_name": "add", "tool_args": {"a": 1, "b": 2}, "reason": "决策理由"}
```
或
```json
{"action": "generate", "reason": "决策理由"}
```

注意：
- 每轮只能输出一个 action
- query_rewrite 用于向量检索，提取关键词（如"现在完成时 用法 区别"）
- 最多循环 3 轮（search/call_tool → 回到决策 → 再 search/call_tool → generate）
- tool_name **只能**取上面「可用能力-2」列出的已注册工具名；不在清单内的一律不得输出（不存在即不可调用）
- 严禁宣称「已完成/已创建/已导入/已上架」等完成态：只有工具结果标记为成功时才可以描述执行结果；
  被权限门拦截（[已拦截]）或执行失败时，必须如实说明"没有发生任何数据变更"，不得编造成功
"""


# ============================================================
# Node 1: agent_node — LLM 决策节点
# ============================================================
def _parse_agent_output(raw: str) -> dict:
    """从 LLM 输出中提取 JSON 决策。"""
    if not raw:
        return {"action": "generate", "reason": "LLM 无输出"}
    text = raw.strip()
    # 去掉 markdown 包裹
    import re
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    else:
        a, b = text.find("{"), text.rfind("}")
        if a >= 0 and b > a:
            text = text[a:b + 1]
    try:
        return json.loads(text)
    except Exception:
        return {"action": "generate", "reason": "LLM 输出无法解析"}


def _build_agent_messages(state: AgentState) -> list[dict]:
    """构建发给 LLM 的消息列表。"""
    messages = [{"role": "system", "content": AGENT_SYSTEM_PROMPT.replace("{tool_catalog}", _agent_tool_catalog())}]

    # 历史消息
    for msg in state.get("messages", []):
        if isinstance(msg, HumanMessage):
            messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            messages.append({"role": "assistant", "content": msg.content})
        elif isinstance(msg, ToolMessage):
            messages.append({"role": "tool", "content": msg.content})

    # 如果有检索结果，追加到上下文
    docs = state.get("docs", [])
    if docs:
        doc_summary = f"检索到 {len(docs)} 条相关文档，摘要：\n"
        for i, d in enumerate(docs[:3]):
            doc_summary += f"  doc[{i+1}]: {d.get('content', '')[:200]}...\n"
        messages.append({"role": "system", "content": doc_summary})
        # 检索完后应生成答案
        messages.append({"role": "system", "content": "检索已完成，请输出 {\"action\": \"generate\", \"reason\": \"检索结果已就绪\"}"})

    # 工具结果
    tool_results = state.get("tool_results", [])
    if tool_results:
        tool_summary = "工具执行结果：\n"
        for tr in tool_results:
            tool_summary += f"  - {tr.get('tool_name', 'unknown')}: {_tool_result_text(tr)[:300]}\n"
        messages.append({"role": "system", "content": tool_summary})
        messages.append({"role": "system", "content": "工具已执行，请输出 {\"action\": \"generate\", \"reason\": \"工具结果已就绪\"}"})

    return messages


async def agent_node(state: AgentState) -> dict:
    """
    LLM 决策节点。

    核心逻辑：
    1. 如果已有检索结果或工具结果 → 直接决定 generate
    2. 否则 → LLM 分析用户意图 → 决定 search_knowledge / call_tool / generate
    """
    # 安全检查：防止无限循环
    loop_count = state.get("loop_count", 0)
    if loop_count >= 3:
        logger.warning(f"[Agent] 达到最大循环次数 {loop_count}，强制 generate")
        return {"next_action": "generate", "loop_count": loop_count + 1}

    docs = state.get("docs", [])
    tool_results = state.get("tool_results", [])

    # 如果已经检索过或有工具结果 → 直接生成答案
    if docs or tool_results:
        return {"next_action": "generate", "loop_count": loop_count}

    # 如果已经循环过（检索完成但无结果）→ 强制生成
    if loop_count > 0:
        logger.info(f"[Agent] 循环 {loop_count} 次后无结果，强制 generate")
        return {"next_action": "generate", "loop_count": loop_count}

    # 第一次进入：LLM 决策
    messages = _build_agent_messages(state)
    # 追加当前用户问题（最后一条 HumanMessage）
    user_msgs = [m for m in state.get("messages", []) if isinstance(m, HumanMessage)]
    if user_msgs:
        messages.append({"role": "user", "content": f"当前问题：{user_msgs[-1].content}"})

    try:
        client = _ChatClient.get()
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(
            None,
            lambda: client.call_chat(
                messages=messages,
                model="fast",
                temperature=0.0,
                max_tokens=500,
                timeout=30.0,
            ),
        )
    except Exception as exc:
        logger.warning(f"[Agent] LLM 决策失败，直接 generate: {type(exc).__name__}: {exc}")
        return {"next_action": "generate", "loop_count": loop_count + 1}

    decision = _parse_agent_output(raw)
    action = decision.get("action", "generate")
    reason = decision.get("reason", "")
    logger.info(f"[Agent] 决策: action={action} reason={reason[:80]}")

    return {
        "next_action": action,
        "loop_count": loop_count + 1,
        # 如果 action 是 search_knowledge，传递 query_rewrite
        **({"query_rewrite": decision.get("query_rewrite", "")} if action == "search_knowledge" else {}),
        **({"tool_name": decision.get("tool_name", ""), "tool_args": decision.get("tool_args", {})} if action == "call_tool" else {}),
    }


# ============================================================
# Node 2: retrieve_node — 检索节点（Milvus + Neo4j）
# ============================================================
async def retrieve_node(state: AgentState) -> dict:
    """
    检索知识库。

    调用 retriever.retrieve_three_channel 做混合检索（稠密 + 稀疏 + 图谱）。
    """
    user_msgs = [m for m in state.get("messages", []) if isinstance(m, HumanMessage)]
    query = user_msgs[-1].content if user_msgs else ""

    # 用 agent_node 传来的 query_rewrite（如果有）
    query_rewrite = state.get("query_rewrite", "") or query

    logger.info(f"[Agent] 检索: '{query_rewrite[:60]}'")

    try:
        user_id = int(state.get("user_id", 1) or 1)
        bundle: RetrievalBundle = await retrieve_three_channel(
            query_rewrite,
            user_id=user_id,  # 真实 user_id 由 run_agent 从请求注入，禁止硬编码
            role=None,
            use_hyde=True,
            enable_graph=True,
            top_k=12,
            final_max_k=5,
            cutoff_drop_ratio=0.2,
        )
        docs = [d.model_dump() for d in bundle.docs]
        graph = [g.model_dump() for g in bundle.graph_entities]
        logger.info(f"[Agent] 检索结果: {len(docs)} docs, {len(graph)} graph entities")
    except Exception as exc:
        logger.warning(f"[Agent] 检索失败: {type(exc).__name__}: {exc}")
        docs = []
        graph = []

    return {"docs": docs, "graph_entities": graph}


# ============================================================
# Node 3: tool_node — MCP 工具调用节点
# ============================================================
# R11 HITL（contracts/reshape-r-hitl.json）：写类/外发类/危险级工具执行前 interrupt。
# 工具集 = R15 write_class_tools（admin_write）∪ course_write ∪ hitl_gate 高风险类
# （复用 executor._classify_hitl_action 分类，单一事实源，禁另造分类器）；
# 风险级用 hitl_gate.RiskLevel 映射到契约 low|medium|high。
def _hitl_risk_level(tool_name: str) -> str | None:
    """判定工具是否需要 HITL 中断，返回契约风险级 low|medium|high；只读/未登记 → None（免中断）。"""
    from app.ai.hitl_gate import RiskLevel
    from app.ai.permission_gate import ADMIN_WRITE_TOOLS, COURSE_WRITE_TOOLS
    from app.mcp.executor import _classify_hitl_action

    n = (tool_name or "").strip().lower()
    risk_map = {RiskLevel.L1.value: "low", RiskLevel.L2.value: "medium", RiskLevel.L3.value: "high"}
    # W-NEXT-2 步骤3：ADMIN_WRITE_TOOLS/COURSE_WRITE_TOOLS = 契约挂起 ∪ **已注册实物**，
    # 上线后的 knowledge_import（admin_write）经此命中 high → interrupt 真实可触达（T8-C1）。
    if n in ADMIN_WRITE_TOOLS:
        return risk_map[RiskLevel.L3.value]   # write_class_tools（收藏写/积分/知识库导入/订单）→ high
    if n in COURSE_WRITE_TOOLS:
        return risk_map[RiskLevel.L2.value]   # 课程/题库写类 → medium
    if _classify_hitl_action(n) is not None:
        return risk_map[RiskLevel.L3.value]   # executor 高风险类（执行/网络/退款/写前缀）→ high
    return None


def _tool_result_from_resp(tool_name: str, resp) -> dict:
    """executor 响应 → agent tool_result（T4-C2 末段修复）。

    - 统一从 pydantic 响应取值（原实现用 `result.get(...)` 对模型对象直接 AttributeError →
      一律落进 except 记为「工具执行异常」，真实结果被吞）。
    - executor 收口的 ACI 拒绝信封（content_text 内嵌 {status:denied,code,message,action_hint}）
      还原为 denied 记录，**必带 `result` 键**（generate 层与 prompt 渲染不再 KeyError）。
    """
    data = resp.model_dump() if hasattr(resp, "model_dump") else (resp if isinstance(resp, dict) else {})
    raw = str(data.get("content_text") or "")
    if raw.strip().startswith("{"):
        try:
            env = json.loads(raw)
            if isinstance(env, dict) and env.get("status") == "denied":
                msg = str(env.get("message") or "该操作已被安全拦截。")
                hint = str(env.get("action_hint") or "")
                return {
                    "tool_name": tool_name, "status": "denied",
                    "code": str(env.get("code") or "permission_denied"),
                    "message": msg, "action_hint": hint,
                    "result": f"[已拦截] {msg}（{hint}）",
                }
        except Exception:  # noqa: BLE001 — 非 JSON 内容按普通结果处理
            pass
    # model_dump()（python 模式）返回枚举成员本身，str() 会得到 "ToolCallStatusEnum.SUCCESS"
    # → 必须先取 .value 再归一，否则真实成功结果被误判为 error（本轮实测暴露）。
    _st_raw = data.get("status")
    up = str(getattr(_st_raw, "value", _st_raw) or "").upper()
    status = {"SUCCESS": "success", "SKIPPED": "skipped", "TIMEOUT": "timeout"}.get(up, "error")
    text = raw or str(data.get("error_message") or "")
    return {"tool_name": tool_name, "status": status, "result": text[:500]}


def _tool_result_text(tr: dict) -> str:
    """统一的工具结果文本（T4-C2 断链修复）。

    denied/rejected 记录没有 `result` 键（或为空），直接 `tr['result']` 会 KeyError 并把本地
    逻辑缺陷误分类为下游 LLM 故障；此处按 status 回退 message + action_hint，保证渲染不炸。
    """
    status = str(tr.get("status") or "")
    text = str(tr.get("result") or "")
    if status == "denied":
        msg = str(tr.get("message") or text or "权限不足，操作被拦截，未执行。")
        hint = str(tr.get("action_hint") or "")
        return f"[已拦截] {msg}（{hint}）" if hint else f"[已拦截] {msg}"
    if status == "rejected":
        msg = str(tr.get("message") or text or "用户拒绝执行该高风险操作，工具未执行。")
        hint = str(tr.get("action_hint") or "")
        return f"[已拒绝] {msg}（{hint}）" if hint else f"[已拒绝] {msg}"
    if text:
        return text
    # 兜底：任何无 result 的记录都不得让渲染层抛 KeyError
    return str(tr.get("message") or "")


async def tool_node(state: AgentState) -> dict:
    """
    调用 MCP 工具。

    从 state 中读取 tool_name 和 tool_args，调用 MCP executor。
    在 call_tool 之前过权限门（can_use_tool，默认 deny fail-closed）；deny 不抛异常、
    不进现有 except 分支，直接返回 ACI 错误信封（code/message/action_hint）。
    R11：权限门通过后、执行前，写类/外发类/危险级工具（settings.HITL_ENABLED=True 时）
    过 langgraph interrupt() 挂起（F-C01-002 interrupt+Command(resume) 三件套）；
    resume=confirm → 真实执行；reject → 零执行 + 拒绝上下文给 generate。
    """
    tool_name = state.get("tool_name", "")
    tool_args = state.get("tool_args", {})

    if not tool_name:
        return {"tool_results": [{"tool_name": "unknown", "status": "error", "result": "未指定工具名"}]}

    # R15 权限门：call_tool 之前判定，deny 零执行（W-NEXT-2 步骤2：与流式路径同源
    # 消费 permission_gate.gate_tool_call / build_denied_envelope —— 禁两份拷贝）
    from app.ai.permission_gate import build_denied_envelope, gate_tool_call
    role = state.get("user_role", "") or "student"
    decision = gate_tool_call(role, tool_name)
    if not decision.allowed:
        env = build_denied_envelope(role, tool_name, decision)
        return {"tool_results": [{
            "tool_name": tool_name,
            "status": "denied",
            "code": env["code"],
            "message": env["message"],
            "action_hint": env["action_hint"],
            "result": f"[已拦截] {env['message']}（{env['action_hint']}）",
        }]}

    # R11 HITL：写类/外发类/危险级工具执行前 interrupt（总开关 settings.HITL_ENABLED）
    _hitl_confirmed = False
    if getattr(settings, "HITL_ENABLED", False):
        risk = _hitl_risk_level(tool_name)
        if risk is not None:
            from langgraph.config import get_config
            from langgraph.types import interrupt

            cfg = get_config()
            thread_id = str((cfg.get("configurable") or {}).get("thread_id") or "unknown")
            payload = {
                "thread_id": thread_id,
                "tool_name": tool_name,
                "args": tool_args,
                "risk_level": risk,
                "timeout_s": 300,
            }
            logger.info(f"[Agent] HITL 中断等待确认: {payload}")
            resume_value = interrupt(payload)
            d = resume_value if isinstance(resume_value, dict) else {}
            action = str(d.get("action") or "").strip().lower()
            if action != "confirm":
                logger.warning(f"[Agent] HITL 拒绝执行工具: {tool_name} reason={d.get('reason')}")
                return {"tool_results": [{
                    "tool_name": tool_name,
                    "status": "rejected",
                    "code": "hitl_rejected",
                    "message": "您拒绝了该高风险操作，工具未执行。",
                    "reason": str(d.get("reason") or ""),
                    "action_hint": "如需执行可重新提问并确认。",
                }]}
            logger.info(f"[Agent] HITL 确认执行工具: {tool_name}")
            _hitl_confirmed = True

    logger.info(f"[Agent] 调用工具: {tool_name}({tool_args})")

    try:
        from app.mcp import executor as mcp_executor
        resp = await mcp_executor.call_tool(
            tool_name=tool_name,
            args=tool_args,
            operator_user_id=int(state.get("user_id", 1) or 1),  # 真实 user_id 由 run_agent 注入
            # HITL 已在 langgraph interrupt 环节人工确认 → 告知 executor 层的 HITL 收口
            # 「已批准」，避免同一动作被二次挂起（双重门 → admin 确认后仍不执行）。
            hitl_decision=True if _hitl_confirmed else None,
        )
        tool_results = [_tool_result_from_resp(tool_name, resp)]
    except Exception as exc:
        logger.warning(f"[Agent] 工具调用失败: {type(exc).__name__}: {exc}")
        tool_results = [{"tool_name": tool_name, "status": "error", "result": "工具执行异常，未执行成功。"}]

    return {"tool_results": tool_results}


# ============================================================
# Node 4: generate_node — LLM 生成最终回答
# ============================================================
async def generate_node(state: AgentState) -> dict:
    """
    LLM 生成最终回答。

    整合检索结果 + 工具结果 + 对话历史 → LLM 生成答案。
    """
    user_msgs = [m for m in state.get("messages", []) if isinstance(m, HumanMessage)]
    query = user_msgs[-1].content if user_msgs else ""

    docs = [RetrievedDoc(**d) for d in state.get("docs", [])]
    graph = [GraphEntity(**g) for g in state.get("graph_entities", [])]
    tool_results = state.get("tool_results", [])

    # 历史对话
    history_str = ""
    for msg in state.get("messages", []):
        if isinstance(msg, HumanMessage):
            history_str += f"- user: {msg.content[:100]}\n"
        elif isinstance(msg, AIMessage) and msg.content:
            history_str += f"- assistant: {msg.content[:100]}\n"

    # 构建 prompt — 始终用闲聊模式做基础，参考材料作为附加上下文
    from app.chat.prompts import CHAT_SYSTEM_PROMPT, CHAT_USER_PROMPT

    # 基础系统提示词
    system_prompt = CHAT_SYSTEM_PROMPT.format(
        platform_rule="当前支持英语/编程/数学。"
    )

    # 如果有检索结果，附加为参考材料
    if docs:
        system_prompt += "\n\n## 参考材料（来自知识库，优先参考）\n"
        system_prompt += format_docs_for_prompt(docs)
        system_prompt += "\n\n如果参考材料与用户问题相关，请引用并标注来源。不相关则用自己的知识回答。"

    # 图谱扩展
    if graph:
        system_prompt += "\n\n## 图谱扩展\n" + format_graph_for_prompt(graph)

    # 工具结果（T4-C2：deny/reject 记录无 result 键，必须走 _tool_result_text 回退，
    # 否则 KeyError → 被 run_agent 兜底文案吞成「AI 服务异常」，真实拒绝上下文彻底丢失）
    if tool_results:
        system_prompt += "\n\n## 工具调用结果\n"
        for tr in tool_results:
            system_prompt += f"- {tr.get('tool_name', 'unknown')}: {_tool_result_text(tr)[:300]}\n"
        if not any(str(tr.get("status")) == "success" for tr in tool_results):
            system_prompt += (
                "\n\n注意：本轮工具调用**没有一次成功执行**，"
                "上面所有条目都是「未执行/被拦截/被拒绝」，**没有发生任何数据变更**。"
                "严禁使用「已完成/已创建/已导入/已上架/已提交」等完成态描述；"
                "若为权限拦截，请如实告知用户无权执行并给出 action_hint 建议。\n"
            )

    user_prompt = CHAT_USER_PROMPT.format(history_str=history_str, query=query)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        client = _ChatClient.get()
        loop = asyncio.get_running_loop()
        answer = await loop.run_in_executor(
            None,
            lambda: client.call_chat(
                messages=messages,
                model="fast",
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
                timeout=60.0,
            ),
        )
        logger.info(f"[Agent] 生成答案: {len(answer)} chars")
    except Exception as exc:
        logger.warning(f"[Agent] LLM 生成失败: {type(exc).__name__}: {exc}")
        answer = "抱歉，AI 服务暂时不可用，请稍后重试。"

    return {"final_answer": answer}


# ============================================================
# 路由函数：根据 agent_node 的决策决定下一步
# ============================================================
def router(state: AgentState) -> Literal["retrieve", "tool", "generate", "end"]:
    """条件边：根据 next_action 决定跳转到哪个节点。"""
    action = state.get("next_action", "generate")
    if action == "search_knowledge":
        return "retrieve"
    elif action == "call_tool":
        return "tool"
    elif action == "generate":
        return "generate"
    return "end"


# 检索/工具完成后回到 agent_node 的路由
def after_action_router(state: AgentState) -> Literal["agent", "generate"]:
    """检索/工具执行完后的路由：回到 agent_node 让 LLM 再次决策。"""
    loop_count = state.get("loop_count", 0)
    if loop_count >= 3:
        return "generate"
    return "agent"


# ============================================================
# 构建 StateGraph
# ============================================================
def build_agent_graph() -> StateGraph:
    """
    构建 LangGraph Agent 图。

    图结构：
      START → agent_node
        ├─ search_knowledge → retrieve_node → agent_node（循环）
        ├─ call_tool        → tool_node      → agent_node（循环）
        └─ generate         → generate_node  → END
    """
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("agent", agent_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("tool", tool_node)
    workflow.add_node("generate", generate_node)

    # 设置入口
    workflow.set_entry_point("agent")

    # agent_node 的条件边
    workflow.add_conditional_edges(
        "agent",
        router,
        {
            "retrieve": "retrieve",
            "tool": "tool",
            "generate": "generate",
            "end": END,
        },
    )

    # retrieve → agent（循环：让 LLM 基于检索结果再次决策）
    workflow.add_edge("retrieve", "agent")

    # tool → agent（循环：让 LLM 基于工具结果再次决策）
    workflow.add_edge("tool", "agent")

    # generate → END
    workflow.add_edge("generate", END)

    return workflow


# ============================================================
# 编译并导出全局 Agent 实例
# ============================================================
agent_graph = build_agent_graph().compile()


async def run_agent(query: str, user_id: int = 1, session_id: str | None = None) -> dict:
    """
    运行 LangGraph Agent。

    Args:
        query: 用户问题
        user_id: 用户 ID
        session_id: 会话 ID

    Returns:
        {"answer": str, "docs": list, "graph_entities": list, "tool_results": list, "loop_count": int}
    """
    t0 = time.perf_counter()

    # R15 角色注入：查 users（sys_user_auth.role_code）取得 role → 注入 AgentState.user_role；
    # 查不到 → "student" 兜底 + warning 日志
    user_role = "student"
    try:
        from app.auth.service import get_user_info_by_id
        info = await get_user_info_by_id(int(user_id))
        if info is not None:
            user_role = info.role.value
        else:
            logger.warning(f"[Agent] 用户 {user_id} 不存在，user_role 兜底 student")
    except Exception as exc:
        logger.warning(f"[Agent] 获取用户角色失败，user_role 兜底 student: {type(exc).__name__}: {exc}")

    initial_state: AgentState = {
        "messages": [HumanMessage(content=query)],
        "docs": [],
        "graph_entities": [],
        "tool_results": [],
        "loop_count": 0,
        "next_action": "",
        "final_answer": "",
        "tool_name": "",
        "tool_args": {},
        "query_rewrite": "",
        "user_id": int(user_id),
        "user_role": user_role,
    }

    # 用 session_id 作为 thread_id，支持 Checkpoint（对话历史持久化）
    config = {"configurable": {"thread_id": session_id or "default"}}

    try:
        final_state = await agent_graph.ainvoke(initial_state, config)
    except Exception as exc:
        # T4-C2 末段：兜底文案不得泄异常类名（避免把本地逻辑缺陷当作下游故障暴露给用户）；
        # 真实异常类型只进服务端日志。
        logger.error(f"[Agent] 图执行异常: {type(exc).__name__}: {exc}")
        return {
            "answer": "AI 服务异常，请稍后重试",
            "docs": [],
            "graph_entities": [],
            "tool_results": [],
            "loop_count": 0,
            "latency_ms": int((time.perf_counter() - t0) * 1000),
        }

    latency_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(f"[Agent] 完成，耗时 {latency_ms}ms，循环 {final_state.get('loop_count', 0)} 次")

    return {
        "answer": final_state.get("final_answer", ""),
        "docs": final_state.get("docs", []),
        "graph_entities": final_state.get("graph_entities", []),
        "tool_results": final_state.get("tool_results", []),
        "loop_count": final_state.get("loop_count", 0),
        "latency_ms": latency_ms,
    }