/**
 * 数据概览 4 StatCard（task54）：学习时长 / 完成课次 ← GET /api/users/me/learning-summary；
 * 积分 / 等级 ← GET /api/gamification/me/points（契约⑬ 复用）。错误走 ErrorState（R-7），绝不渲染 0 兜底。
 */
"use client";
import { useQuery } from "@tanstack/react-query";
import { Clock, CheckCircle2, Coins, Trophy } from "lucide-react";
import { getLearningSummary } from "@/lib/api/me";
import { getMyPoints } from "@/lib/api/community";
import { ErrorState } from "@/components/ui/error-state";
import { cn } from "@/lib/utils";

export function StatCards() {
  const summary = useQuery({
    queryKey: ["me", "learning-summary"] as const,
    queryFn: getLearningSummary,
    staleTime: 60_000,
  });
  const points = useQuery({
    queryKey: ["gamification", "points", 1] as const,
    queryFn: () => getMyPoints(1, 10),
    staleTime: 60_000,
  });

  const isLoading = (summary.isLoading || points.isLoading) && (!summary.data || !points.data);
  const isError = (summary.isError || points.isError) && (!summary.data || !points.data);

  if (isError) {
    return (
      <ErrorState
        title="数据概览加载失败"
        message="网络开小差了，请稍后重试。"
        retry={async () => {
          await Promise.allSettled([summary.refetch(), points.refetch()]);
        }}
        retryLabel="重试"
      />
    );
  }
  if (isLoading || !summary.data || !points.data) return <StatCardsSkeleton />;

  const hours = Math.round(summary.data.total_watched_seconds / 3600);
  const cards = [
    {
      key: "hours",
      Icon: Clock,
      tone: "bg-candy-blue-soft",
      value: String(hours),
      unit: "h",
      label: "学习时长",
    },
    {
      key: "cohorts",
      Icon: CheckCircle2,
      tone: "bg-candy-green-soft",
      value: String(summary.data.active_cohorts_count),
      unit: "课次",
      label: "完成课次",
    },
    {
      key: "points",
      Icon: Coins,
      tone: "bg-candy-yellow/25",
      value: points.data.total_points.toLocaleString(),
      unit: "",
      label: "积分",
    },
    {
      key: "level",
      Icon: Trophy,
      tone: "bg-candy-purple-soft",
      value: `Lv.${points.data.level_no}`,
      unit: points.data.level_title ?? "",
      label: "等级",
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {cards.map(({ key, Icon, tone, value, unit, label }) => (
        <div key={key} className="rounded-2xl border-[3px] border-foreground bg-white p-4 shadow-[0_4px_0_rgba(31,31,31,0.14)]">
          <span
            className={cn(
              "grid h-10 w-10 place-items-center rounded-xl border-[2px] border-foreground",
              tone,
            )}
            aria-hidden="true"
          >
            <Icon className="h-5 w-5 text-foreground" />
          </span>
          <div className="mt-3 flex items-baseline gap-1">
            <span className="text-2xl font-black tabular-nums tracking-tight text-foreground">{value}</span>
            {unit ? <span className="text-xs font-extrabold text-muted-foreground">{unit}</span> : null}
          </div>
          <div className="mt-1 text-xs font-bold text-muted-foreground">{label}</div>
        </div>
      ))}
    </div>
  );
}

function StatCardsSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" role="status" aria-label="正在加载数据概览…">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="animate-pulse rounded-2xl border-[3px] border-border bg-white p-4">
          <div className="h-10 w-10 rounded-xl bg-candy-bg" />
          <div className="mt-3 h-6 w-16 rounded-md bg-candy-bg" />
          <div className="mt-2 h-3 w-12 rounded-md bg-candy-bg" />
        </div>
      ))}
    </div>
  );
}