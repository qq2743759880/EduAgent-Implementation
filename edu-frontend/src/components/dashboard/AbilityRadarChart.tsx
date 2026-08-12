"use client";

import * as echarts from "echarts/core";
import type { ComposeOption } from "echarts/core";
import { useEffect, useMemo, useRef } from "react";

import {
  LegendComponent,
  RadarComponent,
  TitleComponent,
  TooltipComponent,
  type LegendComponentOption,
  type RadarComponentOption,
  type TitleComponentOption,
  type TooltipComponentOption,
} from "echarts/components";
import { RadarChart, type RadarSeriesOption } from "echarts/charts";
import { CanvasRenderer } from "echarts/renderers";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Target } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  SUBJECT_LABELS,
  SUBJECT_OPTIONS,
  type SubjectKey,
} from "@/lib/validators/profile-schemas";

echarts.use([
  RadarComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  RadarChart,
  CanvasRenderer,
]);

export interface AbilityRadarSeries {
  name: string;
  /** 必须与 SUBJECT_OPTIONS 顺序/长度一致：english / coding / math / chinese / physics */
  values: (SubjectKey | number) extends never ? never[] : number[];
  /** 主题色（默认：indigo6/emerald6） */
  color?: string;
  /** 填色不透明度 */
  opacity?: number;
}

interface AbilityRadarChartProps {
  title?: string;
  description?: string;
  /** 至少传 1 组；最多 2 组（"我 vs 全班平均"这种对比场景） */
  series: AbilityRadarSeries[];
  /** 各维度满分，默认 100 */
  max?: number;
  /** 雷达图高度，默认 340px */
  height?: number | string;
  className?: string;
  loading?: boolean;
}

type ECOption = ComposeOption<
  RadarComponentOption | TooltipComponentOption | LegendComponentOption | TitleComponentOption | RadarSeriesOption
>;

/** 把 SUBJECT_OPTIONS 顺序固定为雷达指标顺序；外部 values 必须同序 */
const INDICATOR_ORDER: SubjectKey[] = [...SUBJECT_OPTIONS] as SubjectKey[];

export function AbilityRadarChart({
  title = "学科能力雷达",
  description = "按 5 大学科维度评估当前能力水平（满分 100）。",
  series,
  max = 100,
  height = 340,
  className,
  loading = false,
}: AbilityRadarChartProps) {
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
    const indicators: RadarComponentOption["indicator"] = INDICATOR_ORDER.map((k) => ({
      name: SUBJECT_LABELS[k],
      max,
    }));
    const colors = series.map((s) => s.color || "#6366f1");
    return {
      animationDuration: 600,
      tooltip: {
        trigger: "item",
        valueFormatter: (v) =>
          Array.isArray(v)
            ? v
                .map((x, i) => `${SUBJECT_LABELS[INDICATOR_ORDER[i]!]} ${typeof x === "number" ? x : "—"}`)
                .join("，")
            : String(v),
      },
      legend: series.length > 1 ? { bottom: 0, icon: "roundRect", textStyle: { color: "#64748b", fontSize: 12 } } : undefined,
      radar: {
        indicator: indicators as NonNullable<RadarComponentOption["indicator"]>,
        center: ["50%", "52%"],
        radius: "62%",
        shape: "polygon",
        splitNumber: 4,
        axisName: {
          color: "#475569",
          fontSize: 12,
          fontWeight: 500,
        },
        splitLine: {
          lineStyle: { color: "#e2e8f0" },
        },
        splitArea: {
          areaStyle: { color: ["#f8fafc", "#ffffff", "#f8fafc", "#ffffff"] },
        },
        axisLine: { lineStyle: { color: "#cbd5e1" } },
      },
      series: [
        {
          type: "radar",
          emphasis: { focus: "self" },
          data: series.map((s, idx) => {
            const value = (s.values ?? []).slice(0, INDICATOR_ORDER.length);
            while (value.length < INDICATOR_ORDER.length) value.push(0);
            const color = colors[idx] || "#6366f1";
            const opacity = typeof s.opacity === "number" ? s.opacity : 0.22;
            return {
              name: s.name,
              value,
              symbol: "circle",
              symbolSize: 5,
              lineStyle: { width: 2, color },
              itemStyle: { color, borderWidth: 1, borderColor: "#fff" },
              areaStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 1, 1, [
                  { offset: 0, color },
                  { offset: 1, color },
                ]),
                opacity,
              },
            };
          }),
        } satisfies RadarSeriesOption,
      ],
    } satisfies ECOption;
  }, [series, max]);

  useEffect(() => {
    const c = chartRef.current;
    if (!c) return;
    c.setOption(option, true);
    if (loading) c.showLoading("default", { text: "加载中", textColor: "#10b981", maskColor: "rgba(255,255,255,0.7)" });
    else c.hideLoading();
  }, [option, loading]);

  return (
    <Card className={cn("border-slate-200/80 shadow-sm bg-white", className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <Target className="h-4 w-4 text-emerald-500" />
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

export default AbilityRadarChart;
