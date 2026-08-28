"""task-S1-② 契约测试：hitl_approval 四审计字段 explain_text/propose_text/operator/trace_id 可写。

验收目标：通过生产路径 MysqlHitlStore.create 写入一条带显式四审计字段的记录，
再用 store.get 读回断言四字段真实落库；并通过 store.update 验证
operator/explain_text/propose_text 在 allowed 集合内可被改写（审计可追）。

依据：
- app/ai/hitl_gate.py MysqlHitlStore.create 显式 INSERT explain_text/propose_text/operator/trace_id
- update 的 allowed 集合含 explain_text/propose_text/operator
- 线上表 hitl_approval 已存在这四列（explain_text/propose_text 为 text NULL，
  operator/trace_id 为 varchar(64) NOT NULL）
"""
import asyncio
import os
import sys
import time
import uuid

sys.path.insert(0, ".")

# 本地 MySQL 默认口令；若环境已注入 MYSQL_PASSWORD 则不覆盖
os.environ.setdefault("MYSQL_PASSWORD", "123456")

from app.database import init_mysql, close_mysql, execute_write
from app.ai.hitl_gate import MysqlHitlStore


async def _exercise() -> str:
    await init_mysql()
    try:
        store = MysqlHitlStore()
        aid = f"crit-s1-{uuid.uuid4().hex[:10]}"
        rec = {
            "action_id": aid,
            "action_type": "tool_call",
            "target": "crit-s1-target",
            "params_json": "{}",
            "risk_level": "L2",
            "status": "pending",
            "explain_text": "EXPLAIN_批判落实_S1_解释文本",
            "propose_text": "PROPOSE_批判落实_S1_提议文本",
            "operator": "crit-operator-007",
            "approver": "",
            "trace_id": "trace-crit-s1-xyz123",
            "ai_verdict": "",
            "ai_reason": "",
            "ai_confidence": None,
            "reject_count": 0,
            "server_id": None,
            "created_at": time.time(),
        }
        await store.create(rec)

        got = await store.get(aid)
        assert got is not None, "create 后 store.get 读不到记录"
        assert got["explain_text"] == rec["explain_text"], \
            f"explain_text 未真实落库: {got.get('explain_text')!r}"
        assert got["propose_text"] == rec["propose_text"], \
            f"propose_text 未真实落库: {got.get('propose_text')!r}"
        assert got["operator"] == rec["operator"], \
            f"operator 未真实落库: {got.get('operator')!r}"
        assert got["trace_id"] == rec["trace_id"], \
            f"trace_id 未真实落库: {got.get('trace_id')!r}"

        # 更新路径：operator/explain_text/propose_text 在 allowed 集合，应可改写
        await store.update(aid, explain_text="U_EXP", propose_text="U_PRO", operator="U_OP")
        g2 = await store.get(aid)
        assert g2["explain_text"] == "U_EXP", f"update explain_text 失败: {g2.get('explain_text')!r}"
        assert g2["propose_text"] == "U_PRO", f"update propose_text 失败: {g2.get('propose_text')!r}"
        assert g2["operator"] == "U_OP", f"update operator 失败: {g2.get('operator')!r}"

        # 逻辑删除，不污染审计表
        await execute_write("UPDATE hitl_approval SET yn=0 WHERE action_id=%s", (aid,))
        return aid
    finally:
        await close_mysql()


def test_audit_fields_writable():
    aid = asyncio.run(_exercise())
    assert aid.startswith("crit-s1-"), "未返回有效 action_id"


if __name__ == "__main__":
    asyncio.run(_exercise())
    print("ALL OK: S1-② hitl_approval 四审计字段 explain/propose/operator/trace_id 可真实读写")
