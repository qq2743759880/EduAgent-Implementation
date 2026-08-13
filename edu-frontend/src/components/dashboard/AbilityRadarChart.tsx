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
import { CHART_COLORS } from "@/lib/chart-palette";
import { RotateCw, Target } from "lucide-react";
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
  /** 覆盖层空态（series=[] 且非 loading/error 时由页面传入 true） */
  empty?: boolean;
  /** 空态文案 */
  emptyText?: string;
  /** 覆盖层错误态（query isError 时由页面传入 true） */
  error?: boolean;
  /** 错误态文案 */
  errorText?: string;
  /** 错误覆盖层重试按钮回调 */
  onRetry?: () => void;
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
  empty = false,
  emptyText = "学习后即可生成学科能力评估",
  error = false,
  errorText = "能力评估加载失败",
  onRetry,
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

  // a11y #5（1.1.1）：echarts canvas 无替代文本 → 容器 role="img" + aria-label 汇总数据摘要
  const chartAriaLabel = loading
    ? `${title}（加载中）`
    : error
      ? `${title}（加载失败）`
      : empty
        ? `${title}（暂无数据）`
        : `${title}：${series
            .map(
              (s) =>
                `${s.name} ${INDICATOR_ORDER.map((k, i) => `${SUBJECT_LABELS[k]} ${s.values?.[i] ?? 0}`).join(
                  "、",
                )}`,
            )
            .join("；")}`;

  const option: ECOption = useMemo(() => {
    const indicators: RadarComponentOption["indicator"] = INDICATOR_ORDER.map((k) => ({
      name: SUBJECT_LABELS[k],
      max,
    }));
    const colors = series.map((s) => s.color || CHART_COLORS.primary);
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
      legend: series.length > 1 ? { bottom: 0, icon: "roundRect", textStyle: { color: CHART_COLORS.mutedForeground, fontSize: 12 } } : undefined,
      radar: {
        indicator: indicators as NonNullable<RadarComponentOption["indicator"]>,
        center: ["50%", "52%"],
        radius: "62%",
        shape: "polygon",
        splitNumber: 4,
        axisName: {
          color: CHART_COLORS.axisName,
          fontSize: 12,
          fontWeight: 500,
        },
        splitLine: {
          lineStyle: { color: CHART_COLORS.border },
        },
        splitArea: {
          areaStyle: {
            color: [CHART_COLORS.splitAreaBg, CHART_COLORS.white, CHART_COLORS.splitAreaBg, CHART_COLORS.white],
          },
        },
        axisLine: { lineStyle: { color: CHART_COLORS.border } },
      },
      series: [
        {
          type: "radar",
          emphasis: { focus: "self" },
          data: series.map((s, idx) => {
            const value = (s.values ?? []).slice(0, INDICATOR_ORDER.length);
            while (value.length < INDICATOR_ORDER.length) value.push(0);
            const color = colors[idx] || CHART_COLORS.primary;
            const opacity = typeof s.opacity === "number" ? s.opacity : 0.22;
            return {
              name: s.name,
              value,
              symbol: "circle",
              symbolSize: 5,
              lineStyle: { width: 2, color },
              itemStyle: { color, borderWidth: 1, borderColor: CHART_COLORS.white },
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
    if (loading) c.showLoading("default", { text: "加载中", textColor: CHART_COLORS.success, maskColor: "rgba(255,255,255,0.7)" });
    else c.hideLoading();
  }, [option, loading]);

  return (
    <Card className={cn("border-border shadow-card bg-card", className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <Target className="h-4 w-4 text-primary" />
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
              <Target className="h-6 w-6 opacity-80" aria-hidden="true" />
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
              <Target className="h-6 w-6 text-muted-foreground/60" aria-hidden="true" />
              <p className="text-sm">{emptyText}</p>
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

export default AbilityRadarChart;
