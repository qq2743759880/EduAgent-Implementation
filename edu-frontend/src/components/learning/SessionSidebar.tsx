/**
 * SessionSidebar — 播放页右侧 sticky 侧栏
 * 含：
 *   1) 本课要点（要点 bullet — 若 session metadata 没给，直接显示固定 5 条通用 bullet）
 *   2) 迷你知识图谱（P4 /api/mindmap/me/{seriesId}）— 280x240 ECharts 图
 *   3) 课程学习进度快览（视频/作业/考试/总览）
 *   4) 错题本 / 单词本 两个 CTA 按钮（跳 /practice/wrong-book 和 /practice/vocab）
 */
"use client";

import Link from "next/link";
import * as echarts from "echarts/core";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef } from "react";
import {
  BookMarked,
  BookOpenCheck,
  CircleHelp,
  ListChecks,
  Map,
  Sparkles,
  Users,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { CHART_COLORS } from "@/lib/chart-palette";
import {
  GraphChart,
  type GraphSeriesOption,
} from "echarts/charts";
import {
  TooltipComponent,
  type TooltipComponentOption,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import {
  getMyCourseMindmap,
  type CourseProgressOut,
  type SessionProgressOut,
} from "@/lib/api/learning";
import { type MindMapResponse } from "@/lib/api/curriculum";
import { cn } from "@/lib/utils";

echarts.use([TooltipComponent, GraphChart, CanvasRenderer]);

export interface SessionSidebarProps {
  seriesId: number;
  sessionId?: number;
  sessionTitle?: string | null;
  subjectCode?: string | null;
  /** 要点列表（如果外部能提供 session metadata 就传进来，否则给通用兜底） */
  keyPoints?: string[];
  /** 课程整体进度（外部可传，也可内部不传直接展示本地进度） */
  courseProgress?: Pick<
    CourseProgressOut,
    "overall_ratio" | "video_watch_ratio" | "homework_done_ratio" | "exam_done_ratio"
  >;
  /** 当前课次实时进度（由 VideoPlayer 回调驱动） */
  liveSessionWatch?: { ratio: number; syncedRatio?: number | null } | null;
}

export function SessionSidebar({
  seriesId,
  sessionTitle,
  subjectCode,
  keyPoints,
  courseProgress,
  liveSessionWatch,
}: SessionSidebarProps) {
  const mindQ = useQuery({
    queryKey: ["my_mindmap", seriesId] as const,
    async queryFn(): Promise<MindMapResponse | null> {
      return getMyCourseMindmap(seriesId);
    },
    staleTime: 120_000,
  });

  const overall = pct(courseProgress?.overall_ratio);
  const video = pct(courseProgress?.video_watch_ratio);
  const hw = pct(courseProgress?.homework_done_ratio);
  const exam = pct(courseProgress?.exam_done_ratio);

  const points = keyPoints?.length
    ? keyPoints
    : fallbackKeyPoints(sessionTitle, subjectCode);

  return (
    <div className="space-y-4">
      {/* 要点卡 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <ListChecks className="h-4 w-4 text-primary" />
            本课要点
          </CardTitle>
          <CardDescription>
            本节覆盖的重点概念，学完后做习题巩固。
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          <ul className="space-y-2.5 text-sm">
            {points.map((t, i) => (
              <li key={i} className="flex items-start gap-2 leading-6">
            <span className="mt-1 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-primary/10 text-4xs font-bold text-primary">
              {String(i + 1).padStart(2, "0")}
            </span>
                <span className="min-w-0">{t}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      {/* 迷你导图卡 */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-base">
              <Map className="h-4 w-4 text-primary" />
              我的知识图谱
            </CardTitle>
            <Badge variant="secondary" className="text-4xs">
              P4 mindmap/me
            </Badge>
          </div>
          <CardDescription>绿色=已掌握；蓝色=学习中；灰色=未开始。</CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          <MiniMindmap seriesId={seriesId} data={mindQ.data} loading={mindQ.isFetching} error={mindQ.isError} />
        </CardContent>
      </Card>

      {/* 进度快览 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <BookOpenCheck className="h-4 w-4 text-primary" />
            学习进度快览
          </CardTitle>
          <CardDescription>
            实时观看百分比会随 P3 打点同步更新
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 pt-0">
          <ProgressItem label="本课已观看" value={pct(liveSessionWatch?.ratio)} sync={pctNullable(liveSessionWatch?.syncedRatio)} />
          <Separator />
          <ProgressItem label="总进度" value={overall} />
          <ProgressItem label="视频观看" value={video} />
          <ProgressItem label="作业完成" value={hw} />
          <ProgressItem label="考试完成" value={exam} />
        </CardContent>
      </Card>

      {/* 复习中心 CTA（fe-task07：图标三色 → 主色；错题本=纠错语义保留 destructive 于图标） */}
      <div className="grid grid-cols-2 gap-2">
        <Button asChild variant="outline" className="h-auto flex-col !py-3 gap-1">
          <Link href="/practice/wrong-book">
            <CircleHelp className="h-5 w-5 text-destructive" />
            <div className="text-sm font-semibold">错题本</div>
            <div className="text-3xs text-muted-foreground">重做你的薄弱题</div>
          </Link>
        </Button>
        <Button asChild variant="outline" className="h-auto flex-col !py-3 gap-1">
          <Link href="/practice/vocab">
            <BookMarked className="h-5 w-5 text-primary" />
            <div className="text-sm font-semibold">单词本</div>
            <div className="text-3xs text-muted-foreground">今日单词计划</div>
          </Link>
        </Button>
        <Button asChild variant="outline" className="h-auto flex-col !py-3 gap-1 col-span-2">
          <Link href="/dashboard">
            <Sparkles className="h-5 w-5 text-primary" />
            <span>去我的仪表盘查看总览</span>
          </Link>
        </Button>
      </div>
    </div>
  );
}

/* ---------- 迷你导图（内置 ECharts） ---------- */

type MiniState =
  | { status: "loading" }
  | { status: "empty" }
  | { status: "error" }
  | { status: "ready"; data: MindMapResponse };

function MiniMindmap({
  seriesId,
  data,
  loading,
  error,
}: {
  seriesId: number;
  data: MindMapResponse | null | undefined;
  loading: boolean;
  error: boolean;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const state: MiniState = useMemo(() => {
    if (loading && !data) return { status: "loading" };
    if (error) return { status: "error" };
    if (!data || !Array.isArray(data.nodes) || !data.nodes.length) return { status: "empty" };
    return { status: "ready", data };
  }, [loading, error, data]);

  useEffect(() => {
    if (!ref.current) return;
    const c = echarts.init(ref.current, undefined, { renderer: "canvas" });
    chartRef.current = c;
    const resize = () => c.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      c.dispose();
      chartRef.current = null;
    };
  }, [seriesId]);

  useEffect(() => {
    const c = chartRef.current;
    if (!c) return;
    if (state.status !== "ready") {
      c.clear();
      return;
    }
    const d = state.data;
    c.setOption(
      {
        tooltip: { trigger: "item" },
        animationDuration: 450,
        series: [
          {
            type: "graph",
            layout: "force",
            roam: false,
            label: { show: true, fontSize: 10, position: "bottom", formatter: "{b}" },
            force: {
              repulsion: 180,
              edgeLength: [30, 80],
              gravity: 0.12,
            },
            categories: d.categories?.length
              ? d.categories.map((c) => ({ name: c.name }))
              : undefined,
            data: d.nodes.slice(0, 60).map((n) => ({
              id: n.id,
              name: n.name,
              category: n.category,
              symbolSize: Math.max(10, Math.min(30, n.symbolSize ?? 14)),
              itemStyle: {
                color:
                  n.status === "mastered"
                    ? CHART_COLORS.success
                    : n.status === "learning"
                      ? CHART_COLORS.primary
                      : CHART_COLORS.chartNeutral[2],
              },
            })),
            links: d.links.slice(0, 120).map((l) => ({
              source: l.source,
              target: l.target,
              lineStyle: l.lineStyle ?? { opacity: 0.7, color: CHART_COLORS.muted },
            })),
          } as GraphSeriesOption,
        ],
      } as echarts.ComposeOption<TooltipComponentOption | GraphSeriesOption>,
      true,
    );
  }, [state]);

  return (
    <div className="relative">
      <div
        ref={ref}
        className="w-full overflow-hidden rounded-xl border border-border bg-gradient-to-b from-muted/40 to-card"
        style={{ height: 240 }}
      />
      {state.status === "loading" && (
        <Overlay className="text-primary">
          <Sparkles className="h-5 w-5 animate-spin" />
          <span className="text-xs text-muted-foreground">加载上色中…</span>
        </Overlay>
      )}
      {state.status === "empty" && (
        <Overlay>
          <Users className="h-5 w-5 text-muted-foreground/70" />
          <span className="text-xs text-muted-foreground">暂无上色数据（先报名并开始学习）</span>
        </Overlay>
      )}
      {state.status === "error" && (
        <Overlay>
          <CircleHelp className="h-5 w-5 text-destructive" />
          <span className="text-xs text-destructive">导图加载失败</span>
        </Overlay>
      )}
    </div>
  );
}

function Overlay({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-1.5 rounded-xl bg-card/70 backdrop-blur-[1px]",
        className,
      )}
    >
      {children}
    </div>
  );
}

/* ---------- 小工具 ---------- */

function ProgressItem({
  label,
  value,
  sync,
}: {
  label: string;
  value: number;
  sync?: number | null;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <div className="flex items-center gap-2">
          {typeof sync === "number" && sync !== value ? (
            // fe-task07：同步状态 = 进行中/强调 → text-primary
            <span className="text-4xs text-primary">已同步 {(sync * 100).toFixed(0)}%</span>
          ) : null}
          <span className="font-semibold tabular-nums text-foreground">
            {(value * 100).toFixed(0)}%
          </span>
        </div>
      </div>
      <Progress value={Math.min(100, value * 100)} />
    </div>
  );
}

function pct(v?: number | null): number {
  if (typeof v !== "number" || !Number.isFinite(v)) return 0;
  return Math.max(0, Math.min(1, v));
}
function pctNullable(v?: number | null): number | null {
  if (typeof v !== "number" || !Number.isFinite(v)) return null;
  return Math.max(0, Math.min(1, v));
}

function fallbackKeyPoints(sessionTitle?: string | null, subject?: string | null): string[] {
  const base: string[] = [
    `本节课围绕「${sessionTitle?.trim() || "本节主题"}」的核心概念建立结构化理解`,
    `完成视频观看后，做对应的随堂练习题 3–5 道`,
    `把本节课生词加入 AI 单词本，完成今日 SM-2 复习计划`,
    `做错的题自动加入错题本，可在复习中心再次重做巩固`,
    `完成后知识图谱对应节点上色，在仪表盘雷达图体现能力提升`,
  ];
  switch (subject) {
    case "english":
      return [
        base[0],
        "掌握 15+ 高频词的词性、短语搭配与常用句式",
        "跟读例句 ≥ 5 次，训练耳感和发音",
        base[2],
        base[3],
        base[4],
      ];
    case "programming":
      return [
        base[0],
        "理解语法结构 + 在 IDE 中实际运行一段示例代码",
        "完成 2–3 道随堂编程练习，观察输出与异常",
        base[3],
        "在思维导图中补充对应知识点的关系链",
        base[4],
      ];
    case "math":
      return [
        base[0],
        "弄清概念的定义与适用条件，避免常见错误类型",
        "手动推导 2 道经典例题的完整步骤",
        base[1],
        base[3],
        base[4],
      ];
    case "chinese":
      return [
        base[0],
        "理解文体结构（记叙文/议论文/文言文）与写作意图",
        "归纳文中出现的 8–12 个实词、通假字或特殊句式",
        base[2],
        base[3],
        base[4],
      ];
    case "physics":
      return [
        base[0],
        "明确物理量符号、单位与适用场景",
        "用公式推导 1–2 道典型题，关注符号正负与数量级",
        base[1],
        base[3],
        base[4],
      ];
    default:
      return base;
  }
}

// 让 SessionProgressOut 被 import 类型（避免未来 lint 报错）
export type __Session = SessionProgressOut;
