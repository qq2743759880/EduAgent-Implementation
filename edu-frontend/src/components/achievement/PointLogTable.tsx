/**
 * PointLogTable — 积分总览（等级 / 进度 / 总积分）+ 积分流水分页表
 *
 * 契约：GET /api/gamification/me/points?page&page_size
 *   → { total_points, level_no, level_title, level_progress_pct, logs_total, recent_logs[] }
 *
 * 三态（对抗 fe-task01 #4）：loading（骨架）/ error（错误卡，不显示 0）/
 * empty（无流水空态）明确区分；后端错误时不再把积分显示为 0。
 */
"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Coins, TrendingDown, TrendingUp, Trophy } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatDateTime } from "@/lib/community-meta";
import { getMyPoints, type PointLogItem } from "@/lib/api/community";

const PAGE_SIZE = 10;

const POINT_TYPE_LABEL: Record<string, string> = {
  POST_CREATE: "发布帖子",
  COMMENT_CREATE: "发表回帖",
  LIKE_GAIN: "帖子获赞",
  COMMENT_LIKE_GAIN: "回帖获赞",
  QUIZ_FULL_CORRECT: "练习满分",
  COURSE_FINISHED: "完成课程",
  VOCAB_MASTERED: "单词掌握",
  STUDY_TIME: "学习时长",
  LOGIN: "每日登录",
  BADGE_REWARD: "徽章奖励",
};

function pointTypeLabel(t: string): string {
  return POINT_TYPE_LABEL[t] ?? t;
}

export function PointLogTable() {
  const [page, setPage] = useState(1);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["gamification", "points", page] as const,
    queryFn: () => getMyPoints(page, PAGE_SIZE),
    staleTime: 60_000,
  });

  /* 三态早退：加载中 → 骨架；失败 → 错误卡（绝不渲染 0 分占位，对抗 fe-task01 #4） */
  if (isLoading && !data) return <PointLogSkeleton />;
  if (isError && !data) {
    return (
      <div className="space-y-4">
        <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-8 text-center">
          <div className="text-base font-semibold text-destructive-foreground">积分加载失败</div>
          <p className="mt-1 text-sm text-destructive-foreground/90">请稍后刷新重试。</p>
        </div>
      </div>
    );
  }
  /* data 必达：剩余分支只处理成功态（含带陈旧数据的重试中态） */
  if (!data) return null;

  const logs: PointLogItem[] = data.recent_logs;
  const totalPages = Math.max(1, Math.ceil(data.logs_total / PAGE_SIZE));
  /** 满级判定（对抗 fe-task01 #5）：后端在最高等级时 next_level_min 回退为本级门槛 */
  const maxedLevel = data.next_level_min <= data.level_min;

  return (
    <div className="space-y-4">
      {/* 积分 & 等级总览（fe-task07：深色渐变卡 → 中性卡 + 纯色进度） */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-1.5 rounded-full bg-primary-soft px-3 py-1 text-xs text-primary">
              <Coins className="h-3.5 w-3.5" />
              Lv.{data.level_no} · {data.level_title}
            </div>
            <div className="mt-3 text-4xl font-bold tabular-nums text-primary">
              {data.total_points.toLocaleString()}
            </div>
            <div className="mt-1 text-sm text-muted-foreground">当前积分</div>
          </div>
          <div className="min-w-[180px] flex-1 sm:max-w-xs">
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>
                Lv.{data.level_no}（{data.level_min} 分）
              </span>
              {maxedLevel ? (
                <span className="inline-flex items-center gap-1 text-warning-foreground">
                  <Trophy className="h-3.5 w-3.5" />
                  已达最高等级
                </span>
              ) : (
                <span>
                  下一级 Lv.{data.level_no + 1}（{data.next_level_min} 分）
                </span>
              )}
            </div>
            <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${Math.min(100, Math.max(0, maxedLevel ? 100 : data.level_progress_pct))}%` }}
              />
            </div>
            <div className="mt-1 text-right text-3xs text-muted-foreground">
              {maxedLevel ? "已达成全部等级" : `距下一级 ${Math.round(data.level_progress_pct)}%`}
            </div>
          </div>
        </div>
      </div>

      {/* 积分流水表 */}
      <div className="overflow-hidden rounded-xl border border-border bg-card">
        <div className="border-b border-border px-4 py-3 text-sm font-semibold text-foreground">积分流水</div>

        {isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded-lg bg-muted" />
            ))}
          </div>
        ) : logs.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            还没有积分记录，去社区发帖 / 回帖、完成学习任务赚取第一笔积分吧～
          </div>
        ) : (
          <div className="divide-y divide-border">
            {logs.map((log) => (
              <div key={log.log_id} className="flex items-center gap-3 px-4 py-3">
                <span
                  className={cn(
                    "grid h-8 w-8 shrink-0 place-items-center rounded-lg",
                    log.delta >= 0 ? "bg-success/10 text-success-foreground" : "bg-destructive/10 text-destructive-foreground",
                  )}
                >
                  {log.delta >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-foreground">
                    {pointTypeLabel(log.point_type)}
                  </div>
                  <div className="truncate text-xs text-muted-foreground">
                    {log.note || formatDateTime(log.created_at)} · {formatDateTime(log.created_at)}
                  </div>
                </div>
                <div className="text-right">
                  <div
                    className={cn(
                      "text-sm font-semibold tabular-nums",
                      log.delta >= 0 ? "text-success-foreground" : "text-destructive-foreground",
                    )}
                  >
                    {log.delta >= 0 ? `+${log.delta}` : log.delta}
                  </div>
                  <div className="text-3xs text-muted-foreground tabular-nums">
                    余额 {log.balance_after}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-3 border-t border-border py-3">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              上一页
            </Button>
            <span className="text-xs text-muted-foreground">
              {page} / {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              下一页
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

function PointLogSkeleton() {
  return (
    <div className="space-y-4">
      <div className="h-36 animate-pulse rounded-xl bg-muted" />
      <div className="h-64 animate-pulse rounded-xl border border-border bg-muted/40" />
    </div>
  );
}
