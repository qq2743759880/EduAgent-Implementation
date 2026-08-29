# -*- coding: utf-8 -*-
"""task39 GWT②：72h 超时 escalation 幂等 + 并发安全复测（task28 批判①）。

批判原文：
    task28 批判①「72h 超时 escalation 触发可靠性」
      修复措施：缩短 TTL 模拟超时，验证 escalation 幂等 + 告警
      验收指标：缩短 TTL 下 escalation 正确建 high 工单且幂等；告警送达

做法（不改动生产数据）：
    1. 建一条**隔离的**超时退款单（refund_no 带 task39 前缀，applied_at = 100 小时前）
    2. 缩短 TTL：直接传 hours=72（cutoff=now-72h），applied_at=now-100h → 天然超时
    3. 三轮验证：
       T1 顺序幂等   ：连跑 3 次 escalate_refunds_older_than → 只有第 1 次建单
       T2 并发幂等   ：20 个协程并发跑同一单 → 工单/告警仍各只有 1 条（FOR UPDATE 串行化）
       T3 重复扫描   ：再跑 1 次全局扫描（不带 refund_id）→ 该单被 skipped，不重复建单
    4. 断言工单字段：priority_level=high / ticket_status=open / ticket_source=system_auto
       告警字段：alert_type=refund_anomaly / alert_source=scheduled_job / alert_status=pending
    5. 清理：软删（yn=0）本次造的数据，不动其它行

用法：
    .venv\\Scripts\\python scripts/verify_task39_escalation_idempotent.py

跑之前会做 MySQL 探活（共享 VM 掉线时直接报「环境未就绪」，避免把连接超时误读成
幂等失效）；跑完自动归档到 test-reports/task39-escalation-idempotent.{txt,json}。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
for _p in (str(_ROOT), str(_HERE)):  # _HERE 供 `import task39_report`
    if _p not in sys.path:
        sys.path.insert(0, _p)

from task39_report import archive, preflight, target_from_settings  # noqa: E402

from app.database import (  # noqa: E402
    close_mysql, execute_write, fetch_all, fetch_one, init_mysql,
)
from app.domains.trade.refund.hitl_graph import escalate_refunds_older_than  # noqa: E402

FAILED: list[str] = []
REPORT: list[str] = []
TAG = "T39"


def _log(msg: str) -> None:
    print(msg, flush=True)
    REPORT.append(msg)


def _check(cond: bool, name: str, detail: str = "") -> bool:
    if cond:
        _log(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))
    else:
        _log(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))
        FAILED.append(name)
    return cond


async def _make_refund() -> int:
    """造一条超时的 pending 退款单（applied_at = 100h 前，天然超过 72h cutoff）。"""
    tag = f"{TAG}{uuid.uuid4().hex[:8].upper()}"
    old = datetime.now() - timedelta(hours=100)
    # 复用一条真实单的全部外键维度（payment_id 受 fk_refund_request_payment 约束，
    # 不能填 0），仅改 refund_no + applied_at，保证插入合法且不污染业务语义。
    row = await fetch_one(
        "SELECT id, institution_id, order_id, order_item_id, payment_id, user_id, student_id"
        " FROM refund_request WHERE yn=1 ORDER BY id DESC LIMIT 1"
    )
    if not row:
        raise RuntimeError("refund_request 无可用样本，无法造隔离测试单")
    base = row
    new_id = await execute_write(
        "INSERT INTO refund_request (institution_id, refund_no, order_id, order_item_id, payment_id,"
        " user_id, student_id, refund_type, refund_reason, refund_status, apply_amount,"
        " yn, applied_at, created_at, updated_at)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s,'voluntary',%s,'pending',1.00,1,%s,NOW(),NOW())",
        (int(base["institution_id"]), tag, int(base["order_id"] or 0),
         int(base["order_item_id"] or 0), int(base["payment_id"] or 0),
         int(base["user_id"] or 0), int(base["student_id"] or 0),
         f"task39 幂等测试单 {tag}", old),
    )
    return int(new_id)


async def _count(refund_id: int) -> tuple[int, int]:
    t = await fetch_one(
        "SELECT COUNT(*) c FROM service_ticket WHERE refund_request_id=%s AND yn=1", (refund_id,))
    a = await fetch_one(
        "SELECT COUNT(*) c FROM risk_alert_event WHERE refund_request_id=%s AND yn=1", (refund_id,))
    return int(t["c"]), int(a["c"])


async def _cleanup(refund_id: int) -> None:
    await execute_write("UPDATE service_ticket SET yn=0 WHERE refund_request_id=%s", (refund_id,))
    await execute_write("UPDATE risk_alert_event SET yn=0 WHERE refund_request_id=%s", (refund_id,))
    await execute_write("UPDATE refund_request SET yn=0 WHERE id=%s", (refund_id,))


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="", help="结果文件名（默认 task39-escalation-idempotent）")
    args = ap.parse_args()

    _log("=" * 72)
    _log("task39 GWT② 72h escalation 幂等 + 并发安全复测")
    _log("=" * 72)
    # 预检：MySQL 不可达时 init_mysql/查询会以超时形式失败，容易被误读成「幂等失效」
    preflight([target_from_settings("mysql")], log=_log)
    await init_mysql()

    stats: dict[str, object] = {}
    rid = await _make_refund()
    _log(f"\n造单: refund_request.id={rid}（applied_at = now-100h，hours=72 → 天然超时）")
    try:
        # ---- T1 顺序幂等 ----
        _log("\n■ T1 顺序连跑 3 次 escalate_refunds_older_than(refund_id)")
        results = []
        for i in range(3):
            r = await escalate_refunds_older_than(hours=72, refund_id=rid)
            results.append(r)
            t, a = await _count(rid)
            _log(f"  第 {i+1} 次: {r}  → 工单={t} 告警={a}")
        t, a = await _count(rid)
        stats["T1"] = {"tickets": t, "alerts": a,
                       "escalated_seq": [r["escalated"] for r in results]}
        _check(t == 1 and a == 1, "T1 顺序 3 次只建 1 工单 + 1 告警", f"工单={t} 告警={a}")
        _check(results[0]["escalated"] == 1 and results[1]["escalated"] == 0
               and results[2]["escalated"] == 0,
               "T1 首次 escalated=1、后续 escalated=0（幂等）",
               f"escalated={[r['escalated'] for r in results]}")

        # ---- T2 并发幂等 ----
        _log("\n■ T2 20 并发跑同一单（验证 FOR UPDATE 串行化）")
        # 先把 T1 建的软删，让并发组从零开始
        await _cleanup(rid)
        await execute_write("UPDATE refund_request SET yn=1 WHERE id=%s", (rid,))
        t0, a0 = await _count(rid)
        _log(f"  并发前基线: 工单={t0} 告警={a0}")
        outs = await asyncio.gather(
            *[escalate_refunds_older_than(hours=72, refund_id=rid) for _ in range(20)]
        )
        t, a = await _count(rid)
        esc = sum(o.get("escalated", 0) for o in outs)
        _log(f"  20 并发完成: escalated 合计={esc}  工单={t} 告警={a}")
        stats["T2"] = {"tickets": t, "alerts": a, "escalated_sum": esc, "n_concurrent": 20}
        _check(t == 1 and a == 1, "T2 20 并发仍只建 1 工单 + 1 告警", f"工单={t} 告警={a}")

        # ---- T3 全局重复扫描 ----
        _log("\n■ T3 全局扫描（不带 refund_id）重复触发")
        r = await escalate_refunds_older_than(hours=72)
        t, a = await _count(rid)
        _log(f"  全局扫描: {r}  → 工单={t} 告警={a}")
        stats["T3"] = {"tickets": t, "alerts": a, "escalated": r.get("escalated")}
        _check(t == 1 and a == 1, "T3 全局扫描不重复建单", f"工单={t} 告警={a}")

        # ---- T4 字段正确性 ----
        _log("\n■ T4 建单字段正确性（§6.4 / task28 GWT③）")
        tk = await fetch_one(
            "SELECT priority_level, ticket_status, ticket_source, ticket_type, title"
            " FROM service_ticket WHERE refund_request_id=%s AND yn=1 LIMIT 1", (rid,))
        al = await fetch_one(
            "SELECT alert_type, alert_source, alert_status, risk_level"
            " FROM risk_alert_event WHERE refund_request_id=%s AND yn=1 LIMIT 1", (rid,))
        _log(f"  工单: {tk}")
        _log(f"  告警: {al}")
        _check(bool(tk) and tk["priority_level"] == "high" and tk["ticket_status"] == "open"
               and tk["ticket_source"] == "system_auto",
               "T4 工单 priority=high / status=open / source=system_auto",
               str(tk) if tk else "无工单")
        _check(bool(al) and al["alert_type"] == "refund_anomaly"
               and al["alert_source"] == "scheduled_job" and al["alert_status"] == "pending",
               "T4 告警 refund_anomaly / scheduled_job / pending",
               str(al) if al else "无告警")
        _check(bool(tk) and "72" in str(tk.get("title", "")),
               "T4 工单标题含超时阈值 72h", str(tk.get("title")) if tk else "无工单")
        stats["T4"] = {"ticket": dict(tk) if tk else None, "alert": dict(al) if al else None}
    finally:
        await _cleanup(rid)
        _log(f"\n清理完成：refund_request.id={rid} 及其工单/告警已软删（yn=0）")
        await close_mysql()

    archive(
        args.out or "task39-escalation-idempotent",
        REPORT,
        payload={"refund_id": rid, "stats": stats, "failed": FAILED},
        log=_log,
    )
    _log("\n" + ("✅ GWT② escalation 幂等复测通过" if not FAILED
                 else f"❌ 失败项 {len(FAILED)}: {FAILED}"))
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
