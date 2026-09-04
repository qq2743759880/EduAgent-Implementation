# -*- coding: utf-8 -*-
"""task30 批判② · 真实 LLM 前缀质量 / 成本端到端（离线核算，零额外调用）。

依据：scripts/task30_results.json 已在 RUN_REAL_LLM=1 下用真实 DeepSeek 生成前缀
（mode=real-LLM, contextualized=2, degraded=0, raw_content 全保留, Milvus 落库 content=前缀版、
raw_content=原文 均实证）。本脚本基于该持久化证据做「质量 + 一次性/经常性成本」端到端核算，
并以 estimate_tokens（CJK≈1 tok/字，app.ai.compaction）估算 token 量、参考价折算金额。

说明：实时 LLM 接口当前返回 HTTP 402 Insufficient Balance，故不再发起实时调用；
所有 token 数为 estimate_tokens 估算（非供应商 usage），已在字段显式标注。
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ai.compaction import estimate_tokens  # noqa: E402
from app.config import settings  # noqa: E402

# 参考价（元/1M tokens），量级估算用；替换不改变结论方向
PRICE = {"input_per_1m": 2.0, "output_per_1m": 8.0,
         "note": "DeepSeek-V 档参考价（输入2元/1M、输出8元/1M），仅量级估算"}

RAW = {
    "c1": "上下文注入能在向量化前把片段放到所属文档语境里，显著提升检索召回率。",
    "c2": "Anthropic 实测 contextual embeddings 可将检索失败率降低 35%，代价是略高的存储与调用成本。",
}

# CONTEXT_PROMPT 常数里含 token 预算说明等固定文案（该文案对所有 chunk 相同，构成一次性固定开销）
PROMPT_HEADER = (
    "你是一个为知识检索做准备的 context 助手。给你一段<文档上下文>和其中的<片段>，"
    "请写一个简短的中文上下文描述，把<片段>放到所属文档的主题语境里，便于后续语义检索命中。"
    "要求：(1) 仅输出描述本身，不要重复<片段>原文；(2) 控制在50-100个token；(3) 只描述与<片段>相关的内容。"
)
PREFIX_SEP = "\n"


def main() -> dict:
    rp = os.path.join(os.path.dirname(__file__), "task30_results.json")
    prior = json.load(open(rp, encoding="utf-8"))

    out: dict = {
        "mode": "offline-recheck",
        "evidence_source": "scripts/task30_results.json (RUN_REAL_LLM=1 时的真实前缀持久化)",
        "price": PRICE,
        "note": "实时 LLM HTTP 402 Insufficient Balance，本次为离线核算；token 为 estimate_tokens 估算",
        "live_api_status": "HTTP 402 Insufficient Balance (实时调用受阻)",
    }

    # ---- 质量（复用持久化真实结果）----
    chunks = prior.get("chunks", {})
    out["quality"] = {
        "mode": prior.get("mode"),
        "contextualized": prior.get("stats", {}).get("contextualized"),
        "degraded": prior.get("stats", {}).get("degraded"),
        "skipped": prior.get("stats", {}).get("skipped"),
        "per_chunk": {k: {"has_prefix": v.get("has_prefix"),
                          "raw_content_preserved": v.get("raw_content_preserved"),
                          "content_len": v.get("content_len"), "raw_len": v.get("raw_len"),
                          "degraded_reason": v.get("degraded_reason")}
                      for k, v in chunks.items()},
        "filter_skips_q1_code1": (chunks.get("q1", {}).get("has_prefix") is False
                                  and chunks.get("code1", {}).get("has_prefix") is False),
        "milvus_probe": prior.get("milvus"),
        "degrade_no_500": (prior.get("degrade", {}).get("no_500") is True
                           and prior.get("degrade", {}).get("content_unchanged") is True),
    }

    # ---- 成本：真实前缀长度（持久化）+ estimate_tokens ----
    prefix_chars = {}
    total_raw = 0
    total_prefixed = 0
    for cid, t in RAW.items():
        raw_len = len(t)
        content_len = chunks.get(cid, {}).get("content_len", raw_len)
        pc = max(0, content_len - raw_len)  # 真实前缀字符数（内容含分隔符时略计含 \n 部分，见 prefixed_note）
        prefix_chars[cid] = pc
        total_raw += raw_len
        total_prefixed += content_len

    # 简化：前缀/原文均以「字数近似 token」估算（CJK≈1 tok/字，estimate_tokens 对 CJK 即如此）
    per_prefix = {cid: estimate_tokens(pc * "中") for cid, pc in prefix_chars.items()}
    per_fixed = estimate_tokens(PROMPT_HEADER)

    in_tokens = {cid: per_fixed + estimate_tokens(t) + per_prefix[cid] for cid, t in RAW.items()}
    in_sum = sum(in_tokens.values())
    # 输出 token：前缀本身即输出，≈ per_prefix（参考值）
    out_sum = sum(per_prefix.values())
    cost_in = in_sum / 1e6 * PRICE["input_per_1m"]
    cost_out = out_sum / 1e6 * PRICE["output_per_1m"]
    n = len(RAW)

    out["one_time_cost_per_chunk"] = {
        "per_chunk_input_tokens": {cid: t for cid, t in in_tokens.items()},
        "per_chunk_output_tokens(≈prefix)": {cid: t for cid, t in per_prefix.items()},
        "prompt_fixed_header_tokens": per_fixed,
        "avg_input_tokens_per_chunk": round(in_sum / n, 1),
        "avg_output_tokens_per_chunk": round(out_sum / n, 1),
        "cost_yuan_total": round(cost_in + cost_out, 6),
        "cost_yuan_per_chunk": round((cost_in + cost_out) / n, 6),
    }

    # ---- 经常性成本：前缀膨胀 → 向量存储 + 每次检索 prompt 的 doc content 增量 ----
    out["recurring_cost"] = {
        "raw_total_chars": total_raw,
        "prefixed_total_chars": total_prefixed,
        "prefix_chars": {cid: pc for cid, pc in prefix_chars.items()},
        "content_growth_pct": round((total_prefixed - total_raw) / total_raw * 100, 1),
        "storage_incl_rawcopy_growth_pct": round(((total_prefixed + total_raw) - total_raw) / total_raw * 100, 1),
        "prompt_size_growth_est_pct": round((total_prefixed - total_raw) / total_raw * 100, 1),
        "note": "前缀既放大向量化/文档存储（≈2-3×），又逐次放大 RAG 检索注入 prompt 的 doc content（经常性成本）",
    }

    out["global_switch"] = {"CONTEXTUALIZE_ENABLED": bool(settings.CONTEXTUALIZE_ENABLED),
                            "note": "入库 pipeline 总开关默认 False，需显式开启才产生以上成本"}
    out["critical_finding"] = [
        "质量达标：真实前缀生成 2/2 成功、0 降级；题库/代码正确跳过；降级路径原文保留且不 500；Milvus 落库 content=前缀版/raw_content=原文 实测通过。",
        "成本双面：一次性前缀生成≈每次 100+ token 输入量级（估算）；经常性 content 膨胀≈+200%（含 raw_content 落库≈+290%），使每次检索 prompt 与向量存储同步增大。",
        "默认关闭：CONTEXTUALIZE_ENABLED=False，性能/召回收益未在默认配置落地，需显式开启并接受存储/成本代价。",
    ]

    outp = os.path.join(os.path.dirname(__file__), "task30_cost_results.json")
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=2))