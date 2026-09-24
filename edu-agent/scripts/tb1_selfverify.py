# -*- coding: utf-8 -*-
"""TB1 接线自验：hybrid_rank 三种场景。
① 开关开 + Neo4j 在线 → 响应含 source=neo4j 候选（且 graph_source=neo4j）
② Neo4j 不可达（强制 driver=None）→ 仍成功返回、全 source=mysql、不抛异常
③ 开关关 → 行为与现状一致（纯 MySQL 图，graph_source=mysql）
用法：MYSQL_HOST=127.0.0.1 .venv/Scripts/python.exe scripts/tb1_selfverify.py
"""
from __future__ import annotations
import asyncio, os, sys, types
sys.path.insert(0, ".")
os.environ.setdefault("MYSQL_HOST", "127.0.0.1")

from unittest import mock
from app.config import settings
from app.database import init_mysql
from app.recommender import engine, neo4j_engine

USER = 100003  # user000001 的 user_id（测试账号）

async def run_once(force_off: bool = False, force_down: bool = False):
    orig = settings.KG_RECOMMEND_ENABLED
    settings.KG_RECOMMEND_ENABLED = False if force_off else True
    engine._NE04J_HUB_CACHE["seeds"] = None  # 清 hub 缓存，避免跨场景污染
    if force_down:
        patcher = mock.patch.object(neo4j_engine, "get_neo4j_driver", return_value=None)
        patcher.start()
    try:
        out = await engine.hybrid_rank(USER, top_n=10, for_scene="NEXT")
    finally:
        if force_down:
            patcher.stop()
        settings.KG_RECOMMEND_ENABLED = orig
    return out

async def main() -> int:
    await init_mysql()
    failures = []

    # ① 开关开 + Neo4j 在线
    out1 = await run_once()
    neo_items = [it for it in out1.items if it.source == "neo4j"]
    print(f"[① 开+在线] graph_source={out1.graph_source} items={len(out1.items)} neo4j_items={len(neo_items)}")
    print("    sample:", [(it.item_name, it.source, round(it.score,3)) for it in out1.items[:3]])
    if out1.graph_source != "neo4j":
        failures.append("① graph_source 应为 neo4j")
    if not neo_items:
        failures.append("① 应至少含 1 个 source=neo4j 候选")

    # ② Neo4j 不可达（driver=None）
    try:
        out2 = await run_once(force_down=True)
        down_ok = True
        down_exc = None
    except Exception as exc:
        down_ok = False
        down_exc = f"{type(exc).__name__}: {exc}"
    print(f"[② 不可达]   ok={down_ok} exc={down_exc}")
    if not down_ok:
        failures.append(f"② 不可达应成功返回不抛异常: {down_exc}")
    else:
        if out2.graph_source != "mysql":
            failures.append("② graph_source 应为 mysql")
        if any(it.source != "mysql" for it in out2.items):
            failures.append("② 全部 item 应为 mysql")
        print(f"    graph_source={out2.graph_source} items={len(out2.items)} all_mysql={all(it.source=='mysql' for it in out2.items)}")

    # ③ 开关关 → 与现状一致（纯 MySQL 图）
    out3 = await run_once(force_off=True)
    print(f"[③ 关]       graph_source={out3.graph_source} items={len(out3.items)}")
    if out3.graph_source != "mysql":
        failures.append("③ graph_source 应为 mysql")
    if any(it.source != "mysql" for it in out3.items):
        failures.append("③ 全部 item 应为 mysql")
    # ③ 应与 ② 的候选集合一致（都是纯 MySQL 图路径）
    if down_ok:
        set2 = {it.item_code for it in out2.items}
        set3 = {it.item_code for it in out3.items}
        print(f"    ②vs③ item_code 交集={len(set2 & set3)}/{len(set3)}")
        if set2 != set3:
            failures.append("③ 开关关应与 Neo4j 不可达走同一 MySQL 路径（候选集合应一致）")

    print("\n=== 结果 ===")
    if failures:
        for f in failures:
            print("FAIL:", f)
        return 1
    print("PASS: ①②③ 均符合预期（开→neo4j 候选；不可达/关→mysql 降级且不报错）")
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
