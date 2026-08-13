/**
 * MetricCards — 管理端仪表盘 6 指标卡（task03）
 * 数据源：GET /api/admin/users/dashboard/metrics（user_admin 模块，与用户管理同源）
 *  - total_user_count / active_user_count_7d / role_breakdown / disabled_user_count /
 *    new_register_count_7d / avg_login_days_per_user_30d
 * 无 MOCK：数据全部来自真实 API，加载中骨架、失败错误态可重试。
 */
"use client";

import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  CalendarDays,
  Clock3,
  ShieldBan,
  UserPlus,
  Users,
} from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { getDashboardMetrics, userRoleLabel, type DashboardMetrics } from "@/lib/api/admin/users";
import { ErrorState, LoadingState } from "@/components/admin/controls";

export function MetricCards() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["admin", "users", "metrics"] as const,
    queryFn: () => getDashboardMetrics(),
    staleTime: 60_000,
  });

  if (isLoading) return <LoadingState label="加载运营指标…" />;
  if (isError || !data) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : "运营指标加载失败"}
        onRetry={() => refetch()}
      />
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="metric-cards">
      <MetricCard
        icon={<Users className="h-4 w-4" />}
        label="用户总数"
        value={String(data.total_user_count)}
        tone="indigo"
      />
      <MetricCard
        icon={<Activity className="h-4 w-4" />}
        label="7d 活跃用户"
        value={String(data.active_user_count_7d)}
        tone="emerald"
      />
      <RoleBreakdownCard breakdown={data.role_breakdown} />
      <MetricCard
        icon={<ShieldBan className="h-4 w-4" />}
        label="禁用账号"
        value={String(data.disabled_user_count)}
        tone="rose"
      />
      <MetricCard
        icon={<UserPlus className="h-4 w-4" />}
        label="7d 新增注册"
        value={String(data.new_register_count_7d)}
        tone="emerald"
      />
      <MetricCard
        icon={<Clock3 className="h-4 w-4" />}
        label="30d 人均登录（天）"
        value={data.avg_login_days_per_user_30d.toFixed(2)}
        tone="indigo"
      />
    </div>
  );
}

// D-01/02/03 收敛：仅 indigo（主色）+ emerald/rose（状态语义：7d 活跃=成功、禁用=危险）
// sky/violet/amber 为基准外色已删除；角色分布卡归位 indigo（见 RoleBreakdownCard）
const TONES = {
  indigo: "bg-indigo-50 text-indigo-600",
  emerald: "bg-emerald-50 text-emerald-600",
  rose: "bg-rose-50 text-rose-600",
} as const;

function MetricCard({
  icon,
  label,
  value,
  tone,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  tone: keyof typeof TONES;
}) {
  return (
    <Card size="sm" className="bg-white">
      <CardContent className="flex items-center gap-3">
        <span className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${TONES[tone]}`}>
          {icon}
        </span>
        <div className="min-w-0">
          <div className="text-[13px] text-slate-500">{label}</div>
          <div className="text-xl font-semibold text-slate-900" data-testid={`metric-${label}`}>
            {value}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function RoleBreakdownCard({ breakdown }: { breakdown: Record<string, number> }) {
  const roles = ["admin", "manager", "teacher", "student"];
  return (
    <Card size="sm" className="bg-white">
      <CardContent>
        <div className="flex items-center gap-3">
          <span className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${TONES.indigo}`}>
            <CalendarDays className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <div className="text-[13px] text-slate-500">角色分布</div>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm font-semibold text-slate-900">
              {roles.map((r) => (
                <span key={r} className="inline-flex items-center gap-1" data-testid={`metric-role-${r}`}>
                  <span className="text-[11px] font-normal text-slate-600">{userRoleLabel(r)}</span>
                  {breakdown[r] ?? 0}
                </span>
              ))}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/** 供页面复用：metrics 数据源类型再导出 */
export type { DashboardMetrics };
