/**
 * /orders — 我的订单（Season-2 React，task100）
 *   Tabs: 全部 / 待支付(pending) / 已支付(paid+completed+partial_refunded) / 已取消+已退款(cancelled+refunded)
 *   受保护路由：客户端 OrdersClient hydrate 后未登录 → 跳 /login?redirect=/orders
 *   数据来源：契约⑧ GET /api/trade/orders（task17 已实现）+ 订单详情 getOrder
 */
import { Suspense } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { Loader2 } from "lucide-react";
import OrdersClient from "./_components/OrdersClient";

export const metadata: Metadata = {
  title: "我的订单 · EduAgent",
  description: "查看你的课程订单、支付记录与退款进度。",
};

export const dynamic = "force-dynamic";

export default function OrdersPage() {
  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-6 md:px-6 md:py-10">
      <nav aria-label="面包屑" className="mb-4 flex flex-wrap items-center gap-1.5 text-[0.8rem] text-foreground/70">
        <Link className="font-semibold text-candy-blue hover:underline" href="/me">个人中心</Link>
        <span aria-hidden="true" className="opacity-50">›</span>
        <span className="font-bold text-foreground">我的订单</span>
      </nav>
      <header className="mb-6 flex items-center gap-3.5">
        <span aria-hidden="true" className="text-4xl drop-shadow-[0_4px_0_rgba(31,31,31,0.15)]">🧾</span>
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-foreground md:text-[1.625rem]">我的订单</h1>
          <p className="mt-1 text-[0.8rem] text-foreground/60">
            课程报名订单、支付记录与退款申请都在这里
          </p>
        </div>
      </header>
      <Suspense
        fallback={
          <div className="flex min-h-[50vh] items-center justify-center text-sm text-foreground/60">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            正在加载我的订单…
          </div>
        }
      >
        <OrdersClient />
      </Suspense>
    </div>
  );
}