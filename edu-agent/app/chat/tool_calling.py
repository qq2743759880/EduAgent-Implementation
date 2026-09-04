# -*- coding: utf-8 -*-
"""
P8 补充：MCP 工具注入 LLM 对话（能力 10 联动）。

关键设计：
  1. 不使用外部 `mcp`/`langchain_mcp` 包（避免不存在的导入 API 反复 ImportError）；
     直接复用 P8 已落地的 `app.mcp.executor.call_tool`（stdio/SSE 双向验证通过）。
  2. 触发策略「启发式优先、LLM 意图识别兜底」：
     - 先用正则/关键词匹配已知工具（ping/add/echo/list_alphabet…），快速决策，避免额外 LLM 调用。
     - 启发式未命中时，可选择调用一次 LLM 工具意图识别 prompt（默认关闭，节省成本）。
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
from typing import Any

from app.chat.schemas import MCPToolCallSummary
from app.common.logging import logger
from app.config import settings
from app.database import fetch_all


# ============================================================
# 1. 工具加载：DB 中 enabled=1 且 yn=1 的 Server 下所有工具
# ============================================================
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
    """返回全部启用的 MCP 工具元信息，供意图识别用。"""
    rows = await fetch_all(
        "SELECT t.id AS tool_id, t.server_id, t.tool_name, t.description, t.input_schema_json, "
        "       s.server_code AS category "
        "FROM mcp_tool t "
        "JOIN mcp_server s ON s.id = t.server_id AND s.yn = 1 AND s.enabled = 1 "
        "WHERE t.yn = 1 "
        "ORDER BY s.id, t.id",
    )
    out: list[ToolMeta] = []
    for r in rows:
        name = str(r["tool_name"])
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
        plans.append(ToolPlanItem(tool=ping_tool, args={}, reason="命中 ping 类关键词"))

    # 3. echo 工具：「echo xxx」「重复 xxx」「回显 xxx」→ echo(text=xxx)
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
        plans.append(ToolPlanItem(tool=tm, args={}, reason=f"关键词命中：{hit_kw}"))
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

    t0 = time.perf_counter()
    try:
        tools = await list_enabled_tool_metas()
    except Exception as exc:
        logger.warning(f"[MCP-TC] 加载启用工具列表失败：{type(exc).__name__}: {exc}")
        return summaries, "", f"MCP 工具列表加载失败({type(exc).__name__})"

    if not tools:
        # 无工具：静默返回（不给 degraded，避免打扰正常 RAG 提示）
        return summaries, "", None

    plans = _parse_heuristic(query, tools)
    if not plans:
        return summaries, "", None

    # 逐一调用
    from app.mcp import executor as _mcp_executor  # 延迟循环 import

    calls_any = False
    for plan in plans:
        calls_any = True
        args_summary_raw = _truncate(str(plan.args), 200)
        start_ms = int(time.perf_counter() * 1000)
        try:
            resp = await _mcp_executor.call_tool(
                operator_user_id=int(operator_user_id),
                tenant_id=tenant_id,
                trace_id=trace_id or (f"mcp-chat-{int(start_ms)}"),
                tool_id=int(plan.tool.tool_id),
                args=dict(plan.args or {}),
            )
            latency = resp.latency_ms or max(0, int(time.perf_counter() * 1000) - start_ms)
            status_enum = resp.status.value if hasattr(resp.status, "value") else str(resp.status)
            se_norm = str(status_enum).strip().lower()
            if se_norm == "success":
                status_label: Any = "success"
            elif se_norm == "timeout":
                status_label = "timeout"
            elif se_norm == "skipped":
                status_label = "skipped"
            else:
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
                             f"MCP 工具调用失败 {plan.tool.tool_name}({type(exc).__name__})"

    if not calls_any:
        return summaries, "", degraded_extra
    total_ms = int((time.perf_counter() - t0) * 1000)
    header = (
        f"\n\n# MCP 工具上下文（本轮共 {len(plans)} 次调用，总耗时 {total_ms} ms）\n"
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
