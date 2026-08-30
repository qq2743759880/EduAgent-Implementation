/**
 * CourseMindmapView — 课程详情页「思维导图」Tab
 * 数据来源：P4 /api/mindmap/course/{seriesId}（ECharts Graph 数据形态 nodes/links/categories）
 * 兜底：空态 + Loading Skeleton
 */
"use client";

import * as echarts from "echarts/core";
import { useEffect, useMemo, useRef } from "react";

import {
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  type TooltipComponentOption,
  type LegendComponentOption,
  type TitleComponentOption,
} from "echarts/components";
import { GraphChart, type GraphSeriesOption } from "echarts/charts";
import { CanvasRenderer } from "echarts/renderers";
import { UniversalTransition } from "echarts/features";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CHART_COLORS } from "@/lib/chart-palette";
import { AlertCircle, Loader2 } from "lucide-react";
import type { MindMapResponse } from "@/lib/api/curriculum";
import { cn } from "@/lib/utils";

echarts.use([
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  GraphChart,
  CanvasRenderer,
  UniversalTransition,
]);

export type MindmapLoadState =
  | { status: "loading" }
  | { status: "ready"; data: MindMapResponse }
  | { status: "empty" }
  | { status: "error"; message: string };

export function CourseMindmapView({ state }: { state: MindmapLoadState }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, undefined, { renderer: "canvas" });
    chartRef.current = chart;
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  const option: ComposeOptionSafe = useMemo(() => {
    if (state.status !== "ready" || !state.data.nodes?.length) {
      return undefined as unknown as ComposeOptionSafe;
    }
    const d = state.data;
    return {
      title: {
        text: d.title ?? "课程知识图谱",
        left: "center",
        top: 8,
        textStyle: { fontSize: 14, fontWeight: 600, color: CHART_COLORS.primaryStrong },
      },
      tooltip: {
        trigger: "item",
        formatter: (p: { dataType?: string; data?: Record<string, unknown> }) => {
          if (p.dataType === "edge") {
            const rel = (p.data?.relation as string | undefined) ?? "";
            const relLabel =
              RELATION_LABELS[rel as keyof typeof RELATION_LABELS] ??
              rel ??
              "关联";
            return `<div class="text-xs"><b>${String(p.data?.source ?? "")}</b> → <b>${String(p.data?.target ?? "")}</b><br/>关系：${relLabel}</div>`;
          }
          const nd = (p.data ?? {}) as unknown as MindMapResponse["nodes"][number];
          const statusText =
            nd.status === "mastered"
              ? "已掌握"
              : nd.status === "learning"
                ? "学习中"
                : nd.status === "blocked"
                  ? "受阻"
                  : "未开始";
          const catLabel =
            d.categories?.[nd.category ?? -1]?.name ?? "知识点";
          return `<div class="text-xs"><b>${nd.name}</b><br/>类型：${catLabel}<br/>状态：${statusText}</div>`;
        },
      },
      legend: d.legend?.length
        ? { data: d.legend, bottom: 8, type: "scroll" }
        : undefined,
      animationDuration: 500,
      series: [
        {
          type: "graph",
          layout: "force",
          roam: true,
          draggable: true,
          label: {
            show: true,
            position: "right",
            fontSize: 11,
            formatter: "{b}",
          },
          force: {
            repulsion: 220,
            edgeLength: [60, 140],
            gravity: 0.08,
          },
          categories: d.categories?.length
            ? d.categories.map((c) => ({
                name: c.name,
                itemStyle: c.itemStyle ?? undefined,
              }))
            : undefined,
          data: d.nodes.map((n) => ({
            id: n.id,
            name: n.name,
            category: n.category,
            value: n.value,
            symbolSize: n.symbolSize ?? clampSymbolSize(n.value ?? 20),
            itemStyle: {
              color: statusColor(n.status),
            },
            status: n.status,
          })),
          links: d.links.map((l) => ({
            source: l.source,
            target: l.target,
            relation: l.relation,
            lineStyle: l.lineStyle ?? {
              // 无后端样式时的语义兜底：PREREQUISITE 边保留 amber 语义（chartPalette.warning）；普通边 muted
              color: l.relation === "PREREQUISITE" ? CHART_COLORS.warning : CHART_COLORS.muted,
              type: l.relation === "PREREQUISITE" ? "dashed" : "solid",
              curveness: 0.08,
            },
          })),
          lineStyle: {
            opacity: 0.85,
            width: 1.4,
          },
          emphasis: {
            focus: "adjacency",
            lineStyle: { width: 3 },
          },
        },
      ],
    } as unknown as ComposeOptionSafe;
  }, [state]);

  useEffect(() => {
    if (!chartRef.current) return;
    if (!option) {
      chartRef.current.clear();
      return;
    }
    chartRef.current.setOption(option, true);
  }, [option]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">知识图谱</CardTitle>
        <CardDescription>
          可视化知识点 → 模块 → 先修链关系。拖拽可拖动节点，滚轮可缩放。
        </CardDescription>
      </CardHeader>
      <CardContent className={cn("relative min-h-[420px] w-full", "rounded-xl border border-border bg-muted/40 p-3")}>
        <div ref={ref} className="h-[440px] w-full" />

        {state.status === "loading" && (
          <Overlay>
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
            <span className="text-sm text-muted-foreground">正在加载图谱…</span>
          </Overlay>
        )}
        {state.status === "empty" && (
          <Overlay>
            <AlertCircle className="h-6 w-6 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">暂无该课程的图谱数据</span>
          </Overlay>
        )}
        {state.status === "error" && (
          <Overlay>
            <AlertCircle className="h-6 w-6 text-destructive" />
            <span className="max-w-[90%] truncate text-sm text-destructive">
              {state.message || "加载失败"}
            </span>
          </Overlay>
        )}
      </CardContent>
    </Card>
  );
}

function Overlay({ children }: { children: React.ReactNode }) {
  return (
    <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-2 rounded-xl bg-card/60 backdrop-blur-[2px]">
      {children}
    </div>
  );
}

function statusColor(s?: string): string {
  switch (s) {
    case "mastered":
      return CHART_COLORS.success;
    case "learning":
      return CHART_COLORS.primary;
    case "not_started":
      return CHART_COLORS.chartNeutral[2];
    default:
      return CHART_COLORS.primary;
  }
}

/** 关系类型 → 中文标签（tooltip 展示） */
const RELATION_LABELS = {
  CONTAINS: "包含",
  PREREQUISITE: "先修",
  RELATED_TO: "相关",
  TESTS: "考核",
} as const;

function clampSymbolSize(v: number): number {
  return Math.max(16, Math.min(64, Number(v) || 20));
}

type ComposeOptionSafe = echarts.ComposeOption<
  | TooltipComponentOption
  | LegendComponentOption
  | TitleComponentOption
  | GraphSeriesOption
>;
