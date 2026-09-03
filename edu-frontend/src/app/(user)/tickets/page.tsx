/**
 * /tickets — 我的工单（Season-2 React，task100）
 *   列表（分页）+ 【新建工单】按钮 → 创建成功跳转详情
 *   详情见子路由 /tickets/[ticketId]
 *   受保护路由：客户端 TicketsClient hydrate 后未登录 → 跳 /login?redirect=/tickets
 *   数据来源：契约⑫ GET /api/trade/after_sales/tickets（task22 已实现）
 */
import { Suspense } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { Loader2 } from "lucide-react";
import TicketsClient from "./_components/TicketsClient";

export const metadata: Metadata = {
  title: "我的工单 · EduAgent",
  description: "查看你的咨询、申诉与售后工单，并可新建与追评。",
};

export const dynamic = "force-dynamic";

export default function TicketsPage() {
  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-6 md:px-6 md:py-10">
      <nav aria-label="面包屑" className="mb-4 flex flex-wrap items-center gap-1.5 text-[0.8rem] text-foreground/70">
        <Link className="font-semibold text-candy-blue hover:underline" href="/me">个人中心</Link>
        <span aria-hidden="true" className="opacity-50">›</span>
        <span className="font-bold text-foreground">我的工单</span>
      </nav>
      <header className="mb-6 flex items-center gap-3.5">
        <span aria-hidden="true" className="text-4xl drop-shadow-[0_4px_0_rgba(31,31,31,0.15)]">🎫</span>
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-foreground md:text-[1.625rem]">我的工单</h1>
          <p className="mt-1 text-[0.8rem] text-foreground/60">
            咨询、人工申诉与售后处理进度都在这里
          </p>
        </div>
      </header>
      <Suspense
        fallback={
          <div className="flex min-h-[50vh] items-center justify-center text-sm text-foreground/60">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            正在加载你的工单…
          </div>
        }
      >
        <TicketsClient />
      </Suspense>
    </div>
  );
}