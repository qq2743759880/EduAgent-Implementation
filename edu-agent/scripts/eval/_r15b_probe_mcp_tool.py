# -*- coding: utf-8 -*-
"""R15b 只读对账探针：真实工具注册面（executor 内置 + DB mcp_tool）。

用途：为 test-reports/R15b-completion-report.md 的「G1 逐名对账表」提供可复跑证据。
**全程只读**（仅 SELECT），不写库、不调 LLM、不起服务。

跑法（在 edu-agent/ 下）：
    .venv/Scripts/python.exe scripts/eval/_r15b_probe_mcp_tool.py

输出：
    1) executor.py 源码中 register_builtin_tool(...) 的真实内置工具名
    2) mcp_tool 表（yn=1）真实工具行
    3) 10 个契约语义候选名的反向核验（应全部 0 命中 = 未注册）
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]          # edu-agent/
sys.path.insert(0, str(_REPO))

_EXECUTOR = _REPO / "app" / "mcp" / "executor.py"

# 契约中文语义臆译出来的 10 个候选工具名（R15 原表）
PENDING_CANDIDATES = [
    "course_create", "course_update", "course_delete",
    "question_create", "question_update", "question_delete",
    "favorite_add", "points_change", "knowledge_import", "order_create",
]


def probe_builtin() -> list[str]:
    """① executor 源码实采内置工具名。"""
    src = _EXECUTOR.read_text(encoding="utf-8")
    names = sorted(set(re.findall(r'register_builtin_tool\(\s*"([^"]+)"', src)))
    print(f"[builtin] register_builtin_tool 实采 {len(names)} 个: {names}")
    for i, line in enumerate(src.splitlines(), 1):
        if "register_builtin_tool(" in line and '"' in line:
            print(f"  executor.py:{i}: {line.strip()}")
    # 反向核验：候选名不得出现在 executor 源码里
    hits = {n: len(re.findall(re.escape(n), src)) for n in PENDING_CANDIDATES}
    bad = {n: c for n, c in hits.items() if c}
    print(f"[builtin] 候选名在 executor.py 命中: {bad or '全部 0 命中 ✔'}")
    return names


async def probe_mcp() -> set[str]:
    """②③ DB mcp_tool 真实行 + 候选名反向核验（只读 SELECT）。"""
    import asyncmy
    from app.config import settings

    conn = await asyncmy.connect(
        host=settings.MYSQL_HOST, port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
        db=settings.MYSQL_DATABASE, autocommit=True,
    )
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT t.id, t.tool_name, t.server_id, s.server_code, s.enabled "
                "FROM mcp_tool t LEFT JOIN mcp_server s ON s.id=t.server_id "
                "WHERE t.yn=1 ORDER BY t.tool_name"
            )
            rows = await cur.fetchall()
            print(f"[mcp_tool] yn=1 共 {len(rows)} 行")
            for r in rows:
                print(f"  id={r[0]} tool={r[1]!r} server_id={r[2]} server_code={r[3]!r} enabled={r[4]}")

            ph = ",".join(["%s"] * len(PENDING_CANDIDATES))
            await cur.execute(
                f"SELECT tool_name FROM mcp_tool WHERE tool_name IN ({ph})",
                tuple(PENDING_CANDIDATES),
            )
            found = [r[0] for r in await cur.fetchall()]
            print(f"[mcp_tool] 候选名反向核验命中: {found or '空集 ✔（10 名全部未注册）'}")
            return {str(r[1]) for r in rows}
    finally:
        conn.close()


def main() -> None:
    builtin = probe_builtin()
    mcp = asyncio.run(probe_mcp())
    print(f"[summary] 真实注册面 = {len(builtin)} 内置 + {len(mcp)} MCP = {len(set(builtin) | mcp)} 个")
    print(f"[summary] 全量清单: {sorted(set(builtin) | mcp)}")


if __name__ == "__main__":
    main()
