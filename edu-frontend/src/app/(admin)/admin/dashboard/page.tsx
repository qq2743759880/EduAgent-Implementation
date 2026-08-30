/**
 * 管理端 · 仪表盘（/admin/dashboard，task55 重构）
 *  - KPI 指标卡(6)：GET /api/admin/users/dashboard/metrics（真实聚合，无 MOCK）
 *  - 近 7 天注册趋势柱状图（单系列 primary §1.7）
 *  - 角色分布环形饼图（多系列 §1.7 疏色序）
 *  - 热门课程榜（契约缺口占位卡，禁 MOCK）
 *  - RBAC：非 admin 由 (admin)/layout.tsx 的 AdminGuard 拦截（manager/teacher/student 重定向用户端）
 */
"use client";

import { MetricCards } from "@/components/admin/MetricCards";
import { RankFallback } from "@/components/admin/RankFallback";
import { RegisterTrendChart } from "@/components/admin/RegisterTrendChart";
import { RoleDonutChart } from "@/components/admin/RoleDonutChart";

export default function AdminDashboardPage() {
  return (
    <div className="mx-auto w-full max-w-7xl space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-border pb-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Admin Console
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-foreground">平台运营总览</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            用户规模、活跃、增长与角色分布一览。
          </p>
        </div>
        <code className="rounded bg-muted px-2 py-1 font-mono text-xs text-secondary-foreground">
          GET /api/admin/users/dashboard/metrics
        </code>
      </div>

      <MetricCards />

      <div className="grid gap-4 lg:grid-cols-2">
        <RegisterTrendChart />
        <RoleDonutChart />
      </div>

      <RankFallback />
    </div>
  );
}
