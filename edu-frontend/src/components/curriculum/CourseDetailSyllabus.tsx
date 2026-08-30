/**
 * CourseDetailSyllabus — 课程详情页「课程大纲」四级树（task46，对齐 P8 + HTML 效果图）。
 * 层级：系列（页面上下文）→ 班次（cohortName 头部）→ 模块（stage_no 升序）→ 课次（session_no 升序）。
 * 课次 teaching_status 徽章走 StatusBadge（颜色+文字双通道）。
 */
"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Clock, Video } from "lucide-react";
import { StatusBadge } from "@/components/ui/status-badge";
import type { ModuleWithSessions, Session } from "@/lib/api/curriculum";
import { cn } from "@/lib/utils";

export function CourseDetailSyllabus({
  cohortName,
  modules = [],
}: {
  cohortName: string;
  modules?: ModuleWithSessions[];
}) {
  const totalSessions = modules.reduce((sum, m) => sum + (m.sessions?.length ?? 0), 0);
  const sorted = [...modules].sort((a, b) => (a.stage_no ?? 0) - (b.stage_no ?? 0));

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 rounded-xl border-2 border-border bg-card px-4 py-3">
        <span aria-hidden="true" className="text-lg">📅</span>
        <span className="text-sm font-bold text-foreground">{cohortName}</span>
        <span className="text-3xs text-muted-foreground">
          {modules.length} 个模块 · {totalSessions} 节课次
        </span>
      </div>

      {sorted.length === 0 ? (
        <p className="rounded-xl border-2 border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          该班次暂无课程大纲，请稍后再试。
        </p>
      ) : (
        sorted.map((m) => <ModuleBlock key={m.id} module={m} />)
      )}
    </div>
  );
}

function ModuleBlock({ module }: { module: ModuleWithSessions }) {
  const [open, setOpen] = useState(true);
  const sessions = [...(module.sessions ?? [])].sort((a, b) => (a.session_no ?? 0) - (b.session_no ?? 0));
  const minutes = sessions.reduce(
    (s, x) => s + Math.round((x.videos?.[0]?.duration_seconds ?? 0) / 60),
    0,
  );

  return (
    <div className="overflow-hidden rounded-xl border-2 border-border bg-card">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40"
      >
        <span
          aria-hidden="true"
          className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-candy-green text-sm font-bold text-white shadow-[0_2px_0_rgba(31,31,31,0.14)]"
        >
          {module.stage_no ?? "·"}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-bold text-foreground">
            {module.module_name || `模块 ${module.stage_no ?? ""}`}
          </span>
          <span className="mt-0.5 flex flex-wrap items-center gap-2 text-3xs text-muted-foreground">
            <span>{module.lesson_count ?? sessions.length} 节课次</span>
            {minutes > 0 && (
              <span className="inline-flex items-center gap-0.5">
                <Clock className="h-3 w-3" aria-hidden="true" />
                {minutes < 60 ? `${minutes} 分钟` : `${Math.floor(minutes / 60)}h ${minutes % 60}m`}
              </span>
            )}
            {module.stage_no != null && module.stage_no > 0 && <span>阶段 {module.stage_no}</span>}
          </span>
        </span>
        {open ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        )}
      </button>
      {open && sessions.length > 0 && (
        <ul className="border-t border-border px-4 py-1">
          {sessions.map((s) => (
            <SessionRow key={s.id} session={s} />
          ))}
        </ul>
      )}
      {open && sessions.length === 0 && module.lesson_count ? (
        <p className="border-t border-border px-4 py-3 text-xs text-muted-foreground">
          该模块含 {module.lesson_count} 节课次，完整数据请稍后再试。
        </p>
      ) : null}
    </div>
  );
}

function SessionRow({ session }: { session: Session }) {
  const hasVideo = (session.videos ?? []).some((v) => v.file_url);
  const date = session.teaching_date?.slice(0, 10);
  return (
    <li className="flex items-center gap-3 py-2.5">
      <span className="w-6 shrink-0 text-xs tabular-nums text-muted-foreground">
        {String(session.session_no ?? "").padStart(2, "0")}
      </span>
      {hasVideo ? (
        <Video className="h-4 w-4 shrink-0 text-candy-green" aria-hidden="true" />
      ) : (
        <span aria-hidden="true" className="h-4 w-4 shrink-0 rounded-full border-2 border-muted-foreground/30" />
      )}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm text-foreground">
          {session.session_title || "未命名课次"}
        </span>
        <span className="mt-0.5 block text-3xs text-muted-foreground">
          {date ?? "-"} {session.start_time ?? ""}
        </span>
      </span>
      <StatusBadge
        map="teaching_status"
        status={session.teaching_status}
        className={cn("shrink-0")}
      />
    </li>
  );
}
