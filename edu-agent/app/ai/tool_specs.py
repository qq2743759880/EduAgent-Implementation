# -*- coding: utf-8 -*-
"""
task27 tool_specs 规范 + prompt 精简 + prompt caching（R5 缓存三层组织联动）。

核心目标（tech-source-audit.md §二/MCP 一节：差描述浪费 40% 时间 → 五要素规范；R5 缓存三层组织）：
  1. ToolSpec 五要素：name / description / input_schema / risk(read|write) /
     parallel_safe / timeout_s / admin_only。
     description 遵循「做什么 + 何时用/何时不用 + 参数域 + 返回结构 + 示例 + 副作用/幂等」规范，
     过长的描述在进入 prompt 前裁剪，保证前缀 token 受控。
  2. 稳定排序：工具清单按 name 排序，同输入前缀逐字节一致 → 缓存前缀稳定命中。
  3. 访问控制：admin_only 工具不进入普通用户决策 prompt；仅 is_admin=True 时注入。
  4. 前缀 token 预算：system（精简决策规则）+ 工具清单 ≤ TOOL_PREFIX_BUDGET(默认 300) token。
  5. 并行执行：parallel_safe 且无参数依赖的工具可 asyncio.gather 并发（GWT③）。

本模块为纯函数 / 数据结构，不依赖外部 LLM / Redis，可直接单测。
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal

from app.ai.compaction import estimate_tokens

# task-C2：缓存前缀达标配置（对齐 P7）。优先读 settings，导入失败回退默认，避免循环依赖。
try:  # pragma: no cover - 配置模块始终可用
    from app.config import settings as _settings

    TOOL_DEFERRED_MODE: bool = bool(getattr(_settings, "TOOL_DEFERRED_MODE", True))
    _PROMPT_CACHE_MIN_TOKENS: int = int(getattr(_settings, "PROMPT_CACHE_MIN_TOKENS", 1024))
except Exception:  # pragma: no cover
    TOOL_DEFERRED_MODE = True
    _PROMPT_CACHE_MIN_TOKENS = 1024

__all__ = [
    "ToolSpec",
    "DECISION_SYSTEM_PROMPT",
    "stable_sorted_specs",
    "specs_for_access",
    "build_decision_prefix",
    "measure_prefix_tokens",
    "make_spec",
    "specs_from_metas",
    "run_parallel_tools",
    "SCHEMA_REGISTRY",
    "register_spec",
    "expand_schema",
    "build_tool_expansion_message",
    "TOOL_DEFERRED_MODE",
]

# 前端（可缓存静态前缀）token 预算上限：system + 工具清单（GWT①）
TOOL_PREFIX_BUDGET = 300
# 单条工具进入 prompt 的描述最长字符（超长裁剪，保证前缀预算）
_MAX_DESC_CHARS = 160
# 决策前缀桩用的稳定摘要最长字符（与完整 description 解耦：description 被体检改写不改桩，对齐 Glean 静态优先）
_MAX_SUMMARY_CHARS = 48


def _first_sentence(text: str, limit: int = _MAX_SUMMARY_CHARS) -> str:
    """取首句（以中英文句号/分号/冒号截断）作为稳定摘要，超长截断。

    与完整 description 解耦：description 被 task95 description_reviewer 重写时，
    仅当首句变化才影响决策前缀桩，绝大多数 schema 变更不影响前缀字节（AC2）。"""
    if not text:
        return ""
    for sep in ("。", ".", "；", ";", "：", ":"):
        idx = text.find(sep)
        if 0 < idx < len(text):
            text = text[: idx + 1]
            break
    text = text.strip()
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


@dataclass(frozen=True)
class ToolSpec:
    """工具规范五要素（risk/parallel_safe/timeout_s/admin_only 为增强字段）。

    description 规范（五要素描述）：
      做什么 → 触发该工具的具体任务；
      何时用/何时不用 → 边界（避免误触发）；
      参数域 → 要求键及取值范围；
      返回结构 → 稳定字段描述；
      示例 → 一个典型 args；
      副作用/幂等 → 是否写库、是否可安全重复调用。
    summary：决策前缀桩用的稳定一句话摘要（与 description 解耦，保前缀字节稳定）。
    """

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    risk: Literal["read", "write"] = "read"
    parallel_safe: bool = False
    timeout_s: float = 30.0
    admin_only: bool = False
    summary: str = ""

    def __post_init__(self) -> None:
        # 未显式给 summary → 用 description 首句派生（稳定、解耦完整描述）
        if not self.summary:
            object.__setattr__(self, "summary", _first_sentence(self.description))

    def to_prompt_entry(self, *, deferred: bool = False) -> dict:
        """构建 prompt 项。

        - deferred=True（默认，对齐 Claude defer_loading）：只放 tool_name + summary，
          不含 input_schema → 工具 schema 变更不影响前缀字节，前缀稳定可缓存（AC2/AC3）。
        - deferred=False（full 模式，供 A/B 契约测试）：保留完整 description + input_schema。
        """
        if deferred:
            return {"tool_name": self.name, "description": self.summary}
        desc = (self.description or "").strip()
        if len(desc) > _MAX_DESC_CHARS:
            desc = desc[: _MAX_DESC_CHARS - 3] + "..."
        return {
            "tool_name": self.name,
            "description": desc,
            "input_schema": self.input_schema,
        }


# ------------------------------------------------------------
# 精简决策系统 prompt（规则表化，≤预算可与工具清单共享 300 token）
#   替换原 agent.py 冗长（约 800 token）的 AGENT_DECISION_PROMPT，实现 prompt 精简。
# ------------------------------------------------------------
DECISION_SYSTEM_PROMPT = (
    "你是EduAgent意图决策器，只输出一个JSON，无markdown。规则(按优先级)："
    "1 学科知识→need_search=true，query_rewrite提取检索词；"
    "2 可调工具→need_search=false，tool_plan=[{tool_name,args}]；"
    "3 学习建议→need_search=false，answer_direct引导；"
    "4 闲聊→need_search=false，answer_direct直接答。"
    "输出:{\"need_search\":bool,\"query_rewrite\":\"\",\"tool_plan\":[],\"answer_direct\":\"\"}"
)

# 内置工具示例规范（教育问答场景；真实工具可经 specs_from_metas 由 MCP 元数据映射）
BUILTIN_TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="calculator",
        description="四则/取模计算。何时用:纯数值运算;不用:解释概念。参数:a,b,op(add/sub/mul/div/mod)。返回:{result}。副作用:无,幂等。",
        input_schema={
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}, "op": {"type": "string"}},
            "required": ["a", "b", "op"],
        },
        risk="read",
        parallel_safe=True,
        timeout_s=10.0,
    ),
    ToolSpec(
        name="web_search",
        description="实时网络搜索。何时用:查实时/最新信息;不用:学科常识。参数:q。返回:{hits:[{title,snippet,url}]}。副作用:无,幂等。",
        input_schema={"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
        risk="read",
        parallel_safe=True,
        timeout_s=20.0,
    ),
    ToolSpec(
        name="user_profile_lookup",
        description="读取用户画像/记忆偏好。何时用:需个性化建议。参数:user_id。返回:{profile}。副作用:只读,幂等。",
        input_schema={"type": "object", "properties": {"user_id": {"type": "integer"}}, "required": ["user_id"]},
        risk="read",
        parallel_safe=True,
        timeout_s=15.0,
    ),
    ToolSpec(
        name="code_runner",
        description="执行用户提供的代码片段并返回 stdout。何时用:运行/调试代码;不用:解释语法。参数:code,language。返回:{stdout,exit_code}。副作用:沙箱执行,非幂等,勿并行。",
        input_schema={
            "type": "object",
            "properties": {"code": {"type": "string"}, "language": {"type": "string"}},
            "required": ["code"],
        },
        risk="write",
        parallel_safe=False,
        timeout_s=30.0,
    ),
    ToolSpec(
        name="admin_user_impersonate",
        description="管理员以指定用户视角访问（内部运维）。何时用:管理员排查用户问题;不用:普通用户查询。参数:target_user_id,target_session_id。返回:{ok}。副作用:写审计,非幂等。",
        input_schema={
            "type": "object",
            "properties": {"target_user_id": {"type": "integer"}, "target_session_id": {"type": "string"}},
            "required": ["target_user_id"],
        },
        risk="write",
        parallel_safe=False,
        timeout_s=30.0,
        admin_only=True,
    ),
    ToolSpec(
        name="admin_broadcast_message",
        description="管理员向全体/指定班级广播消息（内部运营）。何时用:管理员群发通知;不用:普通用户发消息。参数:cohort_id,content。返回:{ok,sent}。副作用:写消息,非幂等。",
        input_schema={
            "type": "object",
            "properties": {"cohort_id": {"type": "integer"}, "content": {"type": "string"}},
            "required": ["content"],
        },
        risk="write",
        parallel_safe=False,
        timeout_s=30.0,
        admin_only=True,
    ),
)

# ------------------------------------------------------------
# 稳定排序 + 访问过滤
# ------------------------------------------------------------
def stable_sorted_specs(specs: list[ToolSpec] | tuple[ToolSpec, ...]) -> list[ToolSpec]:
    """按 name 稳定排序（同输入输出确定 → 前缀逐字节一致，缓存命中）。"""
    return sorted(specs, key=lambda s: s.name)


def specs_for_access(specs: list[ToolSpec] | tuple[ToolSpec, ...], *, is_admin: bool = False) -> list[ToolSpec]:
    """访问过滤：admin_only 工具仅 is_admin=True 时可见（GWT③ 普通用户不注入）。"""
    return [s for s in specs if not s.admin_only or is_admin]


# ------------------------------------------------------------
# 工具 schema 注册表（defer_loading 数据源）：name -> 完整 ToolSpec（含 input_schema）
#   决策前缀只放 name+summary（桩），schema 被 LLM 选中才由执行器 expand_schema 展开，
#   展开结果进「后续请求消息」而非前缀 → 前缀字节永不含 schema，稳定可缓存（AC2/AC3）。
# ------------------------------------------------------------
SCHEMA_REGISTRY: dict[str, ToolSpec] = {}


def register_spec(spec: ToolSpec) -> ToolSpec:
    """把完整 ToolSpec 登记进 schema 注册表（供 expand_schema 按需展开）。返回 spec 本身。"""
    SCHEMA_REGISTRY[spec.name] = spec
    return spec


def expand_schema(name: str) -> ToolSpec | None:
    """按 name 从注册表取完整 schema（含 input_schema）。

    LLM 决策选中工具 X 后，执行器调用本函数拿到完整 schema 注入后续请求消息，
    而非写进决策前缀 → 前缀字节稳定（对齐 Claude defer_loading）。
    """
    return SCHEMA_REGISTRY.get(name)


def build_tool_expansion_message(name: str) -> dict | None:
    """为被选中工具 X 构造「完整 schema 展开」消息（进后续请求，不进前缀）。

    返回 role=system 的消息，内容为工具 X 的完整 name/summary/description/input_schema。
    若注册表无该工具返回 None（调用方退化到不注入，由真实 MCP 兜底）。
    """
    spec = expand_schema(name)
    if spec is None:
        return None
    payload = {
        "tool_name": spec.name,
        "description": spec.description,
        "input_schema": spec.input_schema,
    }
    return {"role": "system", "content": "工具调用 schema（按需展开）：\n" + json.dumps(payload, ensure_ascii=False)}


# 内置规范登记进注册表（默认 deferred 桩的数据源）
for _s in BUILTIN_TOOL_SPECS:
    register_spec(_s)


# ------------------------------------------------------------
# 前缀构建 + token 测量（GWT①：system+工具清单 ≤300 且稳定）
# ------------------------------------------------------------
def build_decision_prefix(
    specs: list[ToolSpec] | tuple[ToolSpec, ...],
    *,
    is_admin: bool = False,
    budget: int = TOOL_PREFIX_BUDGET,
    system_prompt: str = DECISION_SYSTEM_PROMPT,
    deferred: bool | None = None,
) -> str:
    """构建可缓存决策前缀：{系统决策规则 + 工具清单}。

    - 先按 name 稳定排序，再按访问控制过滤（保证字节确定）。
    - deferred 默认 TOOL_DEFERRED_MODE（True）：工具桩只含 tool_name + summary，
      不含 input_schema → 工具增删/schema 变更不影响既有桩字节（AC2）。
    - 若超预算，进一步裁剪工具描述（contract：同输入前缀始终逐字节一致）。
    - 返回的字符串即完整 system content，直接作为 LLM system 消息可命中前缀缓存。
    """
    if deferred is None:
        deferred = TOOL_DEFERRED_MODE
    visible = specs_for_access(stable_sorted_specs(specs), is_admin=is_admin)
    header = (system_prompt or "").strip() + "\n## 可用 MCP 工具\n"
    entries = [s.to_prompt_entry(deferred=deferred) for s in visible]
    prefix = header + json.dumps(entries, ensure_ascii=False)

    # 预算裁剪：只在确实超限时缩短工具描述（确定性：固定截断到前缀 token 预算）
    if estimate_tokens(prefix) > budget and visible:
        compact = _compact_tools_in_budget(visible, budget, header, deferred=deferred)
        prefix = header + json.dumps(compact, ensure_ascii=False)
    return prefix


def _compact_tools_in_budget(visible: list[ToolSpec], budget: int, header: str, *, deferred: bool) -> list[dict]:
    """逐级收敛压缩工具清单直至前缀 ≤ budget（确定性、幂等、逐字节稳定）。

    固定顺序（保证同输入结果确定）：
      1) 每条 description 缩短为保留 name + 首句（≤40 字）；
      2) 仍超预算则逐条移除 input_schema（决策前缀只需意图判别，参数结构可缺省）；
      3) 仍超预算则进一步压缩 description 至超短（兜底），直至无可压缩。
    决策前缀是为 LLM 做「意图分类/选工具」，不承载真实 schema 校验（执行期由 MCP
    兜底校验），故超预算时裁剪 schema 是合理的 token 精简且不破坏契约。
    """
    entries = [s.to_prompt_entry(deferred=deferred) for s in visible]
    cur = header + json.dumps(entries, ensure_ascii=False)

    def _render() -> str:
        return header + json.dumps(entries, ensure_ascii=False)

    # 阶段 1：逐条把 description 缩短为保留首句（≤ 40 字）
    for e in entries:
        if estimate_tokens(cur) <= budget:
            break
        desc = e.get("description") or ""
        if len(desc) > 40:
            e["description"] = desc[:37] + "..."
            cur = _render()
    # 阶段 2：仍超预算则逐条移除 input_schema（仅 full 模式含，deferred 模式已无）
    if not deferred:
        for e in entries:
            if estimate_tokens(cur) <= budget:
                break
            if "input_schema" in e:
                e.pop("input_schema")
                cur = _render()
    # 阶段 3：仍超预算则进一步压缩 description（兜底）
    for e in entries:
        if estimate_tokens(cur) <= budget:
            break
        desc = e.get("description") or ""
        if len(desc) > 15:
            e["description"] = desc[:12] + "..."
            cur = _render()
    return entries


def measure_prefix_tokens(prefix: str) -> int:
    """测量前缀 token（复用 compaction 估算，保守偏大）。"""
    return estimate_tokens(prefix)


# ------------------------------------------------------------
# 元数据映射：任意 tool meta 对象 → ToolSpec（默认值兜底）
# ------------------------------------------------------------
def make_spec(
    name: str,
    *,
    description: str = "",
    input_schema: dict[str, Any] | None = None,
    risk: str = "read",
    parallel_safe: bool = False,
    timeout_s: float = 30.0,
    admin_only: bool = False,
) -> ToolSpec:
    """构造 ToolSpec（未知工具元数据映射的统一入口，risk 兜底 read）。"""
    return ToolSpec(
        name=name,
        description=description or "",
        input_schema=input_schema or {},
        risk=("write" if risk == "write" else "read"),
        parallel_safe=bool(parallel_safe),
        timeout_s=float(timeout_s),
        admin_only=bool(admin_only),
    )


def specs_from_metas(tool_metas: list[Any] | None) -> list[ToolSpec]:
    """把任意 tool meta 列表（MCPToolItem 等）映射为 ToolSpec。

    内置同名工具优先用内置规范（含 admin_only/parallel_safe），否则用元数据兜底默认。
    """
    builtin = {s.name: s for s in BUILTIN_TOOL_SPECS}
    specs: list[ToolSpec] = []
    named: set[str] = set()
    for m in (tool_metas or []):
        name = str(getattr(m, "tool_name", None) or getattr(m, "name", "") or "unknown").strip()
        if not name or name in named:
            continue
        named.add(name)
        if name in builtin:
            specs.append(builtin[name])
            continue
        desc = str(getattr(m, "description", None) or "")
        schema = getattr(m, "input_schema_json", None) or getattr(m, "input_schema", None) or {}
        if isinstance(schema, str):
            try:
                schema = json.loads(schema)
            except Exception:
                schema = {}
        spec = make_spec(name, description=desc, input_schema=schema if isinstance(schema, dict) else {})
        register_spec(spec)  # 登记进 schema 注册表（defer_loading 数据源）
        specs.append(spec)
    return specs


# ------------------------------------------------------------
# 并行执行（GWT③）：parallel_safe 且无参数依赖 → asyncio.gather 并发
# ------------------------------------------------------------
async def run_parallel_tools(
    tool_plan: list[dict],
    spec_of: Callable[[str], ToolSpec],
    call_tool: Callable[[str, dict], Awaitable[Any]],
) -> list[dict]:
    """执行工具计划：并行 safe 项，串行非 safe / 缺规范项。

    - spec_of(name) → ToolSpec（提供 parallel_safe）；缺失按 parallel_safe=False 串行。
    - call_tool(name, args) → 单工具异步执行体（调用方注入，便于测试/真实 MCP executor）。
    - 返回与输入 tool_plan 顺序一致的结果摘要列表 [{tool_name,status,result_summary,latency_ms,parallel}]。
    """
    groups: list[dict] = []  # 分组：group["run"]=[(idx,item)]，同组并发；串行项单元素组
    serial: list[dict] = []
    parallel: list[dict] = []
    for idx, item in enumerate(tool_plan):
        name = str(item.get("tool_name") or "").strip()
        entry = {"idx": idx, "item": item, "name": name}
        try:
            spec = spec_of(name) if name else None
            safe = bool(spec and spec.parallel_safe)
        except Exception:
            safe = False
        if safe:
            parallel.append(entry)
        else:
            serial.append(entry)

    results: dict[int, dict] = {}

    async def _run_one(entry: dict) -> dict:
        name = entry["name"]
        args = entry["item"].get("args") if isinstance(entry["item"].get("args"), dict) else {}
        t0 = time.perf_counter()
        try:
            result = await call_tool(name, args)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            status = result.get("status", "SUCCESS") if isinstance(result, dict) else "SUCCESS"
            text = ""
            if isinstance(result, dict):
                text = str(result.get("result") or result.get("error_message") or "")
            return {"tool_name": name, "status": status, "result_summary": text[:500], "latency_ms": latency_ms, "parallel": True}
        except Exception as exc:
            return {"tool_name": name, "status": "ERROR", "result_summary": str(exc)[:200], "latency_ms": int((time.perf_counter() - t0) * 1000), "parallel": True}

    # 并发组：并行项并发执行有独立延迟
    if parallel:
        raws = await asyncio.gather(*[_run_one(e) for e in parallel])
        for e, r in zip(parallel, raws):
            results[e["idx"]] = r
    # 串行组：逐个执行
    for e in serial:
        r = await _run_one(e)
        results[e["idx"]] = {**r, "parallel": False}

    return [results[i] for i in range(len(tool_plan))]