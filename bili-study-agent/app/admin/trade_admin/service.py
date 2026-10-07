"""
管理端运营聚合 service（Season-2 后端缺口 · 需求 A）。

对 DB 直接写聚合 SQL（order / payment_record / student_cohort_rel / series 真实表），
返回裸 dict，交由 RespWrapMiddleware 统一包 {code:0, message:"ok", data}。

数据口径（真实，不造假；表为空则返回 0/[]）：
- top_series：热门课程榜，按有效订单数倒序 top N
- revenue：营收聚合（总营收 / 今日 / 近7日 / 支付成功单数）
- orders：订单概况（总订单数 + 各状态计数）
"""
from __future__ import annotations

from app.database import fetch_all, fetch_one

# 营收口径：已进入收款状态的订单状态（含部分退款/已退款单，均计入营收）
_REVENUE_STATUSES = ("paid", "completed", "partial_refunded", "refunded")


async def get_overview(top_n: int = 10) -> dict:
    """聚合运营概览（热门榜 / 营收 / 订单概况）。"""

    # ── 1. 热门课程榜（按订单数倒序 top N） ──
    top_series = await fetch_all(
        """
        SELECT s.id AS series_id, s.series_name, s.sale_status,
               COUNT(DISTINCT o.id) AS order_count,
               COALESCE((
                 SELECT COUNT(DISTINCT scr.id) FROM student_cohort_rel scr
                 JOIN series_cohort sc2 ON sc2.id = scr.cohort_id
                 WHERE sc2.series_id = s.id AND scr.enroll_status = 'active'
               ), 0) AS active_student_count
        FROM `order` o
        JOIN order_item oi ON oi.order_id = o.id
        JOIN series_cohort c ON c.id = oi.cohort_id
        JOIN series s ON s.id = c.series_id
        GROUP BY s.id, s.series_name, s.sale_status
        ORDER BY order_count DESC
        LIMIT %s
        """,
        (top_n,),
    )
    top_series = [
        {
            "series_id": int(r["series_id"]),
            "title": r["series_name"],
            "sale_status": r["sale_status"],
            "order_count": int(r["order_count"]),
            "active_student_count": int(r["active_student_count"]),
        }
        for r in top_series
    ]

    # ── 2. 营收聚合（量纲：订单 payable_amount） ──
    revenue_agg = await fetch_one(
        """
        SELECT
          ROUND(SUM(CASE WHEN order_status IN ('paid','completed','partial_refunded','refunded')
                         THEN payable_amount ELSE 0 END), 2) AS total_revenue,
          ROUND(SUM(CASE WHEN order_status IN ('paid','completed','partial_refunded','refunded')
                         AND DATE(paid_at) = CURDATE() THEN payable_amount ELSE 0 END), 2) AS today_revenue,
          ROUND(SUM(CASE WHEN order_status IN ('paid','completed','partial_refunded','refunded')
                         AND paid_at >= DATE_SUB(NOW(), INTERVAL 7 DAY) THEN payable_amount ELSE 0 END), 2) AS revenue_7d,
          SUM(CASE WHEN order_status IN ('paid','completed','partial_refunded','refunded') THEN 1 ELSE 0 END) AS paid_order_count,
          COUNT(*) AS total_orders
        FROM `order`
        """
    )
    revenue_agg = revenue_agg or {}
    total_orders_all = int(revenue_agg.get("total_orders") or 0)
    revenue = {
        "total_revenue": float(revenue_agg.get("total_revenue") or 0),
        "today_revenue": float(revenue_agg.get("today_revenue") or 0),
        "revenue_7d": float(revenue_agg.get("revenue_7d") or 0),
        "paid_order_count": int(revenue_agg.get("paid_order_count") or 0),
    }

    # ── 3. 订单概况（总订单数 + 各状态计数） ──
    status_rows = await fetch_all("SELECT order_status, COUNT(*) AS c FROM `order` GROUP BY order_status")
    by_status = {r["order_status"]: int(r["c"]) for r in status_rows}
    orders = {
        "total": total_orders_all,
        "by_status": by_status,
    }

    return {
        "top_series": top_series,
        "revenue": revenue,
        "orders": orders,
    }