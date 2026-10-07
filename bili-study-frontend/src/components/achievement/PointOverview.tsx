/**
 * PointOverview — 积分/等级总览（candy-playful frozen，task53 对齐 approved achievements.html）
 * - Lv.N 徽标 + 总积分大数字 + 等级进度条 → 下一级（或已达最高等级）
 * - 满级判定（对抗 fe-task01 #5）：next_level_min <= level_min 时满 100% + 「已达最高等级」
 * - 三态（对抗 fe-task01 #4）：loading 骨架 / error 错误卡（绝不显示 0 分占位）/ success
 * 契约：GET /api/gamification/me/points → { total_points, level_no, level_title, level_progress_pct, ... }
 */
"use client";

import { useQuery } from "@tanstack/react-query";
import { Coins, Trophy } from "lucide-react";

import { ErrorState } from "@/components/ui/error-state";
import { getMyPoints } from "@/lib/api/community";

export function PointOverview() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["gamification", "points", 1] as const,
    queryFn: () => getMyPoints(1, 10),
    staleTime: 60_000,
  });

  if (isLoading && !data) return <PointOverviewSkeleton />;
  if (isError && !data) {
    return <ErrorState title="积分加载失败" message="网络开小差了，请稍后重试。" retry={refetch} retryLabel="重试" />;
  }
  if (!data) return null;

  /** 满级判定：后端在最高级时 next_level_min 回退为本级门槛 */
  const maxedLevel = data.next_level_min <= data.level_min;
  const pct = Math.min(100, Math.max(0, maxedLevel ? 100 : data.level_progress_pct));

  return (
    <div id="points-overview" className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border-[3px] border-foreground bg-white p-5 shadow-[0_4px_0_rgba(31,31,31,0.14)] md:flex-nowrap">
      <div className="flex flex-col gap-2">
        <span className="inline-flex w-fit items-center gap-1.5 rounded-full border-[2px] border-candy-purple/35 bg-candy-purple-soft px-3 py-1 text-xs font-extrabold text-primary">
          <Coins className="h-3.5 w-3.5" aria-hidden="true" />
          Lv.{data.level_no} · {data.level_title}
        </span>
        <div className="text-4xl font-extrabold tabular-nums text-foreground">{data.total_points.toLocaleString()}</div>
        <div className="text-sm font-semibold text-muted-foreground">当前积分</div>
      </div>

      <div className="min-w-[200px] flex-1 md:max-w-xs">
        <div className="flex items-center justify-between text-xs font-semibold text-muted-foreground">
          <span>
            Lv.{data.level_no}（<b className="text-foreground">{data.level_min}</b> 分）
          </span>
          {maxedLevel ? (
            <span className="inline-flex items-center gap-1 font-extrabold text-warning-foreground">
              <Trophy className="h-3.5 w-3.5" aria-hidden="true" />
              已达最高等级
            </span>
          ) : (
            <span>
              下一级 Lv.{data.level_no + 1}（<b className="text-foreground">{data.next_level_min}</b> 分）
            </span>
          )}
        </div>
        <div className="mt-2 h-3 overflow-hidden rounded-full border-[2px] border-foreground bg-white">
          <div
            className="h-full rounded-full bg-gradient-to-r from-candy-green to-candy-blue"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={pct}
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="mt-1 text-right text-3xs font-bold text-muted-foreground">
          {maxedLevel ? "已达成全部等级" : `距下一级 ${Math.round(pct)}%`}
        </div>
      </div>
    </div>
  );
}

function PointOverviewSkeleton() {
  return (
    <div className="h-36 animate-pulse rounded-2xl border-[3px] border-border bg-white" role="status" aria-label="正在加载积分…" />
  );
}