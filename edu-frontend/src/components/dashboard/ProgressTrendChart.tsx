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
import { TrendingUp } from "lucide-react";

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
            textStyle: { color: "#64748b", fontSize: 12 },
          }
        : undefined,
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: categories,
        axisLine: { lineStyle: { color: "#e2e8f0" } },
        axisLabel: { color: "#94a3b8", fontSize: 11 },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        axisLine: { show: false },
        axisLabel: { color: "#94a3b8", fontSize: 11, formatter: "{value}" },
        splitLine: { lineStyle: { color: "#f1f5f9", type: "dashed" } },
        name: "分钟",
        nameTextStyle: { color: "#94a3b8", fontSize: 11, padding: [0, 0, 0, -20] },
      },
      series: [
        {
          name: "学习时长",
          type: "line",
          smooth: true,
          showSymbol: false,
          sampling: "lttb",
          lineStyle: { width: 3 },
          itemStyle: { color: "#6366f1" },
          areaStyle: {
            opacity: 0.8,
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "rgba(99, 102, 241, 0.32)" },
              { offset: 1, color: "rgba(99, 102, 241, 0.02)" },
            ]),
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
                itemStyle: { color: "#0ea5e9" },
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
    if (loading) c.showLoading("default", { text: "加载中", textColor: "#6366f1", maskColor: "rgba(255,255,255,0.7)" });
    else c.hideLoading();
  }, [option, loading]);

  return (
    <Card className={cn("border-slate-200/80 shadow-sm bg-white", className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-indigo-500" />
              {title}
            </CardTitle>
            <CardDescription className="text-sm text-slate-500 pt-1">{description}</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <div ref={containerRef} style={{ width: "100%", height }} />
      </CardContent>
    </Card>
  );
}

export default ProgressTrendChart;
