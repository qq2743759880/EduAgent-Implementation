/**
 * MyCourseCard — 我的课程卡片（进行中 / 已完成 / 已收藏 均使用）
 * 展示：封面渐变（学科色）+ 收藏按钮 + 三级进度条（视频/作业/考试叠加 overall）
 *       上次活动时间 / 下一课 / 继续学习按钮
 */
"use client";

import Link from "next/link";
import { Clock, PlayCircle, Star, Trophy } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  LEVEL_OPTIONS,
  SUBJECT_OPTIONS,
  type SubjectCode,
} from "@/lib/api/curriculum";
import {
  isSeriesFavorited,
  toggleFavoriteSeries,
  type CourseProgressOut,
} from "@/lib/api/learning";
import { cn } from "@/lib/utils";
import { useEffect, useState } from "react";

export function MyCourseCard({
  data,
  onFavoritedChange,
}: {
  data: CourseProgressOut;
  onFavoritedChange?: (nextFav: boolean) => void;
}) {
  const subject = SUBJECT_OPTIONS.find((s) => s.code === data.subject_code);
  const level = LEVEL_OPTIONS.find((l) => l.code === data.level_code);

  const overall = clamp1(data.overall_ratio ?? 0);
  const video = clamp1(data.video_watch_ratio ?? 0);
  const hw = clamp1(data.homework_done_ratio ?? 0);
  const exam = clamp1(data.exam_done_ratio ?? 0);
  const completed = overall >= 0.9999;

  const [fav, setFav] = useState<boolean>(() =>
    typeof data.__favorited === "boolean"
      ? data.__favorited
      : typeof window !== "undefined" && isSeriesFavorited(data.series_id),
  );

  /* SSR 结束后 localStorage 再同步一次，避免 hydration mismatch */
  useEffect(() => {
    if (typeof data.__favorited === "boolean") return;
    setFav(isSeriesFavorited(data.series_id));
  }, [data.series_id, data.__favorited]);

  const nextSession = findNextSession(data);
  const nextHref = nextSession
    ? `/learning/${data.series_id}/${nextSession.session_id}`
    : `/courses/${data.series_id}`;

  const lastActivityLabel = data.last_activity_at
    ? formatRelative(data.last_activity_at)
    : data.enrolled_at
      ? `报名于 ${formatDate(data.enrolled_at)}`
      : null;

  return (
    <Card className="group h-full overflow-hidden transition-all hover:-translate-y-0.5 hover:shadow-md">
      <div
        className={
          "relative h-32 w-full overflow-hidden bg-gradient-to-br " +
          subjectGradient(data.subject_code as SubjectCode)
        }
      >
        <div className="pointer-events-none absolute inset-0 [background-image:radial-gradient(ellipse_at_top_right,rgba(255,255,255,0.3),transparent_60%)]" />
        <div className="absolute left-3 top-3 flex items-center gap-1.5">
          {subject && (
            <Badge className={"text-white " + subject.color}>{subject.name}</Badge>
          )}
          {level && (
            <Badge variant="secondary" className="bg-white/85 text-slate-700 backdrop-blur-sm">
              {level.short}
            </Badge>
          )}
          {completed && (
            <Badge className="bg-emerald-600 text-white">
              <Trophy className="mr-1 h-3 w-3" /> 已完成
            </Badge>
          )}
        </div>
        <button
          type="button"
          aria-label={fav ? "取消收藏" : "收藏课程"}
          onClick={() => {
            const next = toggleFavoriteSeries(data.series_id);
            setFav(next);
            onFavoritedChange?.(next);
          }}
          className="absolute right-3 top-3 grid h-8 w-8 place-items-center rounded-full bg-white/80 text-amber-500 shadow-sm backdrop-blur transition-transform hover:scale-110"
        >
          <Star className={"h-4 w-4 " + (fav ? "fill-amber-400" : "")} />
        </button>
        <div className="absolute bottom-3 left-4 right-4 text-white drop-shadow-sm">
          <div className="truncate text-base font-semibold">{data.series_title}</div>
        </div>
      </div>

      <CardContent className="space-y-4 p-4">
        <div className="space-y-2">
          <ProgressStack
            video={video}
            homework={hw}
            exam={exam}
            overall={overall}
          />
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>
              视频 {(video * 100).toFixed(0)}% · 作业 {(hw * 100).toFixed(0)}% · 考试{" "}
              {(exam * 100).toFixed(0)}%
            </span>
            <span className="font-semibold text-foreground">
              总进度 {(overall * 100).toFixed(0)}%
            </span>
          </div>
        </div>

        <SeparatorSoft />

        <div className="space-y-1.5 text-sm">
          {nextSession && (
            <div className="flex items-center gap-2 text-foreground/90">
              <PlayCircle className="h-4 w-4 text-primary" />
              <span className="truncate">下一课：{nextSession.title || "未命名课次"}</span>
            </div>
          )}
          {lastActivityLabel && (
            <div className="flex items-center gap-2 text-muted-foreground text-xs">
              <Clock className="h-3.5 w-3.5" />
              {lastActivityLabel}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between pt-1">
          <Badge variant="outline" className="text-xs">
            {data.modules?.length ?? 0} 模块
          </Badge>
          <Button asChild size="sm">
            <Link href={nextHref}>
              {completed ? (
                <>
                  <Trophy className="mr-1.5 h-4 w-4" /> 查看成就
                </>
              ) : (
                <>
                  <PlayCircle className="mr-1.5 h-4 w-4" /> 继续学习
                </>
              )}
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/* ---------- 复合进度条：三段堆叠（视频→作业→考试）+ overall 底线 ---------- */
function ProgressStack({
  video,
  homework,
  exam,
  overall,
}: {
  video: number;
  homework: number;
  exam: number;
  overall: number;
}) {
  return (
    <div className="space-y-1.5">
      <div className="relative h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className="absolute inset-y-0 left-0 bg-sky-400"
          style={{ width: `${video * 100}%` }}
        />
        <div
          className="absolute inset-y-0 left-0 bg-emerald-500 mix-blend-multiply"
          style={{ width: `${homework * 100}%`, opacity: 0.7 }}
        />
        <div
          className="absolute inset-y-0 left-0 bg-violet-500 mix-blend-multiply"
          style={{ width: `${exam * 100}%`, opacity: 0.55 }}
        />
      </div>
      <div className="relative h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div
          className={
            "absolute inset-y-0 left-0 rounded-full " +
            (overall >= 0.9999
              ? "bg-gradient-to-r from-emerald-500 to-teal-400"
              : "bg-gradient-to-r from-primary to-indigo-400")
          }
          style={{ width: `${Math.min(100, overall * 100)}%` }}
        />
      </div>
    </div>
  );
}

function findNextSession(data: CourseProgressOut): { session_id: number; title?: string | null } | null {
  const overall = clamp1(data.overall_ratio ?? 0);
  if (overall >= 0.9999 && data.last_session_id) {
    // 完成后，跳最后一课
    return { session_id: data.last_session_id, title: data.last_session_title };
  }
  // 按模块顺序找第一个视频进度未 100% 的课次
  for (const mod of data.modules ?? []) {
    for (const s of mod.sessions ?? []) {
      const v = clamp1(s.video_watch_ratio ?? 0);
      if (v < 0.999) {
        return { session_id: s.session_id, title: s.session_title };
      }
    }
  }
  if (data.last_session_id) {
    return { session_id: data.last_session_id, title: data.last_session_title };
  }
  return null;
}

function clamp1(v: number) {
  if (!Number.isFinite(v)) return 0;
  return Math.max(0, Math.min(1, v));
}

function SeparatorSoft() {
  return <div className="h-px w-full bg-slate-100" />;
}

function subjectGradient(code?: SubjectCode | string | null): string {
  switch (code) {
    case "english":
      return "from-sky-500 via-sky-400 to-cyan-400";
    case "programming":
      return "from-violet-500 via-indigo-500 to-purple-500";
    case "math":
      return "from-emerald-500 via-teal-500 to-green-500";
    case "chinese":
      return "from-amber-500 via-orange-400 to-yellow-400";
    case "physics":
      return "from-rose-500 via-pink-500 to-red-500";
    default:
      return "from-slate-500 via-slate-400 to-slate-600";
  }
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  } catch {
    return iso.slice(0, 10);
  }
}

function formatRelative(iso: string): string {
  try {
    const now = Date.now();
    const t = new Date(iso).getTime();
    const diff = Math.max(0, Math.floor((now - t) / 1000));
    if (diff < 60) return "刚刚活动过";
    if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前学过`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前学过`;
    if (diff < 7 * 86400) return `${Math.floor(diff / 86400)} 天前学过`;
    return `上次：${formatDate(iso)}`;
  } catch {
    return formatDate(iso);
  }
}
