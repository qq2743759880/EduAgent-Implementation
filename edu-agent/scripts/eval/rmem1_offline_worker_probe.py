# -*- coding: utf-8 -*-
"""W-NEXT-R-MEM-001 离线 worker 实测（任务书验收点 6）。

真实链路：init Redis（真 broker）+ init MySQL（真 user_memory_event 表）→
真实 MemoryWriteQueue consumer（start_consumer，非 pump 模拟）消费一条**合成对话**：
  1) enqueue_turn_window（R08 v=2 载荷，窗内含密钥/手机号——R04-b 入队脱敏）；
  2) 等待真实 worker 消费：LLM 抽取显式关闭（MEMORY_LLM_EXTRACT_ENABLED=False，
     真实 LLM 窗口不可用 → 契约+离线 worker 实测口径），规则抽取确定性；
  3) 断言 user_memory_event 真实落库行：HEAD 判据 valid_to IS NULL AND event_type<>'delete'，
     content 已脱敏（sk- 密钥/手机号不可见）、语义保留（Python 偏好）；
  4) 清理：物理删除本次落库行（按 trace 实测 user_id 精确删除，不动存量数据）。

运行：
    cd edu-agent && .venv/Scripts/python.exe scripts/eval/rmem1_offline_worker_probe.py
退出码 0=全断言通过；非 0=失败。
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from loguru import logger

PROBE_USER_ID = 990_001  # 实测专用 user_id（清理时精确删除，不触碰真实用户数据）
SYNTHETIC_WINDOW = [
    {"role": "user", "content": "记住 我喜欢Python，我的 API key 是 sk-RMEM1probeKEY12345678"},
    {"role": "assistant", "content": "好的，已记录你的偏好，手机号 13800138000"},
]
SECRET_TOKEN = "sk-RMEM1probeKEY12345678"
SECRET_PHONE = "13800138000"


async def main() -> int:
    from app.config import settings
    from app import database as db

    await db.init_mysql()
    await db.init_redis()
    settings.MEMORY_LLM_EXTRACT_ENABLED = False  # 真实 LLM 窗口不可用：规则路径确定性实测

    from app.ai.memory.queue import MemoryWriteQueue
    from app.ai.memory.service import build_turn_window
    from app.ai.memory.store import MemoryStore
    from app.ai.memory.persistence import build_persistence

    persistence = build_persistence()  # 生产同款：SqlEventMemoryPersistence（user_memory_event）
    store = MemoryStore(persistence)
    queue = MemoryWriteQueue(store)

    # 0) 前置清理（防上次运行残留）
    await db.execute_write("DELETE FROM user_memory_event WHERE user_id = %s", (PROBE_USER_ID,))

    # 1) 真实起 worker（lifespan 同款 start_consumer）
    queue.start_consumer()
    try:
        window = build_turn_window(SYNTHETIC_WINDOW[:-1], query="", answer="") or []
        # 模拟 chat 调用点：build_turn_window(历史, query=..., answer=...)
        full_window = build_turn_window(
            [], query=SYNTHETIC_WINDOW[0]["content"], answer=SYNTHETIC_WINDOW[1]["content"]
        )
        assert full_window[-1]["role"] == "assistant", "R08：完整窗必须含 assistant 半边"
        ok = await queue.enqueue_turn_window(PROBE_USER_ID, full_window)
        assert ok is True, "enqueue_turn_window 应成功"

        # 2) 等真实消费循环完成（turn 消费 → 候选回灌 → candidate 写库；以落库行为准，
        #    向量 upsert（BGE-M3 加载）可能拖慢 candidate 计数统计，不影响断言正确性）
        deadline = asyncio.get_event_loop().time() + 30
        while asyncio.get_event_loop().time() < deadline:
            row = await db.fetch_one(
                "SELECT COUNT(*) AS c FROM user_memory_event WHERE user_id = %s",
                (PROBE_USER_ID,),
            )
            if int(row["c"] or 0) >= 1 and queue.stats["turn"] >= 1:
                break
            await asyncio.sleep(0.3)
        print(f"[probe] worker stats: {queue.stats}")

        # 3) user_memory_event 落库行断言（先查事件表——AGENTS.md 教训 11 口径）
        rows = await db.fetch_all(
            "SELECT id, entity_id, event_type, valid_to, event_type, content, importance "
            "FROM user_memory_event WHERE user_id = %s ORDER BY id",
            (PROBE_USER_ID,),
        )
        print(f"[probe] user_memory_event rows = {len(rows)}")
        for r in rows:
            print(f"  id={r['id']} entity={r['entity_id']} type={r['event_type']} "
                  f"valid_to={r['valid_to']} content={r['content'][:80]}")
        head_rows = [
            r for r in rows if r["valid_to"] is None and r["event_type"] != "delete"
        ]
        assert head_rows, "应有 HEAD 落库行（valid_to IS NULL AND event_type<>'delete'）"
        blob = "\n".join(r["content"] or "" for r in head_rows)
        assert SECRET_TOKEN not in blob, "P0：密钥明文泄漏进 user_memory_event！"
        assert SECRET_PHONE not in blob, "P0：手机号明文泄漏进 user_memory_event！"
        assert any("Python" in (r["content"] or "") for r in head_rows), "语义内容应保留（脱敏不损语义）"
        assert any("***REDACTED***" in (r["content"] or "") for r in head_rows), "密钥应已掩码"
        print(f"[probe] PASS：HEAD {len(head_rows)} 行全部脱敏且语义保留")
        return 0
    finally:
        # 4) 清理：物理删除实测行 + 停 worker + 关连接
        await db.execute_write(
            "DELETE FROM user_memory_event WHERE user_id = %s", (PROBE_USER_ID,)
        )
        remaining = await db.fetch_one(
            "SELECT COUNT(*) AS c FROM user_memory_event WHERE user_id = %s", (PROBE_USER_ID,)
        )
        assert int(remaining["c"] or 0) == 0, "清理后不应残留实测行"
        print("[probe] 清理完成：user_memory_event 无 990001 残留")
        await queue.stop_consumer(timeout=5)
        await db.close_redis()
        await db.close_mysql()
        logger.remove()
        sys.stdout.flush()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
