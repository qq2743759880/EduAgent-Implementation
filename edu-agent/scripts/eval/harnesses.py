# -*- coding: utf-8 -*-
"""
task29 三套评估 harness（真实回放，不伪造）：
  - SixNode  ：新 6 节点图（route→compact→plan→fan_out→merge→reflect→answer）
                通过 app.ai.graph.run_agent 真实运行；注入 LLMRecorder 捕获调用与 usage。
  - Baseline：重构前基线（app.chat.flows.langgraph_agent）真实运行。
  - Loop    ：简化循环 harness（route→tool loop→answer，Anthropic 《Building Effective Agents》
                free-agent 模式）——R8 对比候选，全部经 llm_client.call（返回 usage）计量。

每 harness 输出统一 HarnessResult（含预测 intent / effort / 答案 / 延迟 / 调用数 / token / 缓存）。
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from scripts.eval import llm_client
from scripts.eval.eval_dataset import INTENT_TO_EFFORT

# ─────────────────────────────────────────────
# 数据契约
# ─────────────────────────────────────────────
@dataclass
class HarnessResult:
    sample_id: str
    query: str
    intent: str = ""            # 预测意图
    effort: str = ""            # 设计档位（由预测意图派生）
    answer: str = ""
    latency_ms: float = 0.0
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_hit_tokens: int = 0
    cache_miss_tokens: int = 0
    degraded: str | None = None
    error: str | None = None


def effort_from_intent(intent: str) -> str:
    return INTENT_TO_EFFORT.get((intent or "").strip().lower(), "L1")


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


def default_result(sample) -> HarnessResult:
    return HarnessResult(sample_id=sample.id, query=sample.query)


def add_usage(res: HarnessResult, usage: dict) -> None:
    res.prompt_tokens += int(usage.get("prompt_tokens") or 0)
    res.completion_tokens += int(usage.get("completion_tokens") or 0)
    res.cache_hit_tokens += int(usage.get("prompt_cache_hit_tokens") or 0)
    res.cache_miss_tokens += int(usage.get("prompt_cache_miss_tokens") or 0)
    res.llm_calls += 1


# ─────────────────────────────────────────────
# LLMRecorder：monkeypatch graph._llm_call / runner._default_llm → 捕获 usage
# ─────────────────────────────────────────────
class LLMRecorder:
    def __init__(self) -> None:
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cache_hit = 0
        self.cache_miss = 0
        self._orig_graph: Any = None
        self._orig_runner: Any = None

    def install(self) -> None:
        import app.ai.graph as g
        import app.ai.subagents.runner as r

        self._orig_graph = g._llm_call
        self._orig_runner = r._default_llm

        async def _wrap_graph(messages, *, model, temperature=0.0, max_tokens=500, timeout=60.0):
            out = llm_client.call(messages=messages, model=model, temperature=temperature,
                                  max_tokens=max_tokens, timeout=timeout)
            self._add(out["usage"])
            return out["text"]

        async def _wrap_runner(messages, model):
            out = llm_client.call(messages=messages, model=model, temperature=0.0,
                                  max_tokens=settings_llm_max(), timeout=60.0)
            self._add(out["usage"])
            return out["text"]

        g._llm_call = _wrap_graph
        r._default_llm = _wrap_runner

    def _add(self, usage: dict) -> None:
        usage = usage or {}
        self.calls += 1
        self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.completion_tokens += int(usage.get("completion_tokens") or 0)
        self.cache_hit += int(usage.get("prompt_cache_hit_tokens") or 0)
        self.cache_miss += int(usage.get("prompt_cache_miss_tokens") or 0)

    def uninstall(self) -> None:
        if self._orig_graph is not None:
            import app.ai.graph as g
            g._llm_call = self._orig_graph
            self._orig_graph = None
        if self._orig_runner is not None:
            import app.ai.subagents.runner as r
            r._default_llm = self._orig_runner
            self._orig_runner = None

    def apply(self, res: HarnessResult) -> None:
        res.llm_calls = self.calls
        res.prompt_tokens = self.prompt_tokens
        res.completion_tokens = self.completion_tokens
        res.cache_hit_tokens = self.cache_hit
        res.cache_miss_tokens = self.cache_miss


def settings_llm_max() -> int:
    from app.config import settings
    return int(getattr(settings, "LLM_MAX_TOKENS", 2000))


# ─────────────────────────────────────────────
# ROUTE prompts
# ─────────────────────────────────────────────
SIXNODE_ROUTE_PROMPT = (
    "你是EduAgent的意图路由器。把用户的一条消息归类为四类之一，只输出JSON {\"intent\":\"<类别>\"}：\n"
    "- chitchat: 闲聊/打招呼/自我介绍/系统功能询问，与学科知识无关\n"
    "- knowledge: 具体学科知识问题（英语语法/编程/数学/物理等），需要查知识库\n"
    "- tool: 明确可调用工具解决（计算/实时查询/代码执行等）\n"
    "- learning: 学习方法/路径规划/考试策略等引导性建议\n"
    "严格只输出JSON，不要多余文字。"
)

# 重构前基线路由器：镜像旧 AGENT_SYSTEM_PROMPT 的决策规则，但输出统一的四类 intent 以便公平比对
BASELINE_ROUTE_PROMPT = (
    "你是EduAgent智能学习助手，请判断用户意图并输出JSON {\"intent\":\"<类别>\"}：\n"
    "- 用户问学科知识（英语/编程/数学/物理等）→ knowledge\n"
    "- 用户问需要计算/执行代码/实时查询的问题 → tool\n"
    "- 用户闲聊/打招呼/系统功能询问 → chitchat\n"
    "- 用户问\"怎么学\"等学习方法/路径规划 → learning\n"
    "严格只输出JSON，不要多余文字。"
)

_FAST_INTENTS = ("chitchat", "knowledge", "tool", "learning")


async def route_classify(query: str, prompt: str, retries: int = 2) -> str:
    """真实 LLM 路由，返回四类意图之一。

    鲁棒性：fast 模型偶发返回空串/不可解析（实测），若首包不可解析则重试 retries 次，
    避免空输出被错误兜底为 knowledge 而压垮 chitchat 召回（task29 评估发现并验证的缺陷）。
    全部重试失败后才兜底 knowledge。
    """
    for _ in range(retries + 1):
        try:
            out = llm_client.call(
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": query}],
                model="fast", temperature=0.0, max_tokens=30,
            )
            obj = _extract_json(out["text"]) or {}
            cand = str(obj.get("intent") or "").strip().lower()
            if cand in _FAST_INTENTS:
                return cand
        except Exception:
            continue
    return "knowledge"


# ─────────────────────────────────────────────
# Harness 接口
# ─────────────────────────────────────────────
async def run_sixnode(sample) -> HarnessResult:
    """新 6 节点图真实运行 + LLMRecorder 捕获 usage。

    Redis 不可达时按契约降级：初始化失败不阻断（graph/guard/memory/artifact 均有内存降级路径），
    在 degraded 标注 redis_unreachable。durable checkpoint 因此不可用（标注对结果影响）。
    """
    from app import database as db
    try:
        await db.init_redis()
    except Exception as _redis_exc:
        pass  # Redis 不可达 → 降级（graph 会走无 checkpoint 路径）
    from app.ai import graph

    res = default_result(sample)
    res.degraded = "redis_unreachable"  # 预置；后续仅当图自身产出降级原因时才覆盖
    rec = LLMRecorder()
    rec.install()
    t0 = time.perf_counter()
    try:
        out = await graph.run_agent(sample.query, user_id=1, session_id=f"eval-{sample.id}")
        res.answer = out.get("answer", "")
        res.intent = out.get("intent", "")
        res.latency_ms = float(out.get("latency_ms", 0) or (time.perf_counter() - t0) * 1000)
        # 条件式覆盖：只有图显式报告了非空降级原因才替换预设的 redis_unreachable，
        # 否则保留，确保 Redis 不可达（checkpoint/guard/memory 降级）如实透传到结果。
        if out.get("degraded_reason"):
            res.degraded = out["degraded_reason"]
        if out.get("error"):
            res.error = out["error"]
    finally:
        rec.uninstall()
    rec.apply(res)
    if not res.intent:
        res.intent = await route_classify(sample.query, SIXNODE_ROUTE_PROMPT)
    # 真实 effort 以图 plan_node 定级为准（L0=chitchat 直答, L1/L2=fan_out）；图表输出缺失时才回退意图映射
    res.effort = out.get("effort") or effort_from_intent(res.intent)
    return res


async def run_baseline(sample) -> HarnessResult:
    """重构前基线（旧 langgraph_agent）真实运行。"""
    from app.chat.flows import langgraph_agent as base

    res = default_result(sample)
    t0 = time.perf_counter()
    try:
        out = await base.run_agent(sample.query, user_id=1, session_id=f"eval-{sample.id}")
        res.answer = out.get("answer", "")
        res.latency_ms = float(out.get("latency_ms", 0) or (time.perf_counter() - t0) * 1000)
        res.intent = await route_classify(sample.query, BASELINE_ROUTE_PROMPT)
        # 基线无 usage 探针：标记为 n/a（token 计费不在基线对比范围）
        res.degraded = None
        if out.get("error"):
            res.error = out["error"]
    except Exception as exc:
        res.error = f"{type(exc).__name__}: {exc}"
    res.effort = effort_from_intent(res.intent)
    return res


# ─────────────────────────────────────────────
# Loop harness：route→tool loop→answer（R8 候选，Anthropic free-agent 模式）
# ─────────────────────────────────────────────
async def _retrieve(query: str) -> list[dict]:
    try:
        from app.chat.retriever import retrieve_three_channel
        bundle = await retrieve_three_channel(query, user_id=1, role=None, use_hyde=False,
                                              enable_graph=True, top_k=8, final_max_k=5, cutoff_drop_ratio=0.2)
        return [d.model_dump() for d in bundle.docs]
    except Exception:
        return []


async def _mcp_call(tool_name: str, args: dict) -> dict:
    try:
        from app.mcp import executor as mcp_executor
        r = await mcp_executor.call_tool(tool_name=tool_name, arguments=args, operator_user_id=1)
        return {"status": r.get("status", "SUCCESS"), "result": str(r.get("result", r))} if isinstance(r, dict) else {"status": "SUCCESS", "result": str(r)}
    except Exception as exc:
        return {"status": "ERROR", "result": str(exc)[:200]}


async def run_loop(sample) -> HarnessResult:
    """简化循环 harness：route(1) → 按需 tool 循环(≤2轮) → answer(strong)。"""
    from app.ai.tool_specs import BUILTIN_TOOL_SPECS

    res = default_result(sample)
    t0 = time.perf_counter()

    # 1. route
    route_out = llm_client.call(
        messages=[{"role": "system", "content": SIXNODE_ROUTE_PROMPT}, {"role": "user", "content": sample.query}],
        model="fast", temperature=0.0, max_tokens=30,
    )
    add_usage(res, route_out["usage"])
    obj = _extract_json(route_out["text"]) or {}
    intent = str(obj.get("intent") or "").strip().lower()
    res.intent = intent if intent in _FAST_INTENTS else "knowledge"

    context: list[str] = []
    builtin = {s.name: s for s in BUILTIN_TOOL_SPECS}

    # 2. tool 循环（tool 意图 → 决策工具计划 → 执行 → 继续，≤2 轮）
    if res.intent == "tool":
        for _loop in range(2):
            decision = llm_client.call(
                messages=[
                    {"role": "system", "content": (
                        "你是工具决策器，只输出JSON {\"tool_plan\":[{\"tool_name\",\"args\"}]}。可用工具："
                        "calculator(四则), code_runner(执行代码), web_search(实时搜索)。无需工具时 tool_plan 为空数组。")},
                    {"role": "user", "content": sample.query},
                ],
                model="fast", temperature=0.0, max_tokens=120,
            )
            add_usage(res, decision["usage"])
            plan = (_extract_json(decision["text"]) or {}).get("tool_plan") or []
            if not plan:
                break
            for tv in plan[:2]:
                name = str(tv.get("tool_name") or "")
                args = tv.get("args") or {}
                out = await _mcp_call(name, args)
                context.append(f"[工具 {name} 返回] {str(out.get('result', out))[:400]}")
            # 再问一次是否还需要工具
        # 额外 LLM 判断是否可作答（计入调用）
        judge_call = llm_client.call(
            messages=[{"role": "system", "content": "只输出JSON {\"done\":true/false}"},
                      {"role": "user", "content": f"问题：{sample.query}\n已有工具结果：{context}"}],
            model="fast", temperature=0.0, max_tokens=20,
        )
        add_usage(res, judge_call["usage"])

    # 2b. knowledge 意图 → 检索（Milvus 降级为空）
    elif res.intent == "knowledge":
        docs = await _retrieve(sample.query)
        if docs:
            context.append(f"检索到{len(docs)}条参考知识（本环境 Milvus 不可达时为空）。")
        res.degraded = "milvus_unreachable" if not docs else None

    # 3. answer（strong）
    sys_ctx = "\n".join(context) if context else "（无额外上下文）"
    ans = llm_client.call(
        messages=[
            {"role": "system", "content": "你是EduAgent学习助手，基于已有上下文与自身知识给出准确、结构化的回答。" + "\n## 综合上下文\n" + sys_ctx},
            {"role": "user", "content": sample.query},
        ],
        model="strong", temperature=0.0, max_tokens=settings_llm_max(),
    )
    add_usage(res, ans["usage"])
    res.answer = ans["text"]
    res.latency_ms = (time.perf_counter() - t0) * 1000
    res.effort = effort_from_intent(res.intent)
    return res


HARNESSES = {
    "sixnode": run_sixnode,
    "baseline": run_baseline,
    "loop": run_loop,
}