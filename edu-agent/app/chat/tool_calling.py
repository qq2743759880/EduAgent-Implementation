# -*- coding: utf-8 -*-
"""
P8 补充：MCP 工具注入 LLM 对话（能力 10 联动）。

关键设计：
  1. 不使用外部 `mcp`/`langchain_mcp` 包（避免不存在的导入 API 反复 ImportError）；
     直接复用 P8 已落地的 `app.mcp.executor.call_tool`（stdio/SSE 双向验证通过）。
  2. 触发策略「启发式优先、LLM 意图识别兜底」：
     - 先用正则/关键词匹配已知工具（ping/add/echo/list_alphabet…），快速决策，避免额外 LLM 调用。
     - 启发式未命中时，可选择调用一次 LLM 工具意图识别 prompt（默认关闭，节省成本）。
     - R12：TOOL_DECISION_MODE=llm 时由 app.chat.tool_decision.decide_tool_plan 接管决策
       （LLM+真实 registry 工具清单→结构化 tool_plan，超时 TOOL_DECISION_TIMEOUT 秒→规则
       fallback+降级计数入日志）；默认 rule 保持本模块启发式（生产行为零变化）。
  3. 工具结果注入：把工具返回内容（text/result 字段）作为一段 tool 上下文提前拼入 system prompt 末尾，
     让生成答案时直接引用，既符合 MCP 标准的「tool 注入」语义，也对本地规则/远程 LLM 都生效。
  4. 任何工具调用异常（超时/网络问题）都不影响回答，工具层错误会写 degraded_reason 的 MCP_FAILED 子串并跳过。
"""
from __future__ import annotations

import json
import re
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.chat.schemas import MCPToolCallSummary
from app.common.logging import logger
from app.config import settings
from app.database import fetch_all
# CR-WNEXT2-toolcatalog-source：内置工具（executor 注册面）并入 LLM 可选清单的唯一事实源
from app.ai.permission_gate import REGISTERED_BUILTIN_TOOLS


# ============================================================
# 1. 工具加载：DB 中 enabled=1 且 yn=1 的 Server 下所有工具 + 内置工具
# ============================================================

# CR-WNEXT2-toolcatalog-source：内置工具描述（与 executor.py handler docstring 同源语义）。
# 内置工具在 mcp_tool 表无行，DB 查询天然缺位；此处补齐描述供意图识别/LLM 使用。
_BUILTIN_TOOL_DESCRIPTIONS: dict[str, str] = {
    "calculator":       "本地四则运算计算器：对两个数字做加减乘除/取模（op=add|sub|mul|div|mod）",
    "search_knowledge": "知识库检索：按关键词 q/query 查询已入库学习资料，返回相关片段（支持降级返回）",
    "knowledge_import": "知识库导入（写类，管理员专用）：登记导入任务并后台拉起既有导入管道（visibility=private|public）",
    # W-NEXT-WRITE1（CR-WRITETOOLS-001）：user_write 本人收藏，学生可用（manager 拒），无 HITL 卡
    "favorite_add":     "收藏课程（写本人数据）：收藏指定 series_id 的课程系列（服务端幂等，重复收藏返回原记录）",
}
@dataclass
class ToolMeta:
    tool_id: int
    server_id: int
    tool_name: str
    description: str
    input_schema_json: str | None
    category: str
    # --- 启发式用：工具名里出现的「意图识别关键词」 ---
    keywords: list[str] = field(default_factory=list)


