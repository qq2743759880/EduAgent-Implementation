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
    <Card className={cn("border-border shadow-card bg-card", className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-3">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-warning-foreground" />
              连续打卡
            </CardTitle>
            <CardDescription className="text-sm text-muted-foreground pt-1">坚持学习，解锁更多徽章与积分奖励</CardDescription>
          </div>
          <div className="flex items-center gap-1 rounded-xl px-3 py-1.5 bg-warning-foreground text-white shadow-sm">
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
                <span className="text-4xs font-medium text-muted-foreground">{DAY_LABELS[i]}</span>
                <div
                  aria-label={`day-${i + 1}-${st}`}
                  className={cn(
                    "h-9 w-full rounded-xl border flex items-center justify-center transition-all",
                    styles.className,
                  )}
                  style={styles.style}
                >
                  {isToday ? <span className="h-1.5 w-1.5 rounded-full bg-primary" /> : cellIcon(st)}
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * 打卡状态格（fe-task07 收敛）：状态机渐变 → 状态 token 纯色；
 * done=success（已打卡）/ partial=warning（部分）/ today=主色描边（今天）/ rest=中性。
 */
function cellStyles(st: DayStatus): { className: string; style?: CSSProperties } {
  switch (st) {
    case "done":
      return {
        className:
          "bg-success border-success/40 text-white",
      };
    case "partial":
      return {
        className:
          "bg-warning-foreground border-warning/40 text-white",
      };
    case "today":
      return {
        className:
          "bg-card border-primary-border border-2 ring-2 ring-primary/10 text-primary",
      };
    case "rest":
    default:
      return { className: "bg-muted border-border text-muted-foreground/60" };
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
      return <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40" />;
  }
}

export default StreakBadge;
