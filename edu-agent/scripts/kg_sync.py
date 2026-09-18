# -*- coding: utf-8 -*-
"""kg_sync.py —— KG-1 图谱同步 CLI（R-N1，Neo4j 写操作唯一入口）。

用法（在 edu-agent/ 下）：
  .venv/Scripts/python.exe scripts/kg_sync.py --mode full   # 备份→清 kg 子图→全量重建
  .venv/Scripts/python.exe scripts/kg_sync.py --mode inc    # 备份→增量 MERGE（不清旧）
  .venv/Scripts/python.exe scripts/kg_sync.py --mode inc --dry-run          # 只抽取打印，不写
  .venv/Scripts/python.exe scripts/kg_sync.py --mode inc --verify-idempotent  # 连跑两轮对比计数

纪律：
- 写前强制备份（--backup-dir，默认 data/kg_backup）——全量重建同样先备份再删；
- 幂等：MERGE by key + 确定性属性，重跑计数不变（--verify-idempotent 自证）；
- 全量重建只删 source='kg_sync' 子图，P1 遗留数据（CourseSeries/CourseModule/
  QuestionTag/旧 KnowledgePoint）不动（备份里含全图标签快照可审计）；
- Milvus 只读且失败降级（doc_chunk 缺席不阻断 Course/Chapter/KP 主体同步）。

性能注意：MySQL 抽取走 app.database 异步池（aiomysql），Neo4j 走官方同步驱动
（与 app/database.init_neo4j 同参），互不阻塞。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
os.chdir(BASE)

from app.config import settings  # noqa: E402


def _get_driver():
    from neo4j import GraphDatabase

    return GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        connection_timeout=float(settings.NEO4J_CONNECT_TIMEOUT or 3.0),
        max_transaction_retry_time=float(settings.NEO4J_CONNECT_TIMEOUT or 3.0),
    )


async def _collect_sources(limit_chunks: int, skip_milvus: bool) -> dict:
    from app.database import close_mysql, init_mysql
    from app.domains.kg import sync_core as sc

    # 修复（接手 R-N1）：fetch_all 依赖连接池，脚本脱离 uvicorn lifespan
    # 必须自行 init_mysql()/close_mysql()，否则 RuntimeError（实测 2026-09-18）。
    await init_mysql()
    try:
        sources = await sc.extract_mysql_sources()
    finally:
        await close_mysql()
    sources["chunks"], sources["mentions_chunk"] = [], []
    sources["belongs_chunk_course"], sources["belongs_chunk_chapter"] = [], []
    if not skip_milvus:
        chunks = sc.extract_doc_chunks(limit=limit_chunks)
        built = sc.build_chunk_graph(
            chunks, sources["kps"], sources["chapters"], sources["courses"]
        )
        sources.update(built)
    return sources


def _sync_once(mode: str, backup_dir: Path, limit_chunks: int, skip_milvus: bool) -> dict:
    """单轮同步：备份 → (full? 清子图) → 写入 → 返回 {backup, before, after, counts}。"""
    from app.domains.kg import sync_core as sc

    sources = asyncio.run(_collect_sources(limit_chunks, skip_milvus))
    driver = _get_driver()
    try:
        before = sc.kg_counts(driver, settings.NEO4J_DATABASE)
        backup_path = sc.backup_kg_subgraph(driver, backup_dir, settings.NEO4J_DATABASE)
        deleted = 0
        if mode == "full":
            deleted = sc.delete_kg_subgraph(driver, settings.NEO4J_DATABASE)
        written = sc.write_graph(driver, sources, settings.NEO4J_DATABASE)
        after = sc.kg_counts(driver, settings.NEO4J_DATABASE)
    finally:
        driver.close()
    return {
        "mode": mode,
        "backup": str(backup_path),
        "deleted_nodes": deleted,
        "written_batches_rows": written,
        "before": before,
        "after": after,
        "extract": {
            "courses": len(sources["courses"]),
            "chapters": len(sources["chapters"]),
            "kps": len(sources["kps"]),
            "chunks": len(sources.get("chunks", [])),
            "prereq": len(sources["prereq"]),
            "related": len(sources["related"]),
            "belongs": len(sources["belongs"])
            + len(sources.get("belongs_chunk_course", []))
            + len(sources.get("belongs_chunk_chapter", [])),
            "mentions": len(sources["mentions_chapter"])
            + len(sources.get("mentions_chunk", [])),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="KG-1 图谱同步（Neo4j 写操作唯一入口）")
    ap.add_argument("--mode", choices=["full", "inc"], required=True, help="full=全量重建 inc=增量 MERGE")
    ap.add_argument("--backup-dir", default="data/kg_backup", help="备份输出目录")
    ap.add_argument("--limit-chunks", type=int, default=5000, help="doc_chunk 抽取上限")
    ap.add_argument("--skip-milvus", action="store_true", help="跳过 doc_chunk（Milvus 降级演练）")
    ap.add_argument("--dry-run", action="store_true", help="只抽取与打印计划，不写 Neo4j")
    ap.add_argument("--verify-idempotent", action="store_true", help="连跑两轮并断言计数一致")
    args = ap.parse_args()

    backup_dir = BASE / args.backup_dir

    if args.dry_run:
        sources = asyncio.run(_collect_sources(args.limit_chunks, args.skip_milvus))
        print(json.dumps({"dry_run": True, "extract": {
            k: len(sources[k]) for k in
            ("courses", "chapters", "kps", "chunks", "belongs", "mentions_chapter",
             "mentions_chunk", "prereq", "related") if k in sources
        }}, ensure_ascii=False, indent=2))
        return 0

    r1 = _sync_once(args.mode, backup_dir, args.limit_chunks, args.skip_milvus)
    print("== PASS 1 ==")
    print(json.dumps(r1, ensure_ascii=False, indent=2, default=str))

    if args.verify_idempotent:
        r2 = _sync_once(args.mode, backup_dir, args.limit_chunks, args.skip_milvus)
        print("== PASS 2 ==")
        print(json.dumps(r2, ensure_ascii=False, indent=2, default=str))
        ok = r1["after"] == r2["after"]
        print("IDEMPOTENT:", "YES" if ok else "NO")
        if not ok:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