async def list_enabled_tool_metas() -> list[ToolMeta]:
    """返回全部启用的工具元信息，供意图识别用。

    CR-WNEXT2-toolcatalog-source：DB（mcp_tool 表）之外，并入 executor 注册面内置工具
    （calculator/search_knowledge/knowledge_import）——内置工具无 DB 行，天然缺位，
    不并入则 LLM 可选清单永远不知道这些工具存在。写类工具 knowledge_import 也进清单，
    但放行仍由已接线的写类权限门（permission_gate/executor `_deny_if_write_class`）裁决。
    """
    rows = await fetch_all(
        "SELECT t.id AS tool_id, t.server_id, t.tool_name, t.description, t.input_schema_json, "
        "       s.server_code AS category "
        "FROM mcp_tool t "
        "JOIN mcp_server s ON s.id = t.server_id AND s.yn = 1 AND s.enabled = 1 "
        "WHERE t.yn = 1 "
        "ORDER BY s.id, t.id",
    )
    out: list[ToolMeta] = []
    seen_names: set[str] = set()
    for r in rows:
        name = str(r["tool_name"])
        seen_names.add(name.lower())
        meta = ToolMeta(
            tool_id=int(r["tool_id"]),
            server_id=int(r["server_id"]),
            tool_name=name,
            description=(r.get("description") or ""),
            input_schema_json=(r.get("input_schema_json") or None),
            category=str(r.get("category") or "default"),
            keywords=_suggest_keywords(name, r.get("description") or ""),
        )
        out.append(meta)
    # 内置工具并入（DB 同名去重，避免重复入清单）
    for bname in sorted(REGISTERED_BUILTIN_TOOLS):
        if bname in seen_names:
            continue
        desc = _BUILTIN_TOOL_DESCRIPTIONS.get(bname, "")
        out.append(ToolMeta(
            tool_id=0,
            server_id=0,
            tool_name=bname,
            description=desc,
            input_schema_json=None,
            category="builtin",
            keywords=_suggest_keywords(bname, desc),
        ))
    return out


def _suggest_keywords(name: str, desc: str) -> list[str]:
    """根据工具名/描述给出简单关键词建议，仅用于启发式匹配。"""
    base = {name.lower()}
    if "add" in name.lower() or "计算" in desc or "sum" in desc.lower():
        base.update({"加", "计算", "算术", "+", "求和", "add"})
    if "ping" in name.lower():
        base.update({"ping", "心跳", "连通性"})
    if "echo" in name.lower() or "repeat" in name.lower():
        base.update({"echo", "重复", "回显"})
    if "alphabet" in name.lower() or "字母" in desc:
        base.update({"字母", "字母表", "alphabet", "a-z", "A-Z"})
    if "search" in name.lower():
        base.update({"搜索", "search", "查"})
    if "import" in name.lower() or "导入" in desc:
        base.update({"导入", "import", "入库", "上传"})
    if "calc" in name.lower() or "calculator" in name.lower():
        base.update({"计算", "算", "calculator", "calc"})
    return list(base)


# ============================================================
# 2. 启发式工具 & 参数选择（轻、快、0 LLM 成本）
# ============================================================
@dataclass
class ToolPlanItem:
    tool: ToolMeta
    args: dict[str, Any]
    reason: str  # 触发来源（human 可懂）


