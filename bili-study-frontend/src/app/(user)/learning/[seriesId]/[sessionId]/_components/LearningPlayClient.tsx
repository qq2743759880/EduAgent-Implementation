/**
 * LearningPlayClient — task48 学习播放页编排（candy-playful 糖果色，对齐 learning.html）
 *
 * 数据源：
 *   - 契约⑤ getMyCourses()                 → 进度/已报名（task14 已上线）
 *   - 契约⑪ getStudyAccess() / 大纲          → 访问守卫 + 学习大纲（task21 待联调，
 *                                            未就绪时降级：守卫放行 + 大纲用进度兜底 + 标注）
 * GWT：
 *   ① 未报名访问 enrolled_only → 403 ErrorState（不吞错；守卫依据 access.accessible）
 *   ② 15s 打点 tick-batch 落库          → CandyVideoPlayer(useVideoTicks) 负责
 *   ③ 作业/考试提交 → session_*_submission 落库 → HomeworkPanel/ExamPanel
 *   ④ transcode_status 未 completed → 占位不白屏 → CandyVideoPlayer
 */
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { GraduationCap, Home, Loader2, LockKeyhole } from "lucide-react";
import { useAuthStore } from "@/lib/auth-client";
import { getMyCourses, type SessionProgressOut } from "@/lib/api/learning";
import { getStudyAccess, getStudyOutline, type StudyOutline } from "@/lib/api/study";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/error-state";
import { CandyVideoPlayer } from "./CandyVideoPlayer";
import { LearningTabs } from "./LearningTabs";
import { SyllabusPanel } from "./SyllabusPanel";
import { LearningToolbar } from "./LearningToolbar";

export interface LearningPlayClientProps {
  seriesId: number;
  sessionId: number;
}

interface SessionMeta {
  sessionId: number;
  title: string | null;
  videoSrc: string | null;
  transcode: "processing" | "failed" | "missing" | "completed";
  totalSeconds: number | null;
  durationMinutes: number | null;
  watchRatio: number;
  homeworkDone: boolean;
  examDone: boolean;
}

export default function LearningPlayClient({ seriesId, sessionId }: LearningPlayClientProps) {
  const router = useRouter();
  const authed = useAuthStore((s) => s.ready && !!s.token);

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
    queryFn: () => getMyCourses(),
    staleTime: 120_000,
    enabled: !!authed,
  });
  const accessQ = useQuery({
    queryKey: ["study_access", seriesId] as const,
    queryFn: () => getStudyAccess(seriesId),
    staleTime: 5 * 60_000,
    enabled: !!authed && !!seriesId,
    retry: false,
  });
  const outlineQ = useQuery({
    queryKey: ["study_outline", seriesId] as const,
    queryFn: () => getStudyOutline(seriesId),
    staleTime: 5 * 60_000,
    enabled: !!authed && !!seriesId,
    retry: false,
  });

  const validParams = !!seriesId && !!sessionId;

  /* enrolled 判定：契约⑪ access 优先；接口未就绪（报错）时回退「报名列表里有该系列」 */
  const enrolled = useMemo(() => {
    if (accessQ.data) return accessQ.data.accessible;
    if (accessQ.isError) {
      // 契约⑪ 待联调：access 端点未上线 → 用报名列表近似（task21/23 落地后移除）
      return progressQ.data?.some((c) => c.series_id === seriesId) ?? false;
    }
    return true;
  }, [accessQ.data, accessQ.isError, progressQ.data, seriesId]);

  /* 本系列标题 + 课次元信息：优先大纲；缺省用进度兜底 */
  const meta: { seriesTitle: string | null; cur: SessionMeta | null } = useMemo(() => {
    const outline: StudyOutline | null = outlineQ.data ?? null;
    const seriesTitle =
      outline?.series_title ??
      progressQ.data?.find((c) => c.series_id === seriesId)?.series_title ??
      null;

    if (outline) {
      const hit = outline.modules
        .flatMap((m) => m.sessions)
        .find((s) => s.session_id === sessionId);
      if (hit) {
        const ratio = hit.watch_ratio ?? 0;
        const tc: SessionMeta["transcode"] = hit.video_url ? "completed" : "missing";
        return {
          seriesTitle,
          cur: {
            sessionId,
            title: hit.session_title,
            videoSrc: hit.video_url,
            transcode: tc,
            totalSeconds: (hit.duration_minutes ?? 0) * 60 || null,
            durationMinutes: hit.duration_minutes,
            watchRatio: ratio,
            homeworkDone: !!hit.homework_done,
            examDone: ratio >= 0.9,
          },
        };
      }
    }
    // 进度兜底（未拿到大纲时用 P3 progress 合成课次元信息）
    const enrolledSeries = progressQ.data?.find((c) => c.series_id === seriesId);
    const s: SessionProgressOut | undefined = enrolledSeries?.modules
      ?.flatMap((m) => m.sessions ?? [])
      .find((x) => x.session_id === sessionId);
    const ratio =
      s?.video_watch_ratio != null
        ? Math.min(1, Math.max(0, s.video_watch_ratio))
        : 0;
    return {
      seriesTitle,
      cur: {
        sessionId,
        title: s?.session_title ?? null,
        videoSrc: null,
        transcode: "missing",
        totalSeconds: s?.video_total_seconds ?? null,
        durationMinutes: null,
        watchRatio: ratio,
        homeworkDone: (s?.homework_done_ratio ?? 0) >= 1,
        examDone: (s?.exam_done_ratio ?? 0) >= 1,
      },
    };
  }, [outlineQ.data, progressQ.data, seriesId, sessionId]);

  const cur = meta.cur;

  /* 403 守卫（GWT①，不吞错） */
  if (!validParams) {
    return (
      <NotEnrolled
        title="参数不合法"
        reason="seriesId 或 sessionId 缺失或非法"
        showBack
      />
    );
  }
  if (!authed) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-20 text-center">
        <Loader2 className="h-7 w-7 animate-spin text-candy-purple" aria-hidden="true" />
        <p className="text-base font-semibold">请先登录再进入学习页，正在跳转…</p>
      </div>
    );
  }
  if (progressQ.isLoading || (accessQ.isLoading && !accessQ.isError)) {
    return (
      <div
        role="status"
        className="grid gap-5 lg:grid-cols-[minmax(0,1.72fr)_minmax(280px,0.8fr)]"
      >
        <Skeleton h="min-h-[300px]" />
        <Skeleton h="min-h-[420px]" />
      </div>
    );
  }
  if (!enrolled) {
    return (
      <NotEnrolled
        title="未报名 · 本课为报名专属内容"
        reason="仅已报名该班次的学员可观看此 enrolled_only 课次。请先报名本系列后返回继续学习（403）。"
        showBack
      />
    );
  }
  if (!cur) {
    return (
      <NotEnrolled
        title="找不到对应的课次"
        reason={`在该系列中未找到课次 #${sessionId}`}
        showBack
      />
    );
  }

  return (
    <div className="pb-28 md:pb-24">
      {/* 面包屑 */}
      <nav
        aria-label="面包屑"
        className="mb-4 flex flex-wrap items-center gap-1.5 text-sm-table text-muted-foreground"
      >
        <Crumb href="/dashboard" label="仪表盘" Icon={Home} />
        <Sep />
        <Crumb href="/my-courses" label="我的班次" Icon={GraduationCap} />
        <Sep />
        <Crumb href={`/courses/${seriesId}`} label={meta.seriesTitle ?? "课程"} max />
        <Sep />
        <span className="font-bold text-foreground">{cur.title ?? "课次"}</span>
      </nav>

      {/* 主布局：播放+标签 | 大纲 */}
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.72fr)_minmax(280px,0.8fr)]">
        <div className="min-w-0 space-y-2">
          <CandyVideoPlayer
            seriesId={seriesId}
            sessionId={sessionId}
            videoSrc={cur.videoSrc}
            totalSeconds={cur.totalSeconds}
            transcodeStatus={cur.transcode}
            title={cur.title}
          />
          <LearningTabs
            seriesId={seriesId}
            sessionId={sessionId}
            durationMinutes={cur.durationMinutes}
            watchRatio={cur.watchRatio}
            homeworkDone={cur.homeworkDone}
            examDone={cur.examDone}
          />
        </div>
        <div className="lg:sticky lg:top-4">
          <SyllabusPanel
            seriesId={seriesId}
            currentSessionId={sessionId}
            outline={outlineQ.data ?? null}
          />
        </div>
      </div>

      {/* 底部工具栏 */}
      <LearningToolbar seriesId={seriesId} sessionId={sessionId} />
    </div>
  );
}

/* ---------- 子组件 ---------- */

function NotEnrolled({
  title,
  reason,
  showBack,
}: {
  title: string;
  reason: string;
  showBack?: boolean;
}) {
  return (
    <div className="mx-auto max-w-2xl py-10">
      <ErrorState
        role="alert"
        title={
          <span className="inline-flex items-center gap-2">
            <LockKeyhole className="h-4 w-4" aria-hidden="true" /> {title}
          </span>
        }
        message={
          reason.includes("403") ? (
            reason
          ) : (
            <span>
              <b className="text-foreground">{reason}</b>
              {!reason.includes("error") && "（未报名无权访问 enrolled_only 资源）"}
            </span>
          )
        }
      />
      {showBack && (
        <div className="mt-4 flex items-center justify-center gap-2">
          <Button asChild size="sm" variant="ghost">
            <Link href="/my-courses">返回我的班次</Link>
          </Button>
          <Button asChild size="sm">
            <Link href={`/courses`}>去课程中心</Link>
          </Button>
        </div>
      )}
    </div>
  );
}

function Crumb({
  href,
  label,
  Icon,
  max,
}: {
  href: string;
  label: string | null;
  Icon?: React.ComponentType<{ className?: string }>;
  max?: boolean;
}) {
  return (
    <Link
      href={href}
      className={
        "inline-flex items-center gap-1 rounded-md text-muted-foreground hover:text-foreground " +
        (max ? "max-w-[180px] truncate" : "")
      }
    >
      {Icon ? <Icon className="h-3.5 w-3.5" /> : null}
      <span>{label ?? "课程"}</span>
    </Link>
  );
}
function Sep() {
  return <span className="text-muted-foreground/50">›</span>;
}
function Skeleton({ h }: { h: string }) {
  return (
    <div
      className={`animate-pulse rounded-[1.75rem] border-[3px] border-foreground/10 bg-muted/40 ${h}`}
      aria-hidden="true"
    />
  );
}