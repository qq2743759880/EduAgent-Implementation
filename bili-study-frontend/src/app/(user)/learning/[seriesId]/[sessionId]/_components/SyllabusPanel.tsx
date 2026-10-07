/**
 * SyllabusPanel — 学习大纲（task48，糖果色 candy-playful）
 *
 * 数据源：契约⑪ GET /api/study/courses/{series_id}/outline（task21 待联调，缺省走 profile 保底）。
 * 课次三态（学中玩）：
 *   ✓ 已完成 = watch_ratio ≥ 0.9 或 homework_done
 *   ▶ 当前   = sessionId === 当前播放课次（橙色高亮 + aria-current）
 *   ○ 未开始 = 其余
 * 点击跳转 /learning/{series_id}/{session_id}。交互层复用 Base UI Accordion（C13）。
 */
"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";
import {
  Accordion,
  AccordionItem,
  AccordionPanel,
  AccordionTrigger,
} from "@/components/ui/accordion";
import type { StudyOutline, StudyModuleOutlineItem } from "@/lib/api/study";

export interface SyllabusPanelProps {
  seriesId: number;
  currentSessionId: number;
  outline: StudyOutline | null;
}

const MODULE_ICONS = ["📚", "📗", "📘", "📙", "📕", "📔"];

function sessionState(s: {
  watch_ratio?: number | null;
  homework_done?: boolean | null;
  session_id: number;
  session_title: string | null;
}, currentSessionId: number): "done" | "current" | "todo" {
  if (s.session_id === currentSessionId) return "current";
  if ((s.watch_ratio ?? 0) >= 0.9 || s.homework_done) return "done";
  return "todo";
}

function SessionRow({
  seriesId,
  s,
  state,
  current,
}: {
  seriesId: number;
  s: {
    session_id: number;
    session_no?: number | null;
    session_title: string | null;
    duration_minutes?: number | null;
  };
  state: "done" | "current" | "todo";
  current: boolean;
}) {
  return (
    <Link
      href={`/learning/${seriesId}/${s.session_id}`}
      aria-current={current ? "page" : undefined}
      className="flex items-center gap-2.5 rounded-lg px-1.5 py-2 text-2xs no-underline transition-colors hover:bg-candy-bg"
    >
      <span
        className={cn(
          "inline-grid h-5 w-5 shrink-0 place-items-center rounded-md text-4xs font-bold",
          state === "done" && "bg-candy-green text-white",
          state === "current" && "bg-candy-orange text-white shadow-[0_2px_0_rgba(31,31,31,0.3)]",
          state === "todo" && "bg-foreground/10 text-muted-foreground",
        )}
        aria-hidden="true"
      >
        {state === "done" ? "✓" : state === "current" ? "▶" : "○"}
      </span>
      <span
        className={cn(
          "min-w-0 flex-1 truncate",
          current ? "font-extrabold text-candy-orange" : "text-foreground",
        )}
      >
        {String(s.session_no ?? "").padStart(2, "0")} {s.session_title ?? "未命名课次"}
      </span>
      {typeof s.duration_minutes === "number" && s.duration_minutes > 0 ? (
        <span className="shrink-0 text-3xs tabular-nums text-muted-foreground">
          {Math.round(s.duration_minutes)}分
        </span>
      ) : null}
    </Link>
  );
}

function ModuleRow({
  seriesId,
  currentSessionId,
  m,
  index,
}: {
  seriesId: number;
  currentSessionId: number;
  m: StudyModuleOutlineItem;
  index: number;
}) {
  const doneCount = m.sessions.filter(
    (s) => (s.watch_ratio ?? 0) >= 0.9 || s.homework_done,
  ).length;
  return (
    <AccordionItem value={`module-${m.module_id}`}>
      <AccordionTrigger className="px-3 font-bold [&_[data-slot=accordion-chevron]]:text-muted-foreground">
        <span className="flex min-w-0 items-center gap-2">
          <span aria-hidden="true">{MODULE_ICONS[index % MODULE_ICONS.length]}</span>
          <span className="truncate">{m.module_title ?? `第 ${m.module_no ?? index + 1} 章`}</span>
          <span className="ml-auto shrink-0 text-3xs font-semibold text-muted-foreground">
            {doneCount}/{m.sessions.length}
          </span>
        </span>
      </AccordionTrigger>
      <AccordionPanel className="space-y-0.5 pt-1">
        {m.sessions.map((s) => {
          const state = sessionState(s, currentSessionId);
          return (
            <SessionRow
              key={s.session_id}
              seriesId={seriesId}
              s={s}
              state={state}
              current={state === "current"}
            />
          );
        })}
      </AccordionPanel>
    </AccordionItem>
  );
}

export function SyllabusPanel({ seriesId, currentSessionId, outline }: SyllabusPanelProps) {
  const modules = outline?.modules ?? [];
  if (!modules.length) {
    return (
      <div className="rounded-2xl border-2 border-dashed border-border bg-white p-6 text-center text-sm text-muted-foreground">
        大纲待后端生成（契约⑪ pending）
      </div>
    );
  }
  return (
    <div className="overflow-hidden rounded-[1.75rem] border-[3px] border-foreground bg-white shadow-[0_5px_0_rgba(31,31,31,0.14)]">
      <div className="flex items-center gap-2 border-b-[3px] border-foreground/10 px-4 py-3.5 text-sm font-extrabold">
        <span
          className="grid h-7 w-7 place-items-center rounded-lg bg-candy-blue/15"
          aria-hidden="true"
        >
          {outline?.overall_ratio != null && outline.overall_ratio >= 0.9 ? "🏁" : "📚"}
        </span>
        课程大纲
        <span className="ml-auto text-xs font-bold text-muted-foreground">
          {outline?.completed_sessions ?? 0}/{outline?.total_sessions ?? 0} 完成
        </span>
      </div>
      <Accordion multiple defaultValue={modules.map((m) => `module-${m.module_id}`)}>
        {modules.map((m, i) => (
          <ModuleRow
            key={m.module_id}
            seriesId={seriesId}
            currentSessionId={currentSessionId}
            m={m}
            index={i}
          />
        ))}
      </Accordion>
    </div>
  );
}