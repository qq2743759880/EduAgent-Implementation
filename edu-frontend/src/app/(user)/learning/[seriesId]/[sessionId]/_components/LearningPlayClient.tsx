/**
 * LearningPlayClient — 播放页客户端逻辑
 *   - 未登录 → 跳 /login?redirect=
 *   - seriesId/sessionId 非法 → 404 UI + 回我的课程
 *   - 同时查：
 *       a) P3 /api/progress/courses → 找到本系列学习进度（overall/video/hw/exam）
 *       b) 若 a) 无此系列：fallback 到 P4 curriculum getSeriesTree() 拿大纲
 *   - 根据 sessionId 找到：所属模块 title、本课 title、上下一课 sessionId，填入 VideoPlayer + SessionSidebar
 */
"use client";

import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowLeft,
  ArrowRight,
  ChevronRight,
  GraduationCap,
  Home,
  Loader2,
  RotateCcw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuthStore } from "@/lib/auth-client";
import { getSeriesTreeFlat, type SeriesTreeOut } from "@/lib/api/curriculum";
import {
  getMyCourses,
  type CourseProgressOut,
  type ModuleProgressOut,
  type SessionProgressOut,
} from "@/lib/api/learning";
import { VideoPlayer } from "@/components/learning/VideoPlayer";
import { InteractiveTabs } from "@/components/learning/InteractiveTabs";
import { SessionSidebar } from "@/components/learning/SessionSidebar";

export interface LearningPlayClientProps {
  seriesId: number;
  sessionId: number;
}

interface FlattenSession {
  sessionId: number;
  sessionTitle: string | null;
  moduleId: number;
  moduleTitle: string | null;
  index: number; // 1-based
  video_watch_ratio?: number | null;
  video_total_seconds?: number | null;
}

export default function LearningPlayClient({
  seriesId,
  sessionId,
}: LearningPlayClientProps) {
  const router = useRouter();
  const pathname = usePathname();
  const authed = useAuthStore((s) => s.isAuthenticated());

  const [liveProgress, setLiveProgress] = useState<{
    ratio: number;
    syncedRatio?: number | null;
  } | null>(null);

  /* 登录保护 */
  useEffect(() => {
    if (authed) return;
    const redirect = encodeURIComponent(
      window.location.pathname + (window.location.search ?? ""),
    );
    router.replace(`/login?redirect=${redirect}`);
  }, [authed, router]);

  const progressQ = useQuery({
    queryKey: ["my_courses"] as const,
    queryFn: getMyCourses,
    staleTime: 120_000,
    enabled: !!authed,
  });
  const treeQ = useQuery({
    queryKey: ["series_tree", seriesId] as const,
    async queryFn(): Promise<SeriesTreeOut | null> {
      if (!seriesId) return null;
      try {
        return await getSeriesTreeFlat(seriesId);
      } catch {
        return null;
      }
    },
    staleTime: 5 * 60_000,
    enabled: !!seriesId,
  });

  const validParams = !!seriesId && !!sessionId;

  /* 找到该系列（优先用进度；兜底用 curriculum tree） */
  const series: null | {
    title: string;
    code?: string | null;
    subjectCode?: string | null;
    levelCode?: string | null;
    modules: Array<{
      id: number;
      title: string | null;
      sessions: Array<{
        id: number;
        title: string | null;
        video_total_seconds?: number | null;
        video_watch_ratio?: number | null;
      }>;
    }>;
    overallProgress?: Pick<
      CourseProgressOut,
      "overall_ratio" | "video_watch_ratio" | "homework_done_ratio" | "exam_done_ratio"
    >;
  } = useMemo(() => {
    const enrolled: CourseProgressOut | undefined = progressQ.data?.find(
      (c) => c.series_id === seriesId,
    );
    if (enrolled) {
      return {
        title: enrolled.series_title,
        code: enrolled.series_code,
        subjectCode: enrolled.subject_code,
        levelCode: enrolled.level_code,
        modules: (enrolled.modules ?? []).map((m: ModuleProgressOut) => ({
          id: m.module_id,
          title: m.module_title ?? null,
          sessions: (m.sessions ?? []).map((s: SessionProgressOut) => ({
            id: s.session_id,
            title: s.session_title ?? null,
            video_total_seconds: s.video_total_seconds ?? null,
            video_watch_ratio: s.video_watch_ratio ?? null,
          })),
        })),
        overallProgress: {
          overall_ratio: enrolled.overall_ratio,
          video_watch_ratio: enrolled.video_watch_ratio,
          homework_done_ratio: enrolled.homework_done_ratio,
          exam_done_ratio: enrolled.exam_done_ratio,
        },
      };
    }
    const cur = treeQ.data;
    if (cur) {
      return {
        title: cur.title,
        code: cur.series_code,
        subjectCode: cur.subject_code,
        levelCode: cur.level_code,
        modules: (cur.modules ?? []).map((m) => ({
          id: m.module_id,
          title: m.title ?? null,
          sessions: (m.sessions ?? []).map((s) => ({
            id: s.session_id,
            title: s.title ?? null,
            video_total_seconds: s.duration_seconds ?? null,
          })),
        })),
      };
    }
    return null;
  }, [progressQ.data, treeQ.data, seriesId]);

  const { flatten, current, idx }: { flatten: FlattenSession[]; current: FlattenSession | null; idx: number } =
    useMemo(() => {
      if (!series) return { flatten: [], current: null, idx: -1 };
      const out: FlattenSession[] = [];
      let counter = 0;
      for (const m of series.modules) {
        for (const s of m.sessions) {
          counter += 1;
          out.push({
            sessionId: s.id,
            sessionTitle: s.title,
            moduleId: m.id,
            moduleTitle: m.title,
            index: counter,
            video_total_seconds: s.video_total_seconds ?? null,
            video_watch_ratio: s.video_watch_ratio ?? null,
          });
        }
      }
      const idx = out.findIndex((x) => x.sessionId === sessionId);
      return { flatten: out, current: idx >= 0 ? out[idx] : null, idx };
    }, [series, sessionId]);

  const prev = idx > 0 ? flatten[idx - 1] : null;
  const next = idx >= 0 && idx < flatten.length - 1 ? flatten[idx + 1] : null;

  const goSibling = useCallback(
    (target: FlattenSession | null) => {
      if (!target) return;
      router.push(`/learning/${seriesId}/${target.sessionId}`, { scroll: true });
      setLiveProgress(null);
    },
    [router, seriesId],
  );

  const loading = progressQ.isLoading || (treeQ.isLoading && !treeQ.data);
  const hasAnyError = !!progressQ.isError || !!treeQ.isError;

  /* 非法参数 404 */
  if (!validParams) {
    return <NotExistPanel reason="seriesId 或 sessionId 参数不合法" showBackToMyCourses />;
  }

  if (!authed) {
    return (
      <div className="rounded-2xl border border-dashed p-10 text-center">
        <Loader2 className="mx-auto mb-2 h-6 w-6 animate-spin text-primary" />
        <div className="text-base font-semibold">请先登录再进入学习页</div>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          本页是登录态专用页面，正跳转到登录页并带上 redirect 回传。
        </p>
      </div>
    );
  }

  if (loading && !series) {
    return <LoadingGrid />;
  }

  if (!series) {
    return (
      <div className="space-y-3">
        <NotExistPanel
          reason="未找到该课程结构（可能尚未生成大纲，或 progress/curriculum 接口未初始化）"
          showBackToMyCourses
        />
        {hasAnyError && (
          <div className="flex items-center justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                void Promise.all([progressQ.refetch(), treeQ.refetch()]).then(() =>
                  toast.message("已重新获取课程与进度数据"),
                );
              }}
            >
              <RotateCcw className="mr-1.5 h-4 w-4" />
              重新加载
            </Button>
          </div>
        )}
      </div>
    );
  }

  if (!current) {
    return (
      <NotExistPanel
        reason={`在该课程中未找到课次 #${sessionId}（共 ${flatten.length} 节）`}
        showBackToMyCourses
      />
    );
  }

  const subjectCode = series.subjectCode ?? undefined;

  return (
    <div className="space-y-5">
      {/* 面包屑 + 上下一课 */}
      <div className="flex flex-wrap items-center gap-3">
        <nav className="flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
          <Crumb href="/dashboard" Icon={Home} label="仪表盘" />
          <CrumbSep />
          <Crumb href="/my-courses" Icon={GraduationCap} label="我的课程" />
          <CrumbSep />
          <Crumb href={`/courses/${seriesId}`} label={series.title} max />
          <CrumbSep />
          <span className="text-foreground">
            <span className="text-muted-foreground">{current.moduleTitle ?? "模块"} · </span>
            第 {current.index} 节 {current.sessionTitle ?? "未命名课次"}
          </span>
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={!prev}
            onClick={() => goSibling(prev)}
            title={prev ? `上一课：${prev.sessionTitle ?? ""}` : "已经是第一节"}
          >
            <ArrowLeft className="mr-1.5 h-4 w-4" />
            上一课
          </Button>
          <Button
            size="sm"
            disabled={!next}
            onClick={() => goSibling(next)}
            title={next ? `下一课：${next.sessionTitle ?? ""}` : "已经是最后一节"}
          >
            下一课
            <ArrowRight className="ml-1.5 h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* 标题 & 元信息 */}
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary" className="text-xs">
              第 {current.index} / {flatten.length} 节
            </Badge>
            {current.video_watch_ratio != null ? (
              <Badge className="text-xs bg-emerald-500 text-white">
                已观看 {(current.video_watch_ratio * 100).toFixed(0)}%
              </Badge>
            ) : null}
            {!progressQ.data?.some((c) => c.series_id === seriesId) ? (
              <Badge className="bg-amber-500 text-white text-xs">
                未报名（仅预览课程大纲）
              </Badge>
            ) : null}
          </div>
          <h1 className="text-2xl font-bold tracking-tight md:text-3xl">
            {current.sessionTitle ?? "未命名课次"}
          </h1>
          <p className="max-w-2xl text-sm text-muted-foreground">
            所属模块：{current.moduleTitle ?? "（未归类）"} · 系列：
            <Link
              className="text-primary hover:underline"
              href={`/courses/${seriesId}`}
              prefetch={false}
            >
              {series.title}
            </Link>
          </p>
        </div>
      </header>

      {/* 主 2 列布局：左侧内容 + 右侧 sticky 侧栏 */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_320px] xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-5 min-w-0">
          <VideoPlayer
            seriesId={seriesId}
            sessionId={sessionId}
            videoSrc={null}
            subjectCode={subjectCode}
            title={current.sessionTitle}
            expectedSeconds={current.video_total_seconds ?? null}
            onProgressUpdate={(p) =>
              setLiveProgress({ ratio: p.ratio, syncedRatio: p.syncedRatio ?? null })
            }
          />
          <InteractiveTabs
            subjectCode={subjectCode}
            seriesId={seriesId}
            sessionId={sessionId}
          />
        </div>
        <div className="lg:sticky lg:top-24">
          <SessionSidebar
            seriesId={seriesId}
            sessionId={sessionId}
            sessionTitle={current.sessionTitle}
            subjectCode={subjectCode}
            keyPoints={undefined /* 使用侧栏内按学科的通用 fallback，后续可接 metadata */}
            courseProgress={series.overallProgress ?? undefined}
            liveSessionWatch={liveProgress}
          />
        </div>
      </div>

      {/* 底部二次「上下课」条 */}
      <footer className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border bg-white/70 p-4 backdrop-blur">
        <div className="text-sm text-muted-foreground">
          {prev ? (
            <>
              <span className="text-muted-foreground/80">← 上一节：</span>
              <b className="text-foreground">{prev.sessionTitle ?? "未命名课次"}</b>
            </>
          ) : (
            <span>这是课程的第一节课</span>
          )}
        </div>
        <Button
          variant="outline"
          size="sm"
          disabled={!prev}
          onClick={() => goSibling(prev)}
        >
          <ArrowLeft className="mr-1.5 h-4 w-4" /> 上一课
        </Button>
        <Button size="sm" disabled={!next} onClick={() => goSibling(next)}>
          下一课 <ArrowRight className="ml-1.5 h-4 w-4" />
        </Button>
        <div className="text-right text-sm text-muted-foreground">
          {next ? (
            <>
              <span className="text-muted-foreground/80">下一节：</span>
              <b className="text-foreground">{next.sessionTitle ?? "未命名课次"}</b>
              <span className="ml-1 text-muted-foreground">→</span>
            </>
          ) : (
            <span>这是课程的最后一节课 🎉</span>
          )}
        </div>
      </footer>
    </div>
  );
}

/* ---------- 子组件 ---------- */

function Crumb({
  href,
  label,
  Icon,
  max,
}: {
  href: string;
  label: string;
  Icon?: React.ComponentType<{ className?: string }>;
  max?: boolean;
}) {
  return (
    <Link
      href={href}
      className={
        "inline-flex items-center gap-1.5 rounded-md hover:text-foreground " +
        (max ? "max-w-[200px] truncate" : "")
      }
      title={label}
    >
      {Icon ? <Icon className="h-3.5 w-3.5" /> : null}
      <span>{label}</span>
    </Link>
  );
}
function CrumbSep() {
  return <ChevronRight className="h-3.5 w-3.5 opacity-60" />;
}

function NotExistPanel({
  reason,
  showBackToMyCourses,
}: {
  reason: string;
  showBackToMyCourses?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-dashed p-10 text-center">
      <div className="mx-auto mb-2 grid h-14 w-14 place-items-center rounded-2xl bg-primary/10 text-primary">
        <GraduationCap className="h-7 w-7" />
      </div>
      <div className="text-base font-semibold">找不到对应的课次或课程</div>
      <p className="mx-auto mt-1 max-w-xl text-sm text-muted-foreground">{reason}</p>
      {showBackToMyCourses && (
        <div className="mt-4 flex items-center justify-center gap-2">
          <Button asChild size="sm" variant="outline">
            <Link href="/my-courses">
              <ArrowLeft className="mr-1.5 h-4 w-4" />
              返回我的课程
            </Link>
          </Button>
          <Button asChild size="sm">
            <Link href="/courses">去课程首页</Link>
          </Button>
        </div>
      )}
    </div>
  );
}

function LoadingGrid() {
  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="space-y-5">
        <div className="aspect-video w-full animate-pulse rounded-2xl border bg-slate-100" />
        <div className="h-48 w-full animate-pulse rounded-2xl border bg-slate-100" />
      </div>
      <div className="space-y-4">
        <div className="h-44 w-full animate-pulse rounded-2xl border bg-slate-100" />
        <div className="h-72 w-full animate-pulse rounded-2xl border bg-slate-100" />
      </div>
    </div>
  );
}

// 避免 pathname + usePathname lint 未使用告警（pathname 目前用于未来接 redirect 计算的回传，不直接读）
export const __path_ref = usePathname;
