# -*- coding: utf-8 -*-
"""
task29 GWT③ prompt caching 命中率计量（provider 侧，不伪造）。

DeepSeek 返回 usage.prompt_cache_hit_tokens / prompt_cache_miss_tokens；
命中率 = hit / (hit + miss)。

注意（诚实标注）：DeepSeek 前缀缓存通常要求前缀 ≥1024 token 才启用。
task27 决策前缀预算仅 300 token（本系统刻意控制），单独不构成长前缀缓存；
故本计量用一个「生产规模」的大前缀（system + 项目工具清单 + 对话模板，>1500 token），
连续 6 次同前缀请求，量化 provider 侧缓存命中率。首帧为 cache 创建（miss），其后应命中。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # edu-agent/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/

from scripts.eval import llm_client
from app.ai.prompt_cache import ensure_min_prefix, evaluate_cache_sev, evaluate_hit_rate


def build_big_prefix(min_tokens: int = 1600) -> str:
    """构造 ≥min_tokens 的「生产规模」稳定前缀（system + 工具清单 + 对话模板三层组织 R5）。

    task-C2：经 ensure_min_prefix 保证前缀跨过 1024 缓存门槛（provider 才真正缓存），
    且填充注释逐字节稳定，两次构建完全一致。
    """
    sys_prompt = (
        "你是EduAgent生产级学习助手。遵循以下规则与工具规范。"
        "1 意图路由：chitchat/knowledge/tool/learning；2 检索与工具；3 输出JSON契约；"
        "4 安全与脱敏；5 降级与重试。"
    )
    tools = []
    for i in range(24):
        tools.append({
            "tool_name": f"edu_tool_{i:02d}",
            "description": f"工具{i}：用于教育场景第{i}个内建能力；何时用/何时不用/参数域/返回结构/幂等副作用均见规范。",
            "input_schema": {"type": "object", "properties": {"key": {"type": "string"}, "value": {"type": "integer"}}},
        })
    prefix = sys_prompt + "\n## 可用工具清单\n" + json.dumps(tools, ensure_ascii=False)
    return ensure_min_prefix(prefix, min_tokens=min_tokens)


NONCE = ["first", "second", "third", "fourth", "fifth", "sixth"]


def meter(rounds: int = 6, min_tokens: int = 1600, *, model: str = "fast") -> dict:
    """真实 LLM 命中率计量（task97 R5 + task-C2 ④）。

    注意（测试窗口纪律）：真实 LLM 调用仅测试窗口 12:00-14:00 / 18:00-9:00 内执行；
    窗口外调用应由调用方用 mock llm_client 注入 usage 走 evaluate_hit_rate 验证计量/SEV 逻辑。
    """
    prefix = build_big_prefix(min_tokens)
    from app.ai.compaction import estimate_tokens
    prefix_tokens = estimate_tokens(prefix)
    rows = []
    hit_acc = miss_acc = 0
    for i in range(rounds):
        user = f"这是第 {NONCE[i]} 个请求，请返回稳定系统状态 JSON。"
        out = llm_client.call(
            messages=[{"role": "system", "content": prefix}, {"role": "user", "content": user}],
            model=model, temperature=0.0, max_tokens=60,
        )
        c = llm_client.cache_stats_from_usage(out["usage"])
        hit_acc += c["cache_hit_tokens"]
        miss_acc += c["cache_miss_tokens"]
        rows.append({"round": i + 1, **c, "prompt_tokens": int(out["usage"].get("prompt_tokens") or 0),
                     "latency_ms": round(out["latency_ms"], 1)})
    total = hit_acc + miss_acc
    hit_rate = round(hit_acc / total, 4) if total else 0.0
    sev = evaluate_cache_sev(hit_rate)
    return {
        "rounds": rows,
        "total_hit_tokens": hit_acc,
        "total_miss_tokens": miss_acc,
        "hit_rate": hit_rate,
        "sev": sev,
        "min_prefix_tokens": min_tokens,
        "prefix_tokens": prefix_tokens,
        "model": model,
        "provider": "deepseek usage.prompt_cache_*",
    }


def _demo_hit_rate(usage_list: list[dict], *, model: str = "fast", layer: str = "project") -> dict:
    """demo 包装：直接委托 prompt_cache.evaluate_hit_rate（单一真源）。"""
    return evaluate_hit_rate(usage_list, model=model, layer=layer)


if __name__ == "__main__":
    import datetime as _dt
    now_h = _dt.datetime.now().hour
    in_window = (12 <= now_h < 14) or (now_h >= 18) or (now_h < 9)
    if not in_window:
        print("[cache_meter] 当前非测试窗口（12:00-14:00 / 18:00-9:00），跳过真实 LLM；改用 mock 计量示例。")
        sample = [
            {"prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 1500},   # round1 创建缓存
            {"prompt_cache_hit_tokens": 1400, "prompt_cache_miss_tokens": 100},  # round2 命中
            {"prompt_cache_hit_tokens": 1450, "prompt_cache_miss_tokens": 50},
            {"prompt_cache_hit_tokens": 1380, "prompt_cache_miss_tokens": 120},
            {"prompt_cache_hit_tokens": 1420, "prompt_cache_miss_tokens": 80},
            {"prompt_cache_hit_tokens": 1410, "prompt_cache_miss_tokens": 90},
        ]
        out = _demo_hit_rate(sample)
    else:
        rounds = int(os.environ.get("CACHE_ROUNDS", "6"))
        out = meter(rounds)
    print(json.dumps(out, ensure_ascii=False, indent=2))