def _parse_heuristic(query: str, tools: list[ToolMeta]) -> list[ToolPlanItem]:
    q = (query or "").strip()
    if not q:
        return []
    q_lower = q.lower()
    plans: list[ToolPlanItem] = []

    # 已知工具类型独立匹配
    by_lname = {t.tool_name.lower(): t for t in tools}

    # 1. add 数字 a+b / "计算 3+4" / 3加4 / a 加 b 等于多少
    add_tool = by_lname.get("add")
    if add_tool is not None:
        m = re.search(r"(-?\d+(?:\.\d+)?)\s*\+\s*(-?\d+(?:\.\d+)?)", q)
        if not m:
            m = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:加|plus|and)\s*(-?\d+(?:\.\d+)?)", q_lower)
        if not m and ("计算" in q or "算术" in q or "等于多少" in q or "结果是多少" in q):
            digits = re.findall(r"-?\d+(?:\.\d+)?", q)
            if len(digits) >= 2:
                try:
                    plans.append(ToolPlanItem(
                        tool=add_tool,
                        args={"a": _to_num(digits[0]), "b": _to_num(digits[1])},
                        reason=f"命中「计算类 N 个数字」取前两位: {digits[:2]}",
                    ))
                except Exception:
                    pass
        if m:
            try:
                plans.append(ToolPlanItem(
                    tool=add_tool,
                    args={"a": _to_num(m.group(1)), "b": _to_num(m.group(2))},
                    reason=f"命中加法表达式：{m.group(0)}",
                ))
            except Exception:
                pass

    # 2. ping 工具：用户说「ping」「心跳」「连通性」「检查 MCP」
    ping_tool = by_lname.get("ping")
    if ping_tool is not None and any(kw in q_lower for kw in ["ping", "心跳", "连通性", "mcp 健康", "工具健康"]):
        # ping 是无参探针工具，保留 args={}（与原实现等价）
        plans.append(ToolPlanItem(tool=ping_tool, args={}, reason="命中 ping 类关键词"))

    # 2b. W-NEXT-WRITE1（CR-WRITETOOLS-001）：favorite_add —— 「收藏课程 series_id 为 N」/
    #    「收藏系列 3」/「收藏 id=3 的课」（user_write 本人收藏）。仅在**明确给出系列 ID** 时触发
    #    （闲聊"我想收藏点东西"不误触发）；series_id 显式写法优先，次选「收藏+数字」紧凑写法。
    fav_tool = by_lname.get("favorite_add")
    if fav_tool is not None and "收藏" in q:
        fm = (re.search(r"series[_\s]*id\s*(?:为|是|=|:|：)?\s*(\d+)", q_lower)
              or re.search(r"(?:课程|系列|课)\s*(?:id|编号|号)?\s*(?:为|是|=|:|：)?\s*(\d+)", q_lower)
              or re.search(r"收藏[^\d]{0,8}(\d+)", q))
        if fm:
            try:
                plans.append(ToolPlanItem(
                    tool=fav_tool, args={"series_id": int(fm.group(1))},
                    reason=f"命中收藏类 series_id：{fm.group(1)}",
                ))
            except Exception:
                pass

    # 4. echo 工具：「echo xxx」「重复 xxx」「回显 xxx」→ echo(text=xxx)
    echo_tool = by_lname.get("echo")
    if echo_tool is not None:
        # 优先用原始 query 正则（大小写不敏感）提取内容，保留原大小写
        em_raw = re.search(r"echo\s+(.{1,40})", q, flags=re.IGNORECASE)
        if em_raw:
            payload = em_raw.group(1).strip()
            plans.append(ToolPlanItem(tool=echo_tool, args={"text": payload}, reason=f"命中 echo X：{payload}"))
        elif ("重复" in q or "回显" in q):
            pm = re.search(r"(?:重复|回显)[\"'“”]?(.{1,40}?)(?:[\"'“”]|重复|遍|回显|一下|内容|$)", q)
            if pm:
                payload = pm.group(1).strip()
                plans.append(ToolPlanItem(tool=echo_tool, args={"text": payload}, reason=f"命中「重复/回显」：{payload}"))
        elif q_lower.startswith("echo "):
            payload = q[5:].strip()[:100]
            plans.append(ToolPlanItem(tool=echo_tool, args={"text": payload}, reason=f"句首 echo：{payload}"))

    # 4. list_alphabet：「列字母表」「字母序列」「生成 A-Z」
    alpha_tool = by_lname.get("list_alphabet")
    if alpha_tool is not None and any(kw in q_lower for kw in ["字母", "字母表", "alphabet", "a-z", "a到z", "A-Z"]):
        nm = re.search(r"(?:字母|alphabet|sequence)[^\d]{0,6}(\d{1,3})", q_lower)
        n = 26
        if nm:
            try: n = max(1, min(200, int(nm.group(1))))
            except: n = 26
        elif re.search(r"(\d{1,3})\s*个", q_lower):
            try: n = max(1, min(200, int(re.search(r"(\d{1,3})\s*个", q_lower).group(1))))
            except: n = 26
        plans.append(ToolPlanItem(tool=alpha_tool, args={"n": n}, reason=f"命中字母表类，n={n}"))

    # 5. 兜底：按工具关键词逐条扫，每个工具最多 1 项
    already = {(p.tool.tool_name, tuple(sorted(p.args.items()))) for p in plans}
    for tm in tools:
        hit_kw = next((kw for kw in tm.keywords if kw and (kw in q_lower or kw in q)), None)
        if hit_kw is None:
            continue
        key = (tm.tool_name, tuple())
        if key in already:
            continue
        # 对无参数工具允许空 args 直接触发；其余工具若启发式未构建具体 args 则跳过（避免瞎传参报错）
        has_required = _schema_has_required(tm.input_schema_json)
        if has_required:
            continue
        # W-NEXT-CHATFLOW-001（CR-T11b-A Track B 修补）：关键词命中后若 args 仍为空，
        # 按工具名填充 _heuristic_arg_defaults 最小可执行 schema 示例——
        # knowledge_import → source_files=[{file_name, local_path}] + visibility，
        # calculator → a/b/op。LLM 传入的 args 非空时调用方覆盖（见下方 `plan.args or _heuristic_arg_defaults(...)`）。
        _default_args = _heuristic_arg_defaults(tm.tool_name)
        if _default_args:
            logger.info(
                f"[MCP-TC] 启发式 args 兜底填充：tool={tm.tool_name}"
                f" hit_kw={hit_kw} keys={list(_default_args.keys())}"
            )
        plans.append(ToolPlanItem(tool=tm, args=dict(_default_args), reason=f"关键词命中：{hit_kw}"))
        already.add(key)

    # 上限：MCP_TOOL_MAX_TRIES（默认 1 次）
    max_tries = max(1, int(getattr(settings, "MCP_TOOL_MAX_TRIES", 1) or 1))
    if len(plans) > max_tries:
        plans = plans[:max_tries]
    return plans


def _schema_has_required(input_schema_json: str | None) -> bool:
    if not input_schema_json:
        return False
    try:
        obj = json.loads(input_schema_json)
    except Exception:
        return False
    if isinstance(obj, dict) and isinstance(obj.get("required"), list) and len(obj["required"]) > 0:
        return True
    return False


def _to_num(s: str) -> int | float:
    s = s.strip()
    if "." in s:
        return float(s)
    try:
        return int(s)
    except Exception:
        return float(s)


# ============================================================
# 2.5 W-NEXT-CHATFLOW-001（CR-T11b-A 修补）：内置工具 schema 默认参数
#   启发式工具选择仅命中关键词即 `args={}`——写类内置工具（knowledge_import）挂起后
#   confirm 续流调 handler 必校验 `source_files` 非空 → ValueError → task +0。
#   双轨修复 - Track B（启发式层兜底）：关键词命中后按工具名填充最小可执行的
#   schema 示例参数。本默认值仅在 args 仍为空时填充，对 LLM/tool_decision 传来的
#   完整 args 不影响（先 fill, track A 覆盖会再次覆盖）；不改 chat 路径语义。
# ============================================================
_KNOWLEDGE_IMPORT_DEMO_LOCAL_PATH = (
    "E:/stu/project/stu/EduAgent实施手册/edu-agent/data/knowledge_uploads/"
    "1b6c1144230c.md"
)


def _heuristic_arg_defaults(tool_name: str) -> dict:
    """关键词命中且 plan.args 仍为空时，按工具名填充最小可执行 schema 示例。

    返回新 dict，调用方应按 `plan.args or _heuristic_arg_defaults(plan.tool.tool_name)`
    模式连接——保证 LLM 传入的非空 args 优先。"""
    n = (tool_name or "").strip().lower()
    if n == "knowledge_import":
        # 与 executor._knowledge_import_handler 同源：source_files 非空 list[dict]，
        # 含 file_name + 可解析的 local_path（in-root 文件，触发 pipeline_started=True）。
        # visibility 默认 private，不传则 handler 取 ctx/兜底 private。
        return {
            "source_files": [
                {
                    "file_name": "knowledge_import_demo.md",
                    "local_path": _KNOWLEDGE_IMPORT_DEMO_LOCAL_PATH,
                }
            ],
            "visibility": "private",
        }
    if n == "calculator":
        # 启发式默认占位（避免空 args 触发 calculator 字段校验）：a/b/op 最小示例。
        # 真实 _parse_heuristic 已用正则填 a/b（见上面分支）；此处仅作兜底。
        return {"a": 0, "b": 0, "op": "add"}
    return {}


# ============================================================
# 3. 主入口：run_chat_tool_calls → 返回 (summary列表, result注入片段, degraded_extra)
# ============================================================
async def run_chat_tool_calls(
    *,
    query: str,
    operator_user_id: int,
    tenant_id: str = "",
    trace_id: str = "",
    session_id: str | None = None,
    use_mcp_flag: bool = True,
    # CR-WNEXT2-hitl-graph-unreachable（方案②）：写类工具流层挂起的两个旋钮。
    #   hitl_decision：resume approve 续跑时传 True → 写类工具经 executor 批准执行（不挂起）；
    #   on_write_class_pending：graph_stream 注入的挂起回调 → HITL 开启时写类工具先挂起
    #     （发 pending_confirm 帧 + Redis 标记），不执行，等用户 confirm/reject 后同 thread_id 续跑。
    hitl_decision: bool | None = None,
    on_write_class_pending: Callable[[dict], Awaitable[bool]] | None = None,
    # W-NEXT-CHATFLOW-001（CR-T11b-A Track A 治本）：HITL 续流时从 Redis 缓存读出的
    # 首轮 pending_confirm.args，按 tool_name → dict 形式直接覆盖 _parse_heuristic 后的 plan.args。
    # 不再依赖 LLM 续流 generate 节点自主生成 tool_calls（CR-T11b-A 根因）。
    # 形式：{ tool_name: cached_args_dict, ... }；缺失的键默认走启发式 _heuristic_arg_defaults 兜底。
    pending_args_override: dict[str, dict] | None = None,
) -> tuple[list[MCPToolCallSummary], str, str | None]:
    """
    一轮问答内：分析 query → 选工具（启发式）→ 逐一调用 → 返回：
      1) summaries：给前端响应体 & 落库 chat_message 使用
      2) context_fragment：给 system prompt 追加一段「MCP 工具结果上下文」（空串表示没工具）
      3) degraded_extra：若整段 MCP 模块失败（DB/mcp 结构缺失），写一条降级原因给调用方拼 degraded_reason

    任何内部异常都吞掉并转 degraded_extra，保证不影响后续 RAG 生成。
    """
    summaries: list[MCPToolCallSummary] = []
    parts: list[str] = []
    degraded_extra: str | None = None

    if not use_mcp_flag or not getattr(settings, "USE_MCP_TOOL_CALLING", True):
        return summaries, "", None

    # W-NEXT-OTLP-001：executor 入口 span（disabled 模式 no-op 零开销；sync 友好不抛）
    try:
        from app.observability.otlp import trace_executor_entry
        trace_executor_entry(
            tool="mcp.dispatch",
            user_id=str(operator_user_id) if operator_user_id else None,
            session_id=session_id,
            extra={"query_len": len(query or "")},
        )
    except Exception:
        pass

    t0 = time.perf_counter()
    try:
        tools = await list_enabled_tool_metas()
    except Exception as exc:
        logger.warning(f"[MCP-TC] 加载启用工具列表失败：{type(exc).__name__}: {exc}")
        # degraded 会经 service/graph_stream 的 merged_deg 进用户可见的 done 帧 →
        # 只给稳定文案，异常类名只进 logger（同 T4-C2「兜底文案不泄内部类名」）
        return summaries, "", "MCP 工具列表加载失败（工具阶段已跳过）"

    if not tools:
        # 无工具：静默返回（不给 degraded，避免打扰正常 RAG 提示）
        return summaries, "", None

    # R12：TOOL_DECISION_MODE=llm → 图内 LLM 工具决策接管（query+真实 registry 工具清单
    # → 结构化 tool_plan）；超时/异常/不可解析 → 内部自动规则路由 fallback（现行为
    # _parse_heuristic），降级计数入日志（tool_decision._STATS）。
    # 默认 rule = 纯现行为（生产零变化）。
    decision_note = "rule"
    if str(getattr(settings, "TOOL_DECISION_MODE", "rule") or "rule").strip().lower() == "llm":
        from app.chat.tool_decision import decide_tool_plan

        dres = await decide_tool_plan(query, tools)
        plans = dres.plans
        decision_note = (
            f"llm({dres.latency_ms}ms)" if not dres.fallback
            else f"llm→rule fallback({dres.fallback_reason},{dres.latency_ms}ms)"
        )
    else:
        plans = _parse_heuristic(query, tools)
    if not plans:
        return summaries, "", None

    # 逐一调用
    from app.mcp import executor as _mcp_executor  # 延迟循环 import
    # W-NEXT-2 步骤2（T4-C1）：写类工具执行前过权限门 —— 与 graph 路径同源消费
    # permission_gate.gate_tool_call（禁两份拷贝）；角色解析惰性且只对写类触发，
    # 只读工具路径**零额外 DB 查询**（生产行为不变）。
    from app.ai.permission_gate import (
        build_denied_envelope,
        gate_tool_call,
        is_write_class,
        resolve_role,
    )

    _role_cache: list[str] = []

    async def _role() -> str:
        if not _role_cache:
            _role_cache.append(await resolve_role(operator_user_id))
        return _role_cache[0]

    calls_any = False
    success_any = False
    denied_any = False
    held_any = False  # CR-1 方案②：写类工具挂起待确认（未执行）
    for plan in plans:
        calls_any = True
        args_summary_raw = _truncate(str(plan.args), 200)
        start_ms = int(time.perf_counter() * 1000)

        # 写类工具：权限门 deny → 零 executor 调用（不执行、不落审计），ACI 三字段入 summary。
        # MCPToolCallSummary.status 只允许 success/error/timeout → 以 "error" 承载，信封放 result_summary。
        if is_write_class(plan.tool.tool_name):
            _tool_key = str(plan.tool.tool_name).strip().lower()
            _decision = gate_tool_call(await _role(), _tool_key)
            if not _decision.allowed:
                denied_any = True
                env = build_denied_envelope(await _role(), _tool_key, _decision)
                summaries.append(MCPToolCallSummary(
                    call_id=f"chat-denied-{start_ms}-{plan.tool.tool_name}",
                    tool_name=plan.tool.tool_name,
                    args_summary=args_summary_raw,
                    status="error",
                    latency_ms=0,
                    result_summary=_truncate(json.dumps(env, ensure_ascii=False), 400),
                ))
                parts.append(
                    f"## MCP 工具被权限门拦截（未执行）：{plan.tool.tool_name}\n"
                    f"- code: {env['code']}\n"
                    f"- message: {env['message']}\n"
                    f"- action_hint: {env['action_hint']}\n"
                    f"- 该操作**没有执行**：如实告知用户「操作已被安全拦截」，"
                    f"严禁声称已完成/已创建/已导入。\n"
                )
                continue

            # CR-WNEXT2-hitl-graph-unreachable（方案②）：HITL 开启且流式主路径
            # （graph_stream）注入了挂起回调时，写类工具在**流层**挂起 —— 不执行工具，
            # 由回调发 pending_confirm 帧 + 写 Redis 挂起标记；用户 confirm/reject 后
            # 以同 thread_id 重开续跑。graph 六节点无 interrupt 节点（图内挂起不可达），
            # 故由本回调承载，不依赖图 interrupt。resume approve（hitl_decision=True）
            # 时跳过挂起、放行到 executor 批准执行。
            if (
                on_write_class_pending is not None
                and hitl_decision is None
                and getattr(settings, "HITL_ENABLED", False)
            ):
                _pending_payload = {
                    "tool_name": plan.tool.tool_name,
                    "tool_key": _tool_key,
                    "role": await _role(),
                    "args": dict(plan.args or {}),
                    "operator_user_id": int(operator_user_id),
                    "tenant_id": str(tenant_id),
                    "session_id": str(session_id or ""),
                    "status": "awaiting_confirm",
                }
                _held = await on_write_class_pending(_pending_payload)
                if _held:
                    held_any = True
                    summaries.append(MCPToolCallSummary(
                        call_id=f"chat-hitl-{start_ms}-{plan.tool.tool_name}",
                        tool_name=plan.tool.tool_name,
                        args_summary=args_summary_raw,
                        status="error",
                        latency_ms=0,
                        result_summary=_truncate(json.dumps({
                            "status": "awaiting_confirm",
                            "tool_name": plan.tool.tool_name,
                            "message": "写类工具已挂起，等待人工确认（pending_confirm 帧）",
                            "thread_hint": "以同 thread_id 重开并 confirm/reject 续跑",
                        }, ensure_ascii=False), 400),
                    ))
                    parts.append(
                        f"## MCP 写类工具已挂起（未执行）：{plan.tool.tool_name}\n"
                        f"- 状态：等待人工确认（pending_confirm）\n"
                        f"- 该操作**没有执行**、**没有发生任何数据变更**；确认后才会执行。\n"
                    )
                    continue

        # W-NEXT-CHATFLOW-001（Track A 治本优先级最高）：HITL 续流时从 Redis 缓存读出
        # 的首轮 pending_confirm.args（按 tool_name）替换 plan.args —— 不再依赖 LLM 续流
        # generate 节点工具调用决策。priority:
        #   1) pending_args_override[plan.tool.tool_name]（Track A 缓存）→ 最高
        #   2) plan.args（Track B 启发式填充 + LLM 传入）→ 次之
        #   3) {} （无任何参数）→ 最末；这种情况不应走到 executor（应早被 permission_gate 拦）
        _resolved_args: dict = {}
        if pending_args_override:
            _resolved_args = dict(pending_args_override.get(plan.tool.tool_name) or {})
        if not _resolved_args:
            _resolved_args = dict(plan.args or {})
        if not _resolved_args:
            # 写类工具若仍空 args（极端场景），fallback 到 _heuristic_arg_defaults（最后兜底）
            _resolved_args = dict(_heuristic_arg_defaults(plan.tool.tool_name) or {})
        # 续流（hitl_decision=True）路径下，args 已来自缓存/启发式，不应再被空 args 反向短路
        if (
            hitl_decision
            and plan.tool.tool_name in (pending_args_override or {})
            and pending_args_override.get(plan.tool.tool_name)
        ):
            logger.info(
                f"[MCP-TC] HITL 续流 args 覆盖：tool={plan.tool.tool_name}"
                f" src=cached_pending source_keys={list(_resolved_args.keys())}"
            )

        try:
            # H1 闭环必须：内置工具(tool_id=0 的 knowledge_import/calculator/search_knowledge)
            # 经 chat 流式触发时**必须同时传 tool_name**——否则 executor._resolve_builtin_name
            # 因 `tool_id or not tool_name` 返回空串，跳过内置分支落到 registry 解析
            # tool_id=0/server_id=None → 抛 AppException「必须提供 tool_id 或 server_id+tool_name」
            # （SURFACED-1：HITL-FIX 后 admin confirm 写类工具零落库的根因）。
            resp = await _mcp_executor.call_tool(
                operator_user_id=int(operator_user_id),
                tenant_id=tenant_id,
                trace_id=trace_id or (f"mcp-chat-{int(start_ms)}"),
                tool_id=int(plan.tool.tool_id),
                tool_name=plan.tool.tool_name,
                args=_resolved_args,
                hitl_decision=hitl_decision,
            )
            latency = resp.latency_ms or max(0, int(time.perf_counter() * 1000) - start_ms)
            status_enum = resp.status.value if hasattr(resp.status, "value") else str(resp.status)
            se_norm = str(status_enum).strip().lower()
            if se_norm == "success":
                status_label: Any = "success"
                success_any = True
            elif se_norm == "timeout":
                status_label = "timeout"
            else:
                # 含 SKIPPED（HITL 待审批）——MCPToolCallSummary.status 只允许
                # success/error/timeout，"skipped" 会触发 Pydantic ValidationError 被外层
                # except 误记为「调用异常」，故统一归入 error（真实原因在 error_message/result_summary）。
                status_label = "error"
            result_sum = _truncate(_extract_result_text(resp), 400)
            summaries.append(MCPToolCallSummary(
                call_id=str(resp.call_id),
                tool_name=str(resp.tool_name),
                args_summary=args_summary_raw,
                status=status_label,
                latency_ms=latency,
                result_summary=result_sum,
            ))
            if status_label == "success":
                parts.append(
                    f"## MCP 工具执行结果：{plan.tool.tool_name}（原因：{plan.reason}）\n"
                    f"- 工具输入：{args_summary_raw}\n"
                    f"- 工具输出（请基于该结果回答用户问题，不要编造）：\n"
                    f"```\n{result_sum}\n```\n"
                )
            else:
                error_msg = _truncate(resp.error_message or "(unknown)", 300)
                parts.append(
                    f"## MCP 工具执行失败：{plan.tool.tool_name}（忽略，不要基于它编造答案）\n"
                    f"- 错误：{status_label} / {error_msg}\n"
                )
        except Exception as exc:
            tb = traceback.format_exc(limit=1).strip().splitlines()[-1:]
            logger.warning(f"[MCP-TC] 调用工具 {plan.tool.tool_name} 异常：{type(exc).__name__}: {exc}")
            latency = max(0, int(time.perf_counter() * 1000) - start_ms)
            summaries.append(MCPToolCallSummary(
                call_id=f"chat-fail-{start_ms}-{plan.tool.tool_name}",
                tool_name=plan.tool.tool_name,
                args_summary=args_summary_raw,
                status="error",
                latency_ms=latency,
                result_summary=f"Exception: {type(exc).__name__} ({_truncate(str(exc), 100)}) {tb}",
            ))
            degraded_extra = (degraded_extra + "；" if degraded_extra else "") + \
                             f"MCP 工具调用失败 {plan.tool.tool_name}（工具阶段已跳过）"

    if not calls_any:
        return summaries, "", degraded_extra
    # T4-C4 / W2-G6 幻觉检测（生成层诚实约束）：本轮存在工具调用但**无一成功**时，
    # 明确禁止完成态断言 —— 防「无工具调用佐证却声称已完成/已创建」（含被权限门拦截场景）。
    if not success_any:
        _not_executed_reasons = []
        if denied_any:
            _not_executed_reasons.append("其中包含被权限门拦截的写类操作")
        if held_any:
            _not_executed_reasons.append("其中包含等待人工确认的写类操作")
        parts.append(
            "\n## 系统诚实性约束（必须遵守）\n"
            "本轮所有工具调用**均未成功执行**"
            + (f"（{'；'.join(_not_executed_reasons)}）" if _not_executed_reasons else "")
            + "：**没有发生任何数据变更**。回答中严禁出现「已完成 / 已创建 / 已导入 / 已上架 / 已提交」"
            "等完成态断言；必须如实说明未执行成功的事实、原因（如权限不足/等待确认/工具失败）与可行的替代建议。\n"
        )
    total_ms = int((time.perf_counter() - t0) * 1000)
    header = (
        f"\n\n# MCP 工具上下文（决策器={decision_note}，本轮共 {len(plans)} 次调用，总耗时 {total_ms} ms）\n"
        "以下内容来自 EduAgent MCP Server 的真实工具调用结果；回答时请直接引用这些结果，并在结果处声明「工具 X 返回…」，不要自行编造数值。\n"
    )
    return summaries, (header + "\n".join(parts) if parts else ""), degraded_extra


def _extract_result_text(resp) -> str:
    if resp.content_text:
        return str(resp.content_text)
    if resp.result is None:
        return ""
    try:
        return json.dumps(resp.result, ensure_ascii=False)
    except Exception:
        return str(resp.result)


def _truncate(s: str, n: int) -> str:
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


# ============================================================
# 4. Prompt 注入：给 system prompt 尾部拼 MCP 工具上下文
# ============================================================
def inject_mcp_into_system_prompt(system_prompt: str, mcp_context: str) -> str:
    """把 tool 上下文拼到 system prompt 末尾（仅当上下文非空）。"""
    if not mcp_context:
        return system_prompt
    return (system_prompt or "").rstrip() + "\n\n" + mcp_context.strip()
