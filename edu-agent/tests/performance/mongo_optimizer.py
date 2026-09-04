"""
MongoDB 深度优化脚本（Phase 2 性能调优）

面试考点：
- 索引类型：单字段、复合、文本、TTL、地理空间
- 聚合管道：$match → $group → $sort → $project 的执行顺序优化
- TTL 索引：自动过期删除（对话日志、临时会话）
- Change Stream：实时数据变更监听（代替轮询）
- 慢查询分析：explain("executionStats") 查看执行统计

用法（需在 MongoDB shell 或 motor 中执行）：
  python tests/performance/mongo_optimizer.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.database import get_mongo_db


# ============================================================
# MongoDB 索引创建脚本
# ============================================================
MONGO_INDEXES = {
    # ── 对话会话（chat_sessions） ──
    "chat_sessions": [
        # 复合索引：按用户查会话 + 按最后消息时间排序
        {"keys": [("user_id", 1), ("last_message_at", -1)], "name": "idx_user_lastmsg"},
        # 按会话 ID 查（高频）
        {"keys": [("session_id", 1)], "name": "idx_session_id", "unique": True},
        # 软删除过滤
        {"keys": [("yn", 1), ("user_id", 1)], "name": "idx_yn_user"},
    ],

    # ── 对话消息（chat_messages） ──
    "chat_messages": [
        # 按会话 ID + 时间排序（拉历史消息）
        {"keys": [("session_id", 1), ("created_at", 1)], "name": "idx_session_created"},
        # 按用户 ID 查（管理员看所有消息）
        {"keys": [("user_id", 1), ("created_at", -1)], "name": "idx_user_created"},
        # TTL 索引：90 天后自动删除旧消息（节省存储）
        {"keys": [("created_at", 1)], "name": "idx_ttl_created", "expireAfterSeconds": 90 * 86400},
    ],

    # ── 用户行为日志（user_activity_log） ──
    "user_activity_log": [
        {"keys": [("user_id", 1), ("timestamp", -1)], "name": "idx_user_ts"},
        {"keys": [("action_type", 1), ("timestamp", -1)], "name": "idx_action_ts"},
        # TTL：30 天自动清理
        {"keys": [("timestamp", 1)], "name": "idx_ttl_ts", "expireAfterSeconds": 30 * 86400},
    ],
}


async def create_indexes():
    """创建 MongoDB 索引（幂等：已存在则跳过）。"""
    db = get_mongo_db()
    created = 0
    for collection_name, indexes in MONGO_INDEXES.items():
        col = db[collection_name]
        existing = await col.index_information()
        for idx in indexes:
            idx_name = idx["name"]
            if idx_name in existing:
                continue
            try:
                keys = idx["keys"]
                kwargs = {"name": idx_name}
                if idx.get("unique"):
                    kwargs["unique"] = True
                if idx.get("expireAfterSeconds"):
                    kwargs["expireAfterSeconds"] = idx["expireAfterSeconds"]
                await col.create_index(keys, **kwargs)
                created += 1
                print(f"  ✅ {collection_name}.{idx_name}")
            except Exception as exc:
                print(f"  ❌ {collection_name}.{idx_name}: {exc}")
    print(f"  共创建 {created} 个新索引")
    return created


# ============================================================
# MongoDB 聚合管道示例
# ============================================================
async def demo_aggregation():
    """
    聚合管道示例：统计每个用户的对话活跃度。

    等价 SQL：
      SELECT user_id, COUNT(*) AS conversations, MAX(last_message_at) AS last_active
      FROM chat_sessions WHERE yn = 1
      GROUP BY user_id ORDER BY conversations DESC LIMIT 10
    """
    db = get_mongo_db()
    pipeline = [
        # $match：过滤（相当于 WHERE）
        {"$match": {"yn": 1}},

        # $group：分组聚合（相当于 GROUP BY）
        {"$group": {
            "_id": "$user_id",
            "conversations": {"$sum": 1},
            "total_messages": {"$sum": "$message_count"},
            "last_active": {"$max": "$last_message_at"},
        }},

        # $sort：排序（相当于 ORDER BY）
        {"$sort": {"conversations": -1}},

        # $limit：限制行数
        {"$limit": 10},

        # $project：字段投影（相当于 SELECT 指定列）
        {"$project": {
            "_id": 0,
            "user_id": "$_id",
            "conversations": 1,
            "total_messages": 1,
            "last_active": 1,
        }},
    ]

    try:
        cursor = db["chat_sessions"].aggregate(pipeline)
        results = await cursor.to_list(length=10)
        print(f"  聚合结果: {len(results)} 个活跃用户")
        for r in results:
            print(f"    user_id={r['user_id']} conversations={r['conversations']} last_active={r.get('last_active')}")
        return results
    except Exception as exc:
        print(f"  聚合失败（可能集合不存在或 MongoDB 未连接）: {exc}")
        return []


# ============================================================
# MongoDB Change Stream 示例
# ============================================================
async def demo_change_stream():
    """
    Change Stream 示例：监听对话消息的实时变更。

    面试考点：
    - Change Stream 基于 MongoDB Oplog，实时推送变更
    - 比轮询更高效（不需要定时查询）
    - 可以按 collection/database/deployment 级别监听
    - 支持过滤（只监听特定操作的变更）

    实际应用：
    - 新消息 → WebSocket 推送给前端
    - 用户行为 → 实时更新学习仪表盘
    - 数据变更 → 同步到 Elasticsearch 做全文搜索
    """
    db = get_mongo_db()
    try:
        # 监听 chat_messages 的 insert 操作
        pipeline = [{"$match": {"operationType": "insert"}}]
        change_stream = db["chat_messages"].watch(pipeline)

        print("  Change Stream 已启动（监听 chat_messages.insert）")
        print("  提示：在另一个终端插入一条消息即可看到实时推送")

        # 实际使用中应该用 async for 循环监听
        # async for change in change_stream:
        #     print(f"  新消息: {change['fullDocument']}")
        #     # 通过 WebSocket 推送给前端

        await change_stream.close()
    except Exception as exc:
        print(f"  Change Stream 不可用（需要 MongoDB Replica Set）: {exc}")


# ============================================================
# 主入口
# ============================================================
async def main():
    print("=" * 60)
    print("  EduAgent MongoDB 优化器")
    print("=" * 60)
    print()

    print("1. 创建索引")
    await create_indexes()
    print()

    print("2. 聚合管道示例（用户活跃度排名）")
    await demo_aggregation()
    print()

    print("3. Change Stream 示例")
    await demo_change_stream()
    print()

    print("完成！")


if __name__ == "__main__":
    asyncio.run(main())