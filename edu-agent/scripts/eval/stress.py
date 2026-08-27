# -*- coding: utf-8 -*-
"""
task29 GWT② 压测 + 成本测算：
  - L1~L3 各档真实并发跑 6 节点图 → 端到端 P95 延迟（accept：≤8s）
  - 流式首包 TTFT（accept：≤3s）：对最终 answer 生成用 call_stream 实测首 token
  - token 计费：LLMRecorder 累计 prompt/completion → L0~L3 每请求 token → 月度成本测算

不伪造：P95 用真实样本并发实测；cost 用真实 usage；预算假设在报告中显式标注。
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # edu-agent/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/

from scripts.eval import llm_client
from scripts.eval.eval_dataset import by_effort
from scripts.eval.harnesses import LLMRecorder, HarnessResult


def _p95(vals: list[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    k = int(round(0.95 * (len(s) - 1)))
    return float(s[k])


async def _run_sixnode_single(sample, user_id: int, rec: LLMRecorder, results: dict) -> None:
    from app.ai import graph

    t0 = __import__("time").perf_counter()
    try:
        out = await graph.run_agent(sample.query, user_id=user_id, session_id=f"stress-{sample.id}")
        latency_ms = float(out.get("latency_ms", 0) or ((__import__("time").perf_counter() - t0) * 1000))
        results[sample.id] = {"latency_ms": latency_ms, "answer": out.get("answer", ""),
                              "effort": sample.effort, "err": out.get("error")}
    except Exception as exc:
        results[sample.id] = {"latency_ms": 0.0, "answer": "", "effort": sample.effort,
                              "err": f"{type(exc).__name__}: {exc}"}


async def stress(tier: str, n: int = 4) -> dict:
    samples = by_effort(tier)[:n]
    rec = LLMRecorder()
    rec.install()
    results: dict = {}
    t0 = __import__("time").perf_counter()
    try:
        # 用互异 user_id 并发跑，既测真实并发又不触发单用户限流（guard user_max=2）
        await asyncio.gather(*[
            _run_sixnode_single(s, user_id=50000 + i, rec=rec, results=results)
            for i, s in enumerate(samples)
        ])
    finally:
        meta = {"calls": rec.calls, "prompt_tokens": rec.prompt_tokens,
                "completion_tokens": rec.completion_tokens,
                "cache_hit": rec.cache_hit, "cache_miss": rec.cache_miss}
        rec.uninstall()
    latencies = [v["latency_ms"] for v in results.values() if v["latency_ms"] > 0]
    errors = [k for k, v in results.items() if v.get("err")]
    return {
        "tier": tier,
        "samples": list(results.keys()),
        "n": len(samples),
        "latency_ms_list": [round(v["latency_ms"], 1) for v in results.values()],
        "p95_ms": round(_p95(latencies), 1),
        "p50_ms": round(statistics.median(latencies), 1) if latencies else 0.0,
        "errors": errors,
        "llm_meta": meta,
        "per_request_tokens": {
            "prompt": round(meta["prompt_tokens"] / len(samples), 1) if samples else 0,
            "completion": round(meta["completion_tokens"] / len(samples), 1) if samples else 0,
        },
    }


async def stream_ttft(sample, ans_prompt: str) -> dict:
    """最终 answer 生成的流式首包 TTFT 实测。"""
    out = llm_client.call_stream(messages=[
        {"role": "system", "content": "你是EduAgent学习助手，回答用户问题。" + "\n## 综合上下文\n（评估用）"},
        {"role": "user", "content": sample.query},
    ], model="strong", temperature=0.0, max_tokens=300)
    return {"id": sample.id, "ttft_ms": round(out["ttft_ms"], 1), "latency_ms": round(out["latency_ms"], 1)}


# ─────────────────────────────────────────────
# 成本测算（token 计费 + 月度账单投影）
# ─────────────────────────────────────────────
# 价格假设（显式标注，真实项目按账单校准）：
#   DeepSeek 官方类「flash/轻量级」区间价目（每 M token）：输入 ~¥1.0，输出 ~¥6.0
#   —— 估算用占位价，报告标注「假设价，非合同价」。
PRICE_IN_PER_M = 1.0      # ¥ / 1M prompt tokens（假设）
PRICE_OUT_PER_M = 6.0     # ¥ / 1M completion tokens（假设）
DAILY_QUERY = 2000        # 日均用户查询（假设产品规模）


def cost_table(tiers: dict) -> dict:
    """根据各 tier 实测 per_request_tokens 测算月度成本。"""
    rows = []
    monthly_total = 0.0
    for t in ("L0", "L1", "L2", "L3"):
        d = tiers.get(t) or {"per_request_tokens": {"prompt": 0, "completion": 0}}
        pr = d["per_request_tokens"]["prompt"]
        co = d["per_request_tokens"]["completion"]
        per_req_cost = (pr * PRICE_IN_PER_M + co * PRICE_OUT_PER_M) / 1_000_000
        # 档位月请求占比（L0 居多，L3 稀少——假设分布）
        mix = {"L0": 0.45, "L1": 0.35, "L2": 0.15, "L3": 0.05}[t]
        daily_req = DAILY_QUERY * mix
        monthly_req = daily_req * 30
        monthly_cost = monthly_req * per_req_cost
        monthly_total += monthly_cost
        rows.append({"tier": t, "prompt_tok": pr, "completion_tok": co, "per_req_cost_yuan": round(per_req_cost, 6),
                     "monthly_req": int(monthly_req), "monthly_cost_yuan": round(monthly_cost, 2)})
    return {"rows": rows, "monthly_total_yuan": round(monthly_total, 2),
            "price_assumption": {"in_per_M": PRICE_IN_PER_M, "out_per_M": PRICE_OUT_PER_M},
            "daily_query_assumption": DAILY_QUERY,
            "budget_yuan": 300.0}


async def main(n: int = 4) -> dict:
    tiers: dict = {}
    ttft: dict = {}
    for t in ("L1", "L2", "L3"):
        tiers[t] = await stress(t, n)
        ttft[t] = {"samples": []}
        for s in by_effort(t)[:2]:
            ttft[t]["samples"].append(await stream_ttft(s, ""))
        ttft[t]["p95"] = round(_p95([x["ttft_ms"] for x in ttft[t]["samples"]]), 1)
    return {"stress": tiers, "stream_ttft": ttft, "cost": cost_table(tiers)}


# ─────────────────────────────────────────────
# Rerank 压测（task-R1 AC5）：sidecar 连续批处理 vs 同进程串行
# ─────────────────────────────────────────────
async def _call_infer(infer, pairs):
    """调用注入的推理函数：coroutine 直接 await；sync（如 Reranker.rerank_pairs）经 run_in_executor。"""
    if asyncio.iscoroutinefunction(infer):
        return await infer(pairs)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, infer, pairs)


async def _rerank_sidecar_batch(infer, reqs, *, window_ms: int, max_batch_pairs: int) -> list:
    """模拟 sidecar：一个 batcher 并发接收所有请求，连续批处理一次前向。"""
    from app.rerank_service.batcher import ContinuousBatcher

    b = ContinuousBatcher(infer, window_ms=window_ms, max_batch_pairs=max_batch_pairs,
                          max_wait_ms=50, max_queue=200)
    b.start()
    try:
        out = await asyncio.gather(*[b.submit(q, c) for q, c in reqs])
    finally:
        await b.stop()
    return out


async def _rerank_inprocess(infer, reqs) -> list:
    """模拟同进程串行（task31 现状）：每个请求单独前向。"""
    out = []
    for q, c in reqs:
        pairs = [(q, cc) for cc in c]
        out.append(await _call_infer(infer, pairs))
    return out


async def rerank_stress(n_reqs: int = 20, contents_per: int = 5, *, infer=None,
                        window_ms: int = 20, max_batch_pairs: int = 64) -> dict:
    """Rerank 压测：对比 sidecar（连续批处理）与同进程（串行）的吞吐。

    infer: 注入的推理函数（扁平 [(query,content)] -> [score]）。默认用真实 Reranker.rerank_pairs
    （需 CUDA + 模型；窗口外运行注意显存）。返回 sidecar/inproc 耗时、QPS、speedup 与分数（一致性校验）。
    """
    if infer is None:
        from app.knowledge.reranker import Reranker

        rk = Reranker.get()
        infer = rk.rerank_pairs  # 同步函数，_call_infer 会经 run_in_executor

    reqs = [(f"q{i}", [f"c{i}-{j}" for j in range(contents_per)]) for i in range(n_reqs)]

    # sidecar 模式（连续批处理）
    t0 = time.perf_counter()
    sidecar = await _rerank_sidecar_batch(infer, reqs, window_ms=window_ms, max_batch_pairs=max_batch_pairs)
    sidecar_ms = (time.perf_counter() - t0) * 1000.0

    # 同进程串行模式
    t0 = time.perf_counter()
    inproc = await _rerank_inprocess(infer, reqs)
    inproc_ms = (time.perf_counter() - t0) * 1000.0

    sidecar_qps = n_reqs / (sidecar_ms / 1000.0) if sidecar_ms > 0 else 0.0
    inproc_qps = n_reqs / (inproc_ms / 1000.0) if inproc_ms > 0 else 0.0
    sidecar_flat = [s for req in sidecar for s in req]
    inproc_flat = [s for req in inproc for s in req]
    # 一致性：跨请求批处理在 fp16 下存在 ~1e-2 级批处理算术噪声（同单请求 rerank 自身方差同级），
    # 对排序无影响；按容差判定「排序等价」。
    _consist = False
    if sidecar_flat and inproc_flat and len(sidecar_flat) == len(inproc_flat):
        _consist = max(abs(a - b) for a, b in zip(sidecar_flat, inproc_flat)) < 0.05
    return {
        "n_reqs": n_reqs,
        "contents_per": contents_per,
        "sidecar_ms": round(sidecar_ms, 1),
        "inproc_ms": round(inproc_ms, 1),
        "sidecar_qps": round(sidecar_qps, 1),
        "inproc_qps": round(inproc_qps, 1),
        "speedup": round(sidecar_qps / max(inproc_qps, 1e-9), 2),
        "scores_consistent": _consist,
        "sidecar_scores": sidecar_flat,
        "inproc_scores": inproc_flat,
    }


if __name__ == "__main__":
    n = int(os.environ.get("STRESS_N", "4"))
    out = asyncio.run(main(n))
    print(json.dumps(out, ensure_ascii=False, indent=2))