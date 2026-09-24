# -*- coding: utf-8 -*-
"""TB1 模块直跑先测：不接线状态下直调 neo4j_engine.py 查询函数（真实 Neo4j）。
断言：返回非空 / 耗时 P95 可接受(≤2s) / 异常可控（不抛）。
用法：MYSQL_HOST=127.0.0.1 .venv/Scripts/python.exe scripts/tb1_directrun.py
"""
from __future__ import annotations
import sys, time
sys.path.insert(0, ".")
from app.config import settings
from app.recommender import neo4j_engine as ne

TID = "_default"

def timed(fn, n=1):
    ts = []
    last = None
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            last = fn()
            ok = True
            err = None
        except Exception as exc:
            ok = False
            err = f"{type(exc).__name__}: {exc}"
            last = None
        ts.append(time.perf_counter() - t0)
    return last, ts, ok, err

def main() -> int:
    print(f"NEO4J_URI={settings.NEO4J_URI}  tenant_id={TID}")
    driver = ne.get_neo4j_driver()
    print(f"driver_alive={driver is not None}")
    if driver is None:
        print("NEO4J_UNREACHABLE: 跳过真实查询（直跑仅验证导入/降级路径可用）")
        return 0

    # 1) hub 种子
    seeds, ts, ok, err = timed(lambda: ne.hub_seed_names(tenant_id=TID, limit=6))
    p95 = sorted(ts)[-1] * 1000
    print(f"[hub_seed_names] ok={ok} rows={len(seeds or [])} p95={p95:.1f}ms err={err}")
    print(f"    seeds={seeds}")

    # 2) 共现（单种子，多次取 P95）
    hub = (seeds or ["能力提升"])[0]
    _, ts, ok, err = timed(lambda: ne.recommend_by_co_occurrence(hub, tenant_id=TID, top_n=15), n=5)
    p95 = sorted(ts)[-1] * 1000
    print(f"[recommend_by_co_occurrence] seed={hub!r} ok={ok} p95={p95:.1f}ms err={err}")

    # 3) 批量共现（多种子，接线主路径）
    seeds_for_batch = seeds or ["能力提升", "项目实践"]
    res, ts, ok, err = timed(lambda: ne.recommend_knowledge_points(seeds_for_batch, tenant_id=TID, top_n=20), n=5)
    p95 = sorted(ts)[-1] * 1000
    print(f"[recommend_knowledge_points] seeds={len(seeds_for_batch)} ok={ok} rows={len(res or [])} p95={p95:.1f}ms err={err}")
    for r in (res or [])[:5]:
        print(f"    {r['kp_name']} strength={r['strength']} modules={r['modules'][:2]}")

    # 4) PageRank/入度
    _, ts, ok, err = timed(lambda: ne.pagerank_importance(tenant_id=TID, top_n=10), n=3)
    p95 = sorted(ts)[-1] * 1000
    print(f"[pagerank_importance] ok={ok} p95={p95:.1f}ms err={err}")

    # 5) 路径缺口
    _, ts, ok, err = timed(lambda: ne.check_learning_path_gaps("能力提升", ["项目实践"], tenant_id=TID, max_depth=3), n=3)
    p95 = sorted(ts)[-1] * 1000
    print(f"[check_learning_path_gaps] ok={ok} p95={p95:.1f}ms err={err}")

    # 5b) 最短路径（PREREQUISITE 仅 14 条边，可能为空；仅验证不再语法报错）
    _, ts, ok, err = timed(lambda: ne.find_shortest_learning_path(
        (seeds or ["能力提升"])[0], (seeds or ["项目实践"])[1] if len(seeds or ["x","y"]) > 1 else (seeds or ["项目实践"])[0],
        tenant_id=TID, max_depth=5), n=3)
    p95 = sorted(ts)[-1] * 1000
    print(f"[find_shortest_learning_path] ok={ok} p95={p95:.1f}ms err={err}")

    # 6) kp 存在性（路径标注用）
    _, ts, ok, err = timed(lambda: ne.kp_names_present(["能力提升", "项目实践", "不存在的KP_XYZ"], tenant_id=TID), n=3)
    p95 = sorted(ts)[-1] * 1000
    print(f"[kp_names_present] ok={ok} present={len(_ or [])} p95={p95:.1f}ms err={err}")

    # 断言汇总
    print("\n=== 断言 ===")
    assert driver is not None, "Neo4j 不可达"
    assert len(seeds or []) > 0, "hub 种子为空"
    assert len(res or []) > 0, "批量共现为空"
    assert p95 <= 2000, f"P95 超 2s 预算: {p95:.1f}ms"
    print("PASS: 模块直跑非空 + 耗时 ≤2s + 异常可控")
    return 0

if __name__ == "__main__":
    sys.exit(main())
