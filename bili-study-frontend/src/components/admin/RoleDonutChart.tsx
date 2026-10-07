/**
 * RoleDonutChart — 管理端仪表盘：角色分布环形饼图（task55）
 * 数据源：GET /api/admin/users/dashboard/metrics 的 role_breakdown{admin,manager,teacher,student}
 *  - §1.7 多系列取色：ROLE_CHART_COLORS 疏色序（admin indigo-600 / manager rose-500 /
 *    teacher sky-500 / student violet-500，饼图禁用相邻同系）
 *  - 加载失败可重试；无 MOCK（role_breakdown 全部真实聚合）
 */
"use client";

import * as echarts from "echarts/core";
import { useEffect, useMemo, useRef } from "react";

import { PieChart } from "echarts/charts";
import {
  GraphicComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState, LoadingState } from "@/components/admin/controls";
import { CHART_COLORS, ROLE_CHART_COLORS } from "@/lib/chart-palette";
import { getDashboardMetrics } from "@/lib/api/admin/users";
import { userRoleLabel } from "@/lib/api/admin/users";
import { useQuery } from "@tanstack/react-query";

echarts.use([
  PieChart,
  TooltipComponent,
  TitleComponent,
  LegendComponent,
  GraphicComponent,
  CanvasRenderer,
]);

const ROLE_ORDER = ["admin", "manager", "teacher", "student"] as const;

// 图例色点（语义 token，禁内联 hex）：与 chart-palette §1.7 疏色序一致
const ROLE_DOT_CLASSES: Record<string, string> = {
  admin: "bg-primary",
  manager: "bg-candy-red",
  teacher: "bg-candy-blue",
  student: "bg-candy-purple",
};

const fmt = (n: number) => n.toLocaleString();

export function RoleDonutChart() {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["admin", "users", "metrics"] as const,
    queryFn: () => getDashboardMetrics(),
    staleTime: 60_000,
  });

  const series = useMemo(() => {
    const breakdown = data?.role_breakdown ?? {};
    return ROLE_ORDER.map((r) => ({
      key: r,
      name: userRoleLabel(r),
      value: breakdown[r] ?? 0,
      itemStyle: { color: ROLE_CHART_COLORS[r] },
    })).filter((d) => d.value > 0);
  }, [data]);

  useEffect(() => {
    if (!ref.current) return;
    chartRef.current ??= echarts.init(ref.current);
    return () => {
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || series.length === 0) return;
    chart.setOption({
      animationDuration: 600,
      tooltip: {
        trigger: "item",
        formatter: (params: { name: string; value: number }) =>
          `${params.name}：${params.value} 人`,
      },
      series: [
        {
          type: "pie",
          radius: ["52%", "76%"],
          center: ["50%", "48%"],
          avoidLabelOverlap: true,
          itemStyle: { borderColor: CHART_COLORS.white, borderWidth: 2 },
          label: { show: false },
          emphasis: {
            label: { show: false },
            scaleSize: 6,
          },
          data: series,
        },
      ],
    });
  }, [series]);

  // 环形中心摘要（statistic 文本）渲染在容器绝对定位层（不依赖 echarts graphic）
  const total = useMemo(() => series.reduce((s, d) => s + d.value, 0), [series]);
  const top = useMemo(() => [...series].sort((a, b) => b.value - a.value)[0], [series]);

  if (isLoading) return <LoadingState label="加载角色分布…" />;
  if (isError || !data) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : "角色分布加载失败"}
        onRetry={() => refetch()}
      />
    );
  }

  return (
    <Card className="bg-white">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">角色分布</CardTitle>
        <CardDescription>多系列按 §1.7 疏色序取色</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="relative">
          <div
            ref={ref}
            role="img"
            aria-label={`角色分布：${series.map((d) => `${d.name} ${d.value}`).join("，")}`}
            className="h-55 w-full"
          />
          <div className="pointer-events-none absolute inset-x-0 top-5 flex flex-col items-center gap-0.5 text-center">
            <span className="text-2xl font-bold text-foreground tabular-nums">{fmt(total)}</span>
            <span className="text-3xs text-muted-foreground">
              {top ? `${top.name}占比最高` : "暂无数据"}
            </span>
          </div>
        </div>
        <ul className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1.5" data-testid="role-dist-legend">
          {series.map((d) => (
            <li key={d.key} className="flex items-center gap-1.5 text-sm">
              <span
                className={`h-2.5 w-2.5 shrink-0 rounded-full ${ROLE_DOT_CLASSES[d.key]}`}
                aria-hidden="true"
              />
              <span className="text-xs text-muted-foreground">{d.name}</span>
              <span className="ml-auto whitespace-nowrap text-sm font-semibold text-foreground tabular-nums">
                {fmt(d.value)}
                <span className="ml-0.5 text-3xs font-normal text-muted-foreground">
                  {(total > 0 ? (d.value / total) * 100 : 0).toFixed(1)}%
                </span>
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}