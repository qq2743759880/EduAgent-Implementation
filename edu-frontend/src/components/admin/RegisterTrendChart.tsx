/**
 * RegisterTrendChart — 管理端仪表盘：近 7 天注册趋势折线图（P2-B）
 * 数据源：GET /api/admin/users/dashboard/metrics 的 register_trend_7d
 *  - 每次跳转刷新一次（useQuery 缓存），加载失败可重试
 */
"use client";

import * as echarts from "echarts/core";
import { useEffect, useMemo, useRef } from "react";

import {
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
} from "echarts/components";
import { BarChart } from "echarts/charts";
import { UniversalTransition } from "echarts/features";
import { CanvasRenderer } from "echarts/renderers";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CHART_COLORS, primaryGradient } from "@/lib/chart-palette";
import { useQuery } from "@tanstack/react-query";
import { getDashboardMetrics } from "@/lib/api/admin/users";
import { ErrorState, LoadingState } from "@/components/admin/controls";

echarts.use([
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  BarChart,
  CanvasRenderer,
  UniversalTransition,
]);

export function RegisterTrendChart() {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["admin", "users", "metrics"] as const,
    queryFn: () => getDashboardMetrics(),
    staleTime: 60_000,
  });

  const trend = useMemo(() => data?.register_trend_7d ?? [], [data]);

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
    if (!chart) return;
    const dates = trend.map((p) => p.date.slice(5)); // MM-DD
    const counts = trend.map((p) => p.count);
    chart.setOption({
      animationDuration: 600,
      grid: { left: 40, right: 24, top: 40, bottom: 32, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        valueFormatter: (v: unknown) => (typeof v === "number" ? `${v} 人` : "—"),
      },
      xAxis: {
        type: "category",
        data: dates,
        axisLine: { lineStyle: { color: CHART_COLORS.border } },
        axisLabel: { color: CHART_COLORS.muted, fontSize: 11 },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        axisLine: { show: false },
        axisLabel: { color: CHART_COLORS.muted, fontSize: 11 },
        splitLine: { lineStyle: { color: CHART_COLORS.grid, type: "dashed" } },
      },
      series: [
        {
          type: "bar",
          data: counts,
          name: "新增注册",
          barMaxWidth: 28,
          itemStyle: { color: CHART_COLORS.primary, borderRadius: [4, 4, 0, 0] },
          areaStyle: { opacity: 0, ...primaryGradient(0.28, 0.02) },
        },
      ],
    });
  }, [trend]);

  if (isLoading) return <LoadingState label="加载注册趋势…" />;
  if (isError || !data) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : "注册趋势加载失败"}
        onRetry={() => refetch()}
      />
    );
  }

  return (
    <Card className="bg-white">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">近 7 天注册趋势</CardTitle>
        <CardDescription>每日新增注册用户数</CardDescription>
      </CardHeader>
      <CardContent>
        <div
          ref={ref}
          role="img"
          aria-label={`近 7 天注册趋势：${trend.map((p) => `${p.date} ${p.count} 人`).join("，")}`}
          className="h-55 w-full"
        />
      </CardContent>
    </Card>
  );
}
