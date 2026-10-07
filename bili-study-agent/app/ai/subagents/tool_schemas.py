# -*- coding: utf-8 -*-
"""R12 exact-pin：子代理工具参数 schema（逐字段精确绑定）+ 模糊调用结构化拒绝。

对标 KB 精读 F-C02-002-hermes 工具调用范式（.ai-hub/plans/kb-deep-1-orchestration.md §5 /
TOP10 #9）：工具名/参数逐字段精确绑定，拒绝 LLM 自由发挥的模糊调用——

- 每个工具的参数 = 白名单字段 × 精确类型 × 必填性 × 取值域，绑定权威是
  ``app/ai/graph.py::_build_tool_services`` 各服务闭包真实读取的字段（本模块不改闭包、
  不改检索/记忆主链，只在校验层把「闭包实际认什么字段」显式化为可机验契约）。
- ``validate_tool_args`` 纯函数可单测；违规 → ``structured_rejection`` 产出
  ``EXACT_PIN_REJECTED`` 结构化错误（回灌 LLM 自纠错 + 记账入 artifact + 连续超限
  fail-closed 终止），杜绝「拼写错字段静默落默认值」「缺参延迟到服务层才报错」两类模糊调用。
- 对 ChatDev tool_spec 同构判据（KB §7 判据 4）：schema 独立成模块，契约测试直接引用。

本模块为纯函数/数据结构，不依赖 LLM/DB/Redis，可直接单测。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

__all__ = [
    "TOOL_ARG_SCHEMAS",
    "ToolArgSchema",
    "schema_hint",
    "structured_rejection",
    "validate_tool_args",
]

# 连续模糊调用拒绝上限：达到即 fail-closed 终止本子代理会话（结构化错误作 summary 上交主上下文）
MAX_CONSECUTIVE_VAGUE_REJECTS = 2

# 结构化错误码（artifact / 测试断言用）
ERROR_CODE = "EXACT_PIN_REJECTED"


@dataclass(frozen=True)
class ToolArgSchema:
    """一个工具的精确参数契约（字段 × 类型 × 必填 × 域）。"""

    required: tuple[tuple[str, type], ...] = ()
    optional: tuple[tuple[str, type], ...] = ()
    # 字段取值域（可选）：field -> (min, max)，仅对 int 生效
    int_domain: dict[str, tuple[int, int]] = field(default_factory=dict)
    # 字段说明（结构化错误回灌 LLM 用，ACI 当 HCI）
    field_docs: dict[str, str] = field(default_factory=dict)

    def fields_doc(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for name, typ in self.required:
            out[name] = f"{typ.__name__}（必填）{self.field_docs.get(name, '')}".strip()
        for name, typ in self.optional:
            out[name] = f"{typ.__name__}（可选）{self.field_docs.get(name, '')}".strip()
        return out


def _is_str(v: object) -> bool:
    return isinstance(v, str)


def _is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


_TYPE_CHECKS: dict[type, callable] = {str: _is_str, int: _is_int, dict: lambda v: isinstance(v, dict)}

# ── 绑定权威：graph._build_tool_services 各闭包真实消费的字段（逐字段核对，勿凭记忆增删）──
# search_knowledge(args)：只读 args["q"]；检索参数（top_k/use_hyde 等）由 sixnode_retrieval_params()
#   统一供参、不从 args 取 → 除 q 外任何字段都不被服务消费 = 模糊字段，一律拒。
# recall_memory(args)：读 args["q"]（"query" 别名是闭包的容错而非契约，exact-pin 只认 q）+ args["top_k"]。
# recall_profile(args)：读 args["profile_query"]（"q" 别名/空默认同上不作为契约）+ args["top_k"]。
# call_tool(args)：读 args["tool_name"] + args["args"]（嵌套 MCP 工具参数整体透传 executor，
#   嵌套内 schema 校验由 mcp.executor.registry 兜底——未知工具/坏参在下游 fail-closed，双层防御）。
TOOL_ARG_SCHEMAS: dict[str, ToolArgSchema] = {
    "search_knowledge": ToolArgSchema(
        required=(("q", str),),
        field_docs={"q": "用户问题原文（问题本体，不要改写/扩展/拼接任务串）"},
    ),
    "recall_memory": ToolArgSchema(
        required=(("q", str),),
        optional=(("top_k", int),),
        int_domain={"top_k": (1, 50)},
        field_docs={"q": "记忆召回查询词（问题本体）", "top_k": "召回条数上限"},
    ),
    "recall_profile": ToolArgSchema(
        required=(("profile_query", str),),
        optional=(("top_k", int),),
        int_domain={"top_k": (1, 50)},
        field_docs={"profile_query": "画像召回查询词（学习诉求本体）", "top_k": "召回条数上限"},
    ),
    "call_tool": ToolArgSchema(
        required=(("tool_name", str),),
        optional=(("args", dict),),
        field_docs={"tool_name": "MCP registry 工具名（未知工具会被 executor 拒绝）",
                    "args": "嵌套 MCP 工具参数对象"},
    ),
}


def schema_hint(tool_name: str) -> dict[str, str] | None:
    """给 LLM 的 schema 提示（结构化错误内嵌；未知工具返 None 由调用方拼白名单）。"""
    sch = TOOL_ARG_SCHEMAS.get(tool_name)
    return sch.fields_doc() if sch else None


def validate_tool_args(tool_name: str, args: object) -> tuple[bool, str, str]:
    """exact-pin 校验：工具名已过白名单后，对其 args 逐字段精确校验。

    Returns:
        (ok, reason, detail)——ok=True 时 reason=""；否则 reason ∈
        {not_an_object, missing_required, unknown_field, wrong_type, out_of_domain}，
        detail 为人读中文描述（回灌 LLM + 记账 artifact）。
    """
    sch = TOOL_ARG_SCHEMAS.get(tool_name)
    if sch is None:  # 未登记 schema 的工具：不在 exact-pin 管辖内（防御性放行，调用方白名单已把关）
        return True, "", ""
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return False, "not_an_object", f"args 必须是对象，实际 {type(args).__name__}"

    known = {name: typ for name, typ in list(sch.required) + list(sch.optional)}
    for name in args:
        if name not in known:
            return False, "unknown_field", (
                f"未知字段 {name!r}（exact-pin 拒绝模糊字段）；{tool_name} 恰好接受: {sorted(known)}")
    for name, typ in sch.required:
        if name not in args or args[name] is None:
            return False, "missing_required", f"缺少必填字段 {name!r}；schema: {sch.fields_doc()}"
    for name, typ in known.items():
        v = args.get(name)
        if v is None:
            continue
        check = _TYPE_CHECKS.get(typ)
        if check is None or not check(v):
            return False, "wrong_type", f"字段 {name!r} 类型必须 {typ.__name__}，实际 {type(v).__name__}"
        if typ is int and name in sch.int_domain:
            lo, hi = sch.int_domain[name]
            if not (lo <= v <= hi):
                return False, "out_of_domain", f"字段 {name!r} 取值须在 [{lo},{hi}]，实际 {v}"
    for name, typ in sch.required:
        if typ is str and isinstance(args.get(name), str) and not args[name].strip():
            return False, "missing_required", f"必填字段 {name!r} 为空白串（须为有效查询词）"
    return True, "", ""


def structured_rejection(
    *,
    reason: str,
    detail: str,
    claimed_tool: object = None,
    allowed_tools: list[str] | tuple[str, ...] = (),
    schema: dict[str, str] | None = None,
) -> str:
    """构造 EXACT_PIN_REJECTED 结构化错误（回灌 LLM 自纠错 / fail-closed 上交主上下文）。"""
    payload: dict[str, object] = {
        "error_code": ERROR_CODE,
        "reason": reason,
        "detail": detail,
    }
    if claimed_tool is not None:
        payload["claimed_tool"] = str(claimed_tool)
    if allowed_tools:
        payload["allowed_tools"] = list(allowed_tools)
    if schema:
        payload["args_schema"] = schema
    payload["instruction"] = "请严格按 allowed_tools/args_schema 重新输出决策 JSON，或输出最终 JSON {\"tool\": null, \"final\": \"...\"}"
    return json.dumps(payload, ensure_ascii=False)
