"use client";

import * as echarts from "echarts/core";
import type { ComposeOption } from "echarts/core";
import { useEffect, useMemo, useRef } from "react";

import {
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
  type GridComponentOption,
  type LegendComponentOption,
  type TitleComponentOption,
  type TooltipComponentOption,
} from "echarts/components";
import { LineChart, type LineSeriesOption } from "echarts/charts";
import { UniversalTransition } from "echarts/features";
import { CanvasRenderer } from "echarts/renderers";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { CHART_COLORS, primaryGradient } from "@/lib/chart-palette";
import { RotateCw, TrendingUp } from "lucide-react";

echarts.use([
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  LineChart,
  CanvasRenderer,
  UniversalTransition,
]);

export interface ProgressTrendPoint {
  /** MM/DD 或 YYYY-MM-DD 均可；会直接作为 x 轴标签 */
  dateLabel: string;
  minutes: number;
  /** 额外叠加线：练习时长（分钟），可不传 */
  practiceMinutes?: number;
}

interface ProgressTrendChartProps {
  title?: string;
  description?: string;
  data: ProgressTrendPoint[];
  /** 图表高度，默认 320px */
  height?: number | string;
  className?: string;
  /** 当 ECharts 没初始化时显示 loading */
  loading?: boolean;
  /** 覆盖层空态（data=[] 时由页面传入 true；默认 false） */
  empty?: boolean;
  /** 空态文案 */
  emptyText?: string;
  /** 覆盖层错误态（query isError 时由页面传入 true；默认 false） */
  error?: boolean;
  /** 错误态文案 */
  errorText?: string;
  /** 错误覆盖层重试按钮回调 */
  onRetry?: () => void;
}

type ECOption = ComposeOption<
  GridComponentOption | TooltipComponentOption | LegendComponentOption | TitleComponentOption | LineSeriesOption
>;

export function ProgressTrendChart({
  title = "近 14 天学习时长",
  description = "统计每天学习视频 + 练习时长，单位分钟。",
  data,
  height = 320,
  className,
  loading = false,
  empty = false,
  emptyText = "开始学习后，这里会记录你每天的学习时长",
  error = false,
  errorText = "学习数据加载失败",
  onRetry,
}: ProgressTrendChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (typeof window === "undefined" || !containerRef.current) return;
    chartRef.current = echarts.init(containerRef.current, undefined, { renderer: "canvas" });
    const handleResize = () => chartRef.current?.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  // a11y #5（1.1.1）：echarts canvas 无替代文本 → 容器 role="img" + aria-label 汇总数据摘要
  const chartAriaLabel = loading
    ? `${title}（加载中）`
    : error
      ? `${title}（加载失败）`
      : empty
        ? `${title}（暂无数据）`
        : `${title}：每日学习时长（分钟）${data.map((p) => `${p.dateLabel} ${p.minutes}`).join("，")}`;

  const option: ECOption = useMemo(() => {
    const categories = data.map((p) => p.dateLabel);
    const mins = data.map((p) => p.minutes);
    const practice = data.map((p) => (typeof p.practiceMinutes === "number" ? p.practiceMinutes : null));
    const hasPractice = practice.some((v) => typeof v === "number");
    return {
      animationDuration: 600,
      grid: { left: 40, right: 24, top: 40, bottom: 36, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "line" },
        valueFormatter: (v) => (typeof v === "number" ? `${v} 分钟` : "—"),
      },
      legend: hasPractice
        ? {
            top: 0,
            right: 4,
            icon: "roundRect",
            textStyle: { color: CHART_COLORS.mutedForeground, fontSize: 12 },
          }
        : undefined,
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: categories,
        axisLine: { lineStyle: { color: CHART_COLORS.border } },
        axisLabel: { color: CHART_COLORS.muted, fontSize: 11 },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        axisLine: { show: false },
        axisLabel: { color: CHART_COLORS.muted, fontSize: 11, formatter: "{value}" },
        splitLine: { lineStyle: { color: CHART_COLORS.grid, type: "dashed" } },
        name: "分钟",
        nameTextStyle: { color: CHART_COLORS.muted, fontSize: 11, padding: [0, 0, 0, -20] },
      },
      series: [
        {
          name: "学习时长",
          type: "line",
          smooth: true,
          showSymbol: false,
          sampling: "lttb",
          lineStyle: { width: 3 },
          itemStyle: { color: CHART_COLORS.primary },
          areaStyle: {
            opacity: 0.8,
            color: primaryGradient(),
          },
          emphasis: { focus: "series" },
          data: mins,
        },
        ...(hasPractice
          ? [
              {
                name: "练习时长",
                type: "line",
                smooth: true,
                showSymbol: false,
                lineStyle: { width: 2, type: "dashed" },
                itemStyle: { color: CHART_COLORS.chartNeutral[1] },
                data: practice,
              } as LineSeriesOption,
            ]
          : []),
      ],
    } satisfies ECOption;
  }, [data]);

  useEffect(() => {
    const c = chartRef.current;
    if (!c) return;
    c.setOption(option, true);
    if (loading) c.showLoading("default", { text: "加载中", textColor: CHART_COLORS.primary, maskColor: "rgba(255,255,255,0.7)" });
    else c.hideLoading();
  }, [option, loading]);

  return (
    <Card className={cn("border-border shadow-card bg-card", className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-primary" />
              {title}
            </CardTitle>
            <CardDescription className="text-sm text-muted-foreground pt-1">{description}</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="relative" style={{ height }}>
          <div
            ref={containerRef}
            role="img"
            aria-label={chartAriaLabel}
            style={{ width: "100%", height }}
          />
          {error ? (
            <div
              role="alert"
              className="absolute inset-0 flex flex-col items-center justify-center gap-2 rounded-xl border border-destructive/30 bg-destructive/10 text-destructive-foreground px-4 text-center"
            >
              <TrendingUp className="h-6 w-6 opacity-80" aria-hidden="true" />
              <p className="text-sm font-medium">{errorText}</p>
              {onRetry ? (
                <button
                  type="button"
                  onClick={onRetry}
                  className="inline-flex items-center gap-1.5 h-8 px-3 rounded-full bg-primary text-primary-foreground text-xs font-medium hover:opacity-90"
                >
                  <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
                  重试
                </button>
              ) : null}
            </div>
          ) : empty && !loading ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed border-border bg-muted/40 text-muted-foreground px-4 text-center">
              <TrendingUp className="h-6 w-6 text-muted-foreground/60" aria-hidden="true" />
              <p className="text-sm">{emptyText}</p>
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

export default ProgressTrendChart;
