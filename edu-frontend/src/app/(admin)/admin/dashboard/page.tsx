/**
 * 管理端 · 仪表盘（/admin/dashboard，task03）
 *  - 6 项运营指标卡：GET /api/admin/users/dashboard/metrics
 *    （total_user_count / active_user_count_7d / role_breakdown / disabled_user_count /
 *      new_register_count_7d / avg_login_days_per_user_30d）
 *  - task02 占位壳已替换为真实数据组件 MetricCards（无 MOCK）
 */
"use client";

import { MetricCards } from "@/components/admin/MetricCards";

export default function AdminDashboardPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">仪表盘</h1>
        <p className="text-sm text-slate-500">
          平台运营总览 · 数据来自
          <code className="ml-1.5 rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-700">
            GET /api/admin/users/dashboard/metrics
          </code>
        </p>
      </div>

      <MetricCards />
    </div>
  );
}
