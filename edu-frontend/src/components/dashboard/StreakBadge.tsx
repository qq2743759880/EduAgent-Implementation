"use client";

import { Flame, Sparkles } from "lucide-react";
import type { CSSProperties } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type DayStatus = "done" | "partial" | "rest" | "today";

export interface StreakBadgeProps {
  /** 连续打卡天数（>= 0） */
  streakDays: number;
  /** 近 7 天状态，按「最老 day 0 … day 6 = 今天」的顺序传，最多 7 个；少的按 rest 占位 */
  last7Days?: (DayStatus | null | undefined)[];
  className?: string;
}

const DAY_LABELS = ["一", "二", "三", "四", "五", "六", "日"] as const;

export function StreakBadge({ streakDays, last7Days, className }: StreakBadgeProps) {
  const days: DayStatus[] = Array.from({ length: 7 }, (_, idx) => {
    const v = last7Days?.[idx];
    if (!v) return idx === 6 ? "today" : "rest";
    return v;
  });
  /* 若传的 last7Days 最后一天不是 today 且 today == rest/partial，手动标 today */
  if (days[6] === "rest") days[6] = "today";

  return (
    <Card className={cn("border-slate-200/80 shadow-sm bg-gradient-to-br from-amber-50/70 via-white to-orange-50/70", className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-3">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-amber-500" />
              连续打卡
            </CardTitle>
            <CardDescription className="text-sm text-slate-500 pt-1">坚持学习，解锁更多徽章与积分奖励</CardDescription>
          </div>
          <div className="flex items-center gap-1 rounded-2xl px-3 py-1.5 bg-gradient-to-br from-amber-500 to-orange-500 text-white shadow-sm ring-8 ring-amber-100">
            <Flame className="h-4 w-4" />
            <span className="font-bold tabular-nums text-lg leading-none">{streakDays}</span>
            <span className="text-xs ml-0.5 opacity-90">天</span>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-1">
        <div className="grid grid-cols-7 gap-2 max-w-md mx-auto">
          {days.map((st, i) => {
            const isToday = i === 6 || st === "today";
            const styles = cellStyles(st);
            return (
              <div key={i} className="flex flex-col items-center gap-1.5">
                <span className="text-[10px] font-medium text-slate-400">{DAY_LABELS[i]}</span>
                <div
                  aria-label={`day-${i + 1}-${st}`}
                  className={cn(
                    "h-9 w-full rounded-xl border flex items-center justify-center transition-all",
                    styles.className,
                  )}
                  style={styles.style}
                >
                  {isToday ? <span className="h-1.5 w-1.5 rounded-full bg-white/80" /> : cellIcon(st)}
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

function cellStyles(st: DayStatus): { className: string; style?: CSSProperties } {
  switch (st) {
    case "done":
      return {
        className:
          "bg-gradient-to-br from-emerald-500 to-teal-600 border-emerald-400 shadow-sm text-white",
      };
    case "partial":
      return {
        className:
          "bg-gradient-to-br from-amber-300 to-amber-500 border-amber-300 text-white",
      };
    case "today":
      return {
        className:
          "bg-white border-indigo-300 border-2 ring-2 ring-indigo-100 text-indigo-600",
      };
    case "rest":
    default:
      return { className: "bg-slate-100/70 border border-slate-200 text-slate-300" };
  }
}

function cellIcon(st: DayStatus) {
  switch (st) {
    case "done":
      return <span className="text-xs font-bold">✓</span>;
    case "partial":
      return <span className="text-xs font-bold">~</span>;
    case "today":
      return null;
    default:
      return <span className="h-1.5 w-1.5 rounded-full bg-slate-200" />;
  }
}

export default StreakBadge;
