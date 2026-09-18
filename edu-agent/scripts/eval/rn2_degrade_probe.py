# -*- coding: utf-8 -*-
"""R-N2 降级实测探针：Neo4j 黑洞（不可达）下 graph_expand 通道不得拖垮检索主链。

方法：进程内把 NEO4J_URI 指向不可路由黑洞地址（TEST-NET-1 10.255.255.1，SYN 无响应，
模拟 Neo4j 宕机/断连），KG_EXPAND_ENABLED=True 走真实 retrieve_three_channel：
- 主链断言：docs 正常返回（Milvus/rerank 不受影响）；
- 预算断言：kg_expand 通道耗时 ≤ KG_EXPAND_TIMEOUT_MS 预算（首查含同步 driver
  懒初始化挂起也必须被 800ms 硬顶放弃——kg_bridge 线程化 + wait_for 回归防线）；
- 留痕断言：degraded_reason 含 kg_expand:*，绝不 500。

用法（edu-agent/ 下）：
  NEO4J_URI_BLACKHOLE=1 .venv/Scripts/python.exe scripts/eval/rn2_degrade_probe.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# 黑洞注入必须在 import app.config 之前（settings 读 env）
if os.environ.get("NEO4J_URI_BLACKHOLE") == "1":
    os.environ["NEO4J_URI"] = "bolt://10.255.255.1:7687"

from app.config import settings  # noqa: E402


async def main() -> int:
    from app.auth import UserRole
    from app.chat.retriever import retrieve_three_channel

    settings.KG_EXPAND_ENABLED = True
    print(f"[degrade] NEO4J_URI={settings.NEO4J_URI}（黑洞）KG_EXPAND_ENABLED={settings.KG_EXPAND_ENABLED}")
    print(f"[degrade] 预算 KG_EXPAND_TIMEOUT_MS={settings.KG_EXPAND_TIMEOUT_MS}")

    # warmup：冷 BGE-M3 encode ~13s > Milvus 8s 预算（与 rn2_dualrun 同教训），
    # 先热透 GPU/sidecar，否则测的是「Milvus 超时」而非「kg 降级」。
    for attempt in range(1, 4):
        b = await retrieve_three_channel(
            "warmup 线性代数特征值预热查询",
            user_id=1, role=UserRole.STUDENT,
            use_hyde=False, enable_graph=False,
            top_k=5, final_max_k=5, cutoff_drop_ratio=1.0,
        )
        if "Milvus" not in (b.degraded_reason or ""):
            break
        print(f"[degrade] warmup 第 {attempt} 轮未热透，重试")

    async def _one(i: int, kg_on: bool):
        settings.KG_EXPAND_ENABLED = bool(kg_on)
        t0 = time.perf_counter()
        b = await retrieve_three_channel(
            f"线性代数特征值降级实测第{i}问",
            user_id=1, role=UserRole.STUDENT,
            use_hyde=False, enable_graph=False,
            top_k=5, final_max_k=5, cutoff_drop_ratio=0.40,
        )
        lat = (time.perf_counter() - t0) * 1000
        kg_reason = next(
            (p for p in (b.degraded_reason or "").split("；") if "kg_expand" in p), None
        )
        return round(lat, 1), len(b.docs), kg_reason

    on_runs: list[tuple[float, int, str | None]] = []
    for i in range(5):
        r = await _one(i, kg_on=True)
        on_runs.append(r)
        print(f"[degrade] on q{i}: total={r[0]}ms docs={r[1]} kg_reason={r[2]}")

    off_runs: list[tuple[float, int, str | None]] = []
    for i in range(2):
        r = await _one(100 + i, kg_on=False)
        off_runs.append(r)
        print(f"[degrade] off q{i}: total={r[0]}ms docs={r[1]} kg_reason={r[2]}")

    n_docs_ok = all(c > 0 for _l, c, _r in on_runs)
    all_flagged = all(r and r.startswith("kg_expand:") for _l, _c, r in on_runs)
    budget_cap_ok = all(
        r == "kg_expand:timeout(0.8s)" or r == "kg_expand:neo4j_not_connected"
        for _l, _c, r in on_runs
    ), tuple(r for _l, _c, r in on_runs)
    on_max, off_max = max(l for l, _c, _r in on_runs), max(l for l, _c, _r in off_runs)
    overhead_ms = round(on_max - off_max, 1)
    overhead_ok = overhead_ms <= 1200  # 800ms 预算 + 调度抖动
    print(f"[degrade] 断言: 主链有docs={n_docs_ok} 通道留痕={all_flagged} "
          f"降级原因受控{budget_cap_ok[0]}{'' if budget_cap_ok[0] else budget_cap_ok[1]} "
          f"通道开销(on最大-off最大)={overhead_ms}ms ≤1200ms={overhead_ok}")
    if not (n_docs_ok and all_flagged and budget_cap_ok[0] and overhead_ok):
        print("[degrade] FAIL")
        return 1
    print("[degrade] PASS — Neo4j 断连下通道静默跳过，主链无感（50301 范式对齐）")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
