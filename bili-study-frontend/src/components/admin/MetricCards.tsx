/**
 * MetricCards — 管理端仪表盘 6 指标卡（task55 重构，task03 基础）
 * 数据源：GET /api/admin/users/dashboard/metrics（user_admin 模块，与用户管理同源）
 *  - total_user_count / active_user_count_7d / role_breakdown / disabled_user_count /
 *    new_register_count_7d / avg_login_days_per_user_30d
 * 无 MOCK：数据全部来自真实 API，加载中骨架、失败错误态可重试。
 * task55：收编 arbitrary 小字号为语义 token（text-sm-table/text-3xs），KPI 图标改糖果色系
 *  （candy-playful 定调），角色分布色取自 ROLE_CHART_COLORS（§1.7 疏色序，多系列取色）。
 */
"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, CalendarDays, ShieldBan, UserPlus, Users } from "lucide-react";

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

  const roles = ["admin", "manager", "teacher", "student"] as const;
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="metric-cards">
      <MetricCard
        icon={<Users className="h-4 w-4" />}
        label="用户总数"
        value={String(data.total_user_count)}
        iconClass="bg-candy-purple/10 text-candy-purple"
      />
      <MetricCard
        icon={<Activity className="h-4 w-4" />}
        label="7d 活跃用户"
        value={String(data.active_user_count_7d)}
        iconClass="bg-candy-green/10 text-candy-green"
      />
      <RoleBreakdownCard breakdown={data.role_breakdown} roles={roles} />
      <MetricCard
        icon={<ShieldBan className="h-4 w-4" />}
        label="禁用账号"
        value={String(data.disabled_user_count)}
        iconClass="bg-candy-red/10 text-candy-red"
      />
      <MetricCard
        icon={<UserPlus className="h-4 w-4" />}
        label="7d 新增注册"
        value={String(data.new_register_count_7d)}
        iconClass="bg-candy-green/10 text-candy-green"
      />
      <MetricCard
        icon={<CalendarDays className="h-4 w-4" />}
        label="30d 人均登录（天）"
        value={data.avg_login_days_per_user_30d.toFixed(2)}
        iconClass="bg-candy-yellow/20 text-candy-purple"
      />
    </div>
  );
}

/**
 * 指标卡：图标糖果浅底 + 标签/数值。字号 token 化（sm-base 值、sm-table 标签）。
 * iconClass 由调用方传入糖果语义浅底（candy-purple/green/red/yellow），符合 candy-playful 定调。
 */
function MetricCard({
  icon,
  label,
  value,
  iconClass,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  iconClass: string;
}) {
  return (
    <Card size="sm" className="bg-white">
      <CardContent className="flex items-center gap-3">
        <span
          className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${iconClass}`}
        >
          {icon}
        </span>
        <div className="min-w-0">
          <div className="text-sm-table text-muted-foreground">{label}</div>
          <div className="text-2xl font-semibold text-foreground tabular-nums" data-testid={`metric-${label}`}>
            {value}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/** 角色分布色点 class 映射（§1.7 疏色序 / candy 系，与饼图同源视觉、无内联色）。 */
const ROLE_DOT_CLASSES: Record<string, string> = {
  admin: "bg-primary",
  manager: "bg-candy-red",
  teacher: "bg-candy-blue",
  student: "bg-candy-purple",
};

/** 角色分布卡：四个角色计数，色点取 ROLE_DOT_CLASSES（§1.7 疏色序，与饼图同源）。 */
function RoleBreakdownCard({
  breakdown,
  roles,
}: {
  breakdown: Record<string, number>;
  roles: readonly ("admin" | "manager" | "teacher" | "student")[];
}) {
  return (
    <Card size="sm" className="bg-white">
      <CardContent>
        <div className="flex items-center gap-3">
          <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-candy-blue/10 text-candy-blue">
            <CalendarDays className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <div className="text-sm-table text-muted-foreground">角色分布</div>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm font-semibold text-foreground">
              {roles.map((r) => (
                <span
                  key={r}
                  className="inline-flex items-center gap-1"
                  data-testid={`metric-role-${r}`}
                >
                  <span
                    className={`h-2 w-2 shrink-0 rounded-full ${ROLE_DOT_CLASSES[r]}`}
                    aria-hidden="true"
                  />
                  <span className="text-3xs font-normal text-muted-foreground">{userRoleLabel(r)}</span>
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