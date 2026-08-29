"""
子代理独立上下文运行器（task92 R1 落地）。

修复 self-critique 维度3 结构性缺陷「子代理共享 state」：
- 每个子代理由 `run_subagent` 以「本会话独立 messages 数组 + 独立 system prompt + 独立工具白名单」
  运行一个独立 LLM 会话循环（≤ spec.maxTurns 轮）。
- 完整输出（检索原文 / 工具结果 / 子代理全消息）写 **artifact**（Redis TTL 1h，可降级内存），
  只向主上下文返回「蒸馏摘要（≤ summary_budget token）+ artifact 引用」。
- 崩溃重试发生在每个子代理的本地循环内，绝不写主共享 state（独立会话隔离）。

对齐 Claude Code sub-agents「Each subagent runs in its own context window」。
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

import yaml

from loguru import logger

from app.config import settings

# task-P1L 优化H3：可确定性预执行的单工具子代理（工具入参可由 input_text 推导，无需 LLM 决策轮）。
# search/memory/learning 各只有 1 个工具且入参为查询词；tool 子代理的 call_tool 入参开放
# （tool_name/args 依赖 LLM 决策），不在其列——对齐 Anthropic Building Effective Agents 取舍。
_DIRECT_PREFETCH_TOOLS: frozenset[str] = frozenset({"search_knowledge", "recall_memory", "recall_profile"})


def _direct_tool_args(subagent: str, input_text: str) -> dict:
    """推导单工具子代理的确定性入参（对齐 _build_tool_services 的工具签名）。

    plan 节点注入的 input 形如 ``<模板>（问题：<query>）``，此处取 ``（问题：…）`` 尾部为查询词；
    提取失败（query 含异常括号等）→ 整段 input_text 作查询词兜底（检索对输入不敏感，可容忍）。
    """
    q = input_text or ""
    m = re.search(r"（问题：(.*)）\s*$", q, re.S)
    if m and m.group(1).strip():
        q = m.group(1).strip()
    if subagent == "learning":
        return {"profile_query": q}
    return {"q": q}


# 内置 4 子代理定义文件
_DEFINITIONS_PATH = Path(__file__).resolve().parent / "definitions.yaml"


# ═══════════════════════════════════════════
# 数据契约
# ═══════════════════════════════════════════
@dataclass(frozen=True)
class SubagentSpec:
    """子代理定义（对齐 Claude Code frontmatter 子集）。"""
    name: str
    description: str = ""
    tools: tuple[str, ...] = ()
    model: str = "fast"
    maxTurns: int = 4
    memory_scope: str = "none"
    system_prompt: str = ""


@dataclass
class SubagentTask:
    """一个待执行的子代理任务（由主图 plan_node 产出）。"""
    subagent: str                              # definitions.yaml 中的 name
    objective: str
    input: str = ""
    tool_services: dict[str, Callable[[dict], Awaitable[Any]]] = field(default_factory=dict)
    llm: Callable[[list[dict], str], Awaitable[str]] | None = None  # 可选注入（测试/模拟）；None→默认客户端
    user_id: int | None = None
    thread_id: str | None = None


@dataclass
class SubagentResult:
    """子代理返回给主上下文的蒸馏结果（不含原文，仅摘要 + artifact 引用）。"""
    subagent: str
    summary: str
    artifact_ref: str
    ok: bool
    turns: int = 0
    tool_calls: int = 0
    summary_tokens: int = 0

    def as_distilled(self) -> dict:
        """主 state 可安全合并的最小载荷（≤ budget token 摘要 + 引用）。"""
        return {
            "subagent": self.subagent,
            "summary": self.summary,
            "artifact_ref": self.artifact_ref,
            "summary_tokens": self.summary_tokens,
        }


# ═══════════════════════════════════════════
# 定义加载
# ═══════════════════════════════════════════
_specs_cache: dict[str, SubagentSpec] | None = None


def _load_definitions(path: Path = _DEFINITIONS_PATH) -> dict[str, SubagentSpec]:
    global _specs_cache
    if _specs_cache is not None:
        return _specs_cache
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    specs: dict[str, SubagentSpec] = {}
    for item in raw.get("subagents", []):
        specs[item["name"]] = SubagentSpec(
            name=item["name"],
            description=item.get("description", ""),
            tools=tuple(item.get("tools", [])),
            model=item.get("model", "fast"),
            maxTurns=int(item.get("maxTurns", 4)),
            memory_scope=item.get("memory_scope", "none"),
            system_prompt=item.get("system_prompt", ""),
        )
    _specs_cache = specs
    return specs


def get_subagent_spec(name: str) -> SubagentSpec:
    specs = _load_definitions()
    if name not in specs:
        raise ValueError(f"未知子代理定义：{name}，可用: {sorted(specs)}")
    return specs[name]


# ═══════════════════════════════════════════
# Token 估算与摘要裁剪（主上下文只收 ≤ budget 摘要）
# ═══════════════════════════════════════════
def _token_approx(text: str) -> int:
    """粗略 token 估算：中文/全角 ≈1 token/字，ASCII ≈1 token/4字符（保守偏大）。"""
    cjk = 0
    ascii_cnt = 0
    for ch in text:
        o = ord(ch)
        if 0x2E80 <= o <= 0x9FFF or 0x3000 <= o <= 0x303F:
            cjk += 1
        elif ch != "\n":
            ascii_cnt += 1
    return cjk + ascii_cnt // 4 + 1


def _clamp_summary(text: str, budget: int) -> str:
    """将摘要裁剪到 ≤ budget token。"""
    text = (text or "").strip()
    if not text or _token_approx(text) <= budget:
        return text
    # 按 token 预算反推大致字符数（最坏按全 CJK 1 字/token）
    hint = budget * 1  # CJK 最坏情形
    if _token_approx(text[:hint]) <= budget:
        return text[:hint]
    # 二分到合适前缀 + 省略号
    lo, hi = 0, min(len(text), budget * 2)
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if _token_approx(text[:mid]) <= budget:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return text[:best].rstrip() + "…"


# ═══════════════════════════════════════════
# Artifact 存储（完整输出进 artifact，Redis TTL 1h，可降级内存）
# ═══════════════════════════════════════════
class ArtifactStore:
    def __init__(self) -> None:
        self._mem: dict[str, Any] = {}

    async def write(self, payload: Any, ttl: int = 3600) -> str:
        ref = f"artifact:{uuid.uuid4().hex}"
        blob = json.dumps(payload, ensure_ascii=False, default=str)
        try:
            from app.database import get_redis
            r = get_redis()
            await r.set(ref, blob, ex=ttl)
            return ref
        except Exception:
            self._mem[ref] = blob
            return ref

    async def read(self, ref: str) -> Any:
        try:
            from app.database import get_redis
            r = get_redis()
            raw = await r.get(ref)
            if raw is not None:
                return json.loads(raw)
        except Exception:
            pass
        if ref in self._mem:
            return json.loads(self._mem[ref])
        return None


_default_store = ArtifactStore()


# ═══════════════════════════════════════════
# 默认 LLM 客户端（复用 chat.generator._ChatClient；测试可注入 fake）
# ═══════════════════════════════════════════
async def _default_llm(messages: list[dict], model: str) -> str:
    from app.chat.generator import _ChatClient
    client = _ChatClient.get()
    loop = asyncio.get_running_loop()
    # task-P1L 优化F：子代理输出收紧到 ≤800 token（决策 JSON ~50 token、蒸馏摘要 ≤2000 预算但
    # 实际 200~800 token 已足够）。原用 LLM_MAX_TOKENS=2000 全量预算 → 总结轮生成上千 token
    # （~50-100 token/s → 15-30s），是 fan_out 块 17s 实测的根因；收紧后生成时间大幅下降。
    max_tokens = min(int(getattr(settings, "SUBAGENT_MAX_TOKENS", 800)), int(settings.LLM_MAX_TOKENS))
    return await loop.run_in_executor(
        None,
        lambda: client.call_chat(
            messages=messages,
            model=model,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=max_tokens,
            timeout=60.0,
        ),
    )


def _parse_action(raw: str) -> dict:
    if not raw:
        return {"tool": None, "final": ""}
    text = raw.strip()
    import re
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    else:
        a, b = text.find("{"), text.rfind("}")
        if a >= 0 and b > a:
            text = text[a:b + 1]
    try:
        obj = json.loads(text)
        return obj
    except Exception:
        return {"tool": None, "final": text}


# ═══════════════════════════════════════════
# 独立上下文会话循环
# ═══════════════════════════════════════════
async def _call_llm_with_retry(llm, messages: list[dict], model: str, max_attempts: int = 2) -> str | None:
    """LLM 调用 + 崩溃重试（重试 ebough 语义）——全程只操作本会话局部 messages，不写共享 state。"""
    for attempt in range(1, max_attempts + 1):
        try:
            return await llm(messages, model=model)
        except Exception as exc:
            logger.warning(f"[Subagent] LLM 调用失败（第 {attempt}/{max_attempts} 次重试）: {type(exc).__name__}: {exc}")
            if attempt >= max_attempts:
                return None
            await asyncio.sleep(0.1 * attempt)
    return None


async def run_subagent(
    spec: SubagentSpec,
    *,
    objective: str,
    input_text: str = "",
    tool_services: dict[str, Callable[[dict], Awaitable[Any]]] | None = None,
    llm: Callable[[list[dict], str], Awaitable[str]] | None = None,
    user_id: int | None = None,
    thread_id: str | None = None,
    summary_budget: int | None = None,
    artifact_ttl: int | None = None,
) -> SubagentResult:
    """运行一个子代理——独立 LLM 会话循环（独立 messages/system/tool 白名单/maxTurns）。

    上下文隔离：本函数每次调用都新建本地 `messages` 列表；工具输出只追加到该列表；
    崩溃重试只发生在此本地循环内；对外只暴露 SubagentResult(summary + artifact_ref)。
    绝不写入任何主共享 state。

    Returns:
        SubagentResult——summary 为 ≤ budget token 蒸馏摘要，artifact_ref 指向完整输出。
    """
    budget = summary_budget if summary_budget is not None else settings.SUBAGENT_SUMMARY_BUDGET
    ttl = artifact_ttl if artifact_ttl is not None else settings.SUBAGENT_ARTIFACT_TTL
    llm = llm or _default_llm
    tool_services = tool_services or {}
    user_ctx = (f"[user_id={user_id}] " if user_id is not None else "")
    thread_ctx = (f"[thread_id={thread_id}] " if thread_id else "")

    # —— 独立会话消息数组（绝不来自共享 state）——
    # task-P1L 优化E：子代理 system prompt 为静态定义 → ensure_min_prefix 撑到 ≥2048 token，
    # 跨请求/跨用户字节一致，火山 ark prompt cache 命中 → turn0 决策调用的 prefill 大幅下降
    # （fan_out 块是主链路最重阶段，子代理内首轮决策直接受益）。不改变会话循环语义（maxTurns/工具决策不变）。
    if spec.system_prompt.strip():
        from app.ai.prompt_cache import ensure_min_prefix

        system_content = ensure_min_prefix(spec.system_prompt)
    else:
        system_content = spec.system_prompt
    messages: list[dict] = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": f"# 子代理: {spec.name}\n# 目标: {objective}\n{user_ctx}{thread_ctx}\n{input_text}".strip()},
    ]

    tool_calls = 0
    final_text = ""
    ok = False
    full_tool_outputs: list[dict] = []   # 完整工具输出——整体落 artifact（不截断），主上下文只见摘要

    # —— task-P1L 优化H3：单工具确定性子代理 turn-1 预执行（0 决策轮 LLM）——
    # search/memory/learning 的工具调用是确定性的（入参由 input_text 推导）：turn-0 直接执行
    # 唯一工具并把结果注入首轮 prompt，LLM 只做总结轮 → 子代理从「决策+工具+总结 2 次 LLM」
    # 降为「总结 1 次 LLM」（task39 实测决策轮 1.4~5.0s，fan_out 块串行累计直接受益）。
    # 失败/开关关闭 → 保持原 LLM 决策循环（行为不降级）。tool 子代理不在其列（call_tool 入参开放）。
    if (
        getattr(settings, "SUBAGENT_DIRECT_TOOL_ENABLED", True)
        and len(spec.tools) == 1
        and spec.tools[0] in _DIRECT_PREFETCH_TOOLS
        and tool_services
    ):
        prefetch_tool = spec.tools[0]
        handler = tool_services.get(prefetch_tool)
        if handler is not None:
            prefetch_args = _direct_tool_args(spec.name, input_text)
            try:
                prefetch_result = await handler(prefetch_args)
            except Exception as exc:
                prefetch_result = {"error": f"{type(exc).__name__}: {exc}"}
            tool_calls = 1
            full_tool_outputs.append({"tool": prefetch_tool, "args": prefetch_args, "result": prefetch_result})
            flow_txt = json.dumps(prefetch_result, ensure_ascii=False, default=str)[:4000]
            try:
                from app.ai.artifact import distill_tool_output as _distill

                distilled = await _distill(prefetch_tool, prefetch_result, ttl=ttl)
                if distilled.get("distilled"):
                    flow_txt = f"{distilled['conclusion']}（artifact:{distilled.get('artifact_ref')}）"
            except Exception:
                pass  # 蒸馏失败 → 保持原截断，不影响主链路
            messages.append(
                {
                    "role": "user",
                    "content": f"[工具 {prefetch_tool} 已确定性预执行，结果如下]\n{flow_txt}\n\n"
                    f"请直接基于以上结果输出 final JSON（{{\"tool\": null, \"final\": \"<摘要>\"}}），不要再调用任何工具。",
                }
            )
            logger.info(f"[Subagent:{spec.name}] 单工具确定性预执行完成（0 决策 LLM），LLM 仅总结轮")

    for turn in range(spec.maxTurns):
        raw = await _call_llm_with_retry(llm, messages, spec.model)
        if raw is None:
            logger.warning(f"[Subagent:{spec.name}] LLM 连试失败，提前结束 turn={turn + 1}（不污染主上下文）")
            break

        action = _parse_action(raw)
        tool_name = action.get("tool")
        if not tool_name:
            final_text = str(action.get("final") or raw).strip()
            ok = True
            break

        # —— 工具白名单校验 + 本会话局部调用 ——
        if tool_name not in spec.tools:
            messages.append({"role": "user", "content": f"[工具 {tool_name} 不在白名单 {list(spec.tools)}，跳过]"})
            continue
        handler = tool_services.get(tool_name)
        if handler is None:
            messages.append({"role": "user", "content": f"[工具 {tool_name} 不可用（未注入），跳过]"})
            continue
        tool_calls += 1
        try:
            result = await handler(action.get("args") or {})
        except Exception as exc:
            result = {"error": f"{type(exc).__name__}: {exc}"}
        # 完整结果整体进 artifact；messages 内 txt 截断（LLM 上下文体量受控 + 子代理上下文隔离）
        # task26 GWT②/R4 tool result clearing：单条工具输出 >1500 token → 流内仅 1 行结论，原文进 artifact
        full_tool_outputs.append({"tool": tool_name, "args": action.get("args") or {}, "result": result})
        messages.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})
        flow_txt = json.dumps(result, ensure_ascii=False, default=str)[:4000]
        try:
            from app.ai.artifact import distill_tool_output as _distill

            distilled = await _distill(tool_name, result, ttl=ttl)
            if distilled.get("distilled"):
                flow_txt = f"{distilled['conclusion']}（artifact:{distilled.get('artifact_ref')}）"
        except Exception:
            pass  # 蒸馏失败 → 保持原截断，不影响主链路
        messages.append({"role": "user", "content": f"[工具 {tool_name} 返回] {flow_txt}"})

    # —— 完整输出（工具原文/全消息）进 artifact，主上下文只收摘要 ——
    payload = {
        "subagent": spec.name,
        "objective": objective,
        "model": spec.model,
        "turns": min(turn + 1, spec.maxTurns),
        "tool_calls": tool_calls,
        "ok": ok,
        "artifact_ttl": ttl,
        "tool_outputs": full_tool_outputs,   # 完整工具返回体（如检索的 100 篇原文）
        "messages": messages,               # 子代理全消息（含截断视图）
    }
    artifact_ref = await _default_store.write(payload, ttl)

    summary = _clamp_summary(final_text or objective, budget)
    return SubagentResult(
        subagent=spec.name,
        summary=summary,
        artifact_ref=artifact_ref,
        ok=ok,
        turns=min(turn + 1, spec.maxTurns),
        tool_calls=tool_calls,
        summary_tokens=_token_approx(summary),
    )


# ═══════════════════════════════════════════
# 并行 fan-out：每个子代理独立上下文（非共享 state）
# ═══════════════════════════════════════════
async def run_subagents(
    tasks: list[SubagentTask],
    *,
    llm: Callable[[list[dict], str], Awaitable[str]] | None = None,
    summary_budget: int | None = None,
) -> list[SubagentResult]:
    """并行启动 N 个子代理（asyncio.gather），各自独立上下文；主 state 仅收各自摘要。

    每个任务在独立 messages 数组上运行；一个子代理的检索/工具输出不会进入其它子代理或主上下文。
    """
    specs = _load_definitions()

    async def _one(task: SubagentTask) -> SubagentResult:
        # 未知子代理：统一友好错误（不抛裸 KeyError）
        if task.subagent not in specs:
            return SubagentResult(
                subagent=task.subagent,
                summary=f"[未知子代理] {task.subagent}，可用: {sorted(specs)}",
                artifact_ref="",
                ok=False,
            )
        spec = specs[task.subagent]
        try:
            return await run_subagent(
                spec,
                objective=task.objective,
                input_text=task.input,
                tool_services=task.tool_services,
                llm=task.llm or llm,          # per-task llm 优先（测试/模拟）；None→共享/默认
                user_id=task.user_id,
                thread_id=task.thread_id,
                summary_budget=summary_budget,
            )
        except Exception as exc:
            # 防御性兜底：单子代理意外异常 → 降级为 ok=False，不污染主上下文、不拖垮整批
            logger.error(f"[Subagent:{task.subagent}] 意外异常（已隔离）: {type(exc).__name__}: {exc}")
            return SubagentResult(subagent=task.subagent, summary="", artifact_ref="", ok=False)

    # return_exceptions=True：单个子代理失败不取消整批并行
    raw = await asyncio.gather(*[_one(t) for t in tasks], return_exceptions=True)
    return [r if not isinstance(r, Exception) else SubagentResult(subagent="unknown", summary="", artifact_ref="", ok=False)
            for r in raw]


def artifact_store() -> ArtifactStore:
    """暴露 artifact store（供验收 inspect 原文）。"""
    return _default_store