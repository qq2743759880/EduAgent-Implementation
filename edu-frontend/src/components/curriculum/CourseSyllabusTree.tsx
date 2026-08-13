/**
 * CourseSyllabusTree — 课程详情页「教学大纲」折叠树
 * 数据来源：/api/curriculum/series/{id}/tree （后端已返回 modules 数组，每个模块可带 sessions）
 */
"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Clock, Lock, PlayCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import type { ModuleOut, SessionOut } from "@/lib/api/curriculum";

export function CourseSyllabusTree({ modules = [] }: { modules?: ModuleOut[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">教学大纲</CardTitle>
        <p className="text-sm text-muted-foreground">
          共 {modules.length} 个模块，
          {modules.reduce((sum, m) => sum + (m.sessions?.length ?? m.session_count ?? 0), 0)} 节
          课次
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {modules.length === 0 ? (
          <EmptySyllabus />
        ) : (
          modules.map((m, i) => <ModuleBlock key={m.id ?? i} index={i + 1} module={m} />)
        )}
      </CardContent>
    </Card>
  );
}

function ModuleBlock({ index, module }: { index: number; module: ModuleOut }) {
  const [open, setOpen] = useState(index <= 2);
  const sessions = module.sessions ?? [];
  const sessionCount = sessions.length || module.session_count || 0;
  const minutes = sessions.reduce(
    (s, x) => s + (typeof x.duration_minutes === "number" ? x.duration_minutes : 0),
    0,
  );

  return (
    <div className="rounded-xl border bg-card">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-primary/10 text-sm font-semibold text-primary">
          {index}
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium">
            {module.module_title || `模块 ${index}`}
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span>{sessionCount} 节</span>
            {minutes > 0 && (
              <>
                <Separator orientation="vertical" className="h-3" />
                <ClockInline minutes={minutes} />
              </>
            )}
            {module.stage_no != null && (
              <>
                <Separator orientation="vertical" className="h-3" />
                <span>阶段 {module.stage_no}</span>
              </>
            )}
          </div>
        </div>
        {open ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        )}
      </button>
      {open && sessions.length > 0 && (
        <div className="border-t px-4 py-2">
          <ul className="divide-y">
            {sessions.map((s, i) => (
              <SessionRow key={s.id ?? i} session={s} index={i + 1} />
            ))}
          </ul>
        </div>
      )}
      {open && sessions.length === 0 && module.session_count ? (
        <div className="border-t px-4 py-3 text-xs text-muted-foreground">
          该模块含 {module.session_count} 节课次，完整数据请加载树接口。
        </div>
      ) : null}
    </div>
  );
}

function SessionRow({ session, index }: { session: SessionOut; index: number }) {
  const isFree = (session.is_free_preview ?? 0) !== 0;
  const dur = session.duration_minutes;
  const date = session.teaching_date;

  return (
    <li className="flex items-center gap-3 py-2.5">
      <span className="w-6 text-xs tabular-nums text-muted-foreground">
        {String(index).padStart(2, "0")}
      </span>
      {isFree ? (
        <PlayCircle className="h-4 w-4 text-success" />
      ) : (
        <Lock className="h-4 w-4 text-muted-foreground/70" />
      )}
      <div className="min-w-0 flex-1 text-sm">
        <div className="truncate">{session.session_title || "未命名课次"}</div>
        <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {isFree && <Badge variant="outline" className="text-success-foreground">免费试看</Badge>}
          {dur != null && <ClockInline minutes={Number(dur)} />}
          {date && <span>{date}</span>}
        </div>
      </div>
    </li>
  );
}

function ClockInline({ minutes }: { minutes: number }) {
  if (!minutes) return null;
  if (minutes < 60) return <span className="inline-flex items-center gap-1"><Clock className="h-3.5 w-3.5" />{minutes} 分钟</span>;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return (
    <span className="inline-flex items-center gap-1">
      <Clock className="h-3.5 w-3.5" />
      {h}h {m}m
    </span>
  );
}

function EmptySyllabus() {
  return (
    <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
      暂无大纲数据，请稍后再试。
    </div>
  );
}
