/**
 * PointLogList — 积分流水分页（candy-playful frozen，task53 对齐 approved achievements.html）
 * - 每条流水：point_type 文案映射 + note + 时间 + delta（正向绿/负向红）+ 余额
 * - delta 符号展示：正向 `+N` 绿（success-foreground）/ 负向 `-N` 红（destructive-foreground）
 * - 分页 C2（Pagination 位移分页）：PAGE_SIZE=10；logs_total 驱动
 * - 空态 C7：还没有积分记录，去社区发帖 / 回帖、完成学习任务赚取第一笔积分吧～
 * 契约：GET /api/gamification/me/points?page&page_size → { ...logs_total, recent_logs: PointLogItem[] }
 */
"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { TrendingDown, TrendingUp } from "lucide-react";

import { cn } from "@/lib/utils";
import { EmptyState } from "@/components/ui/empty-state";
import { Pagination } from "@/components/ui/pagination";
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

export function PointLogList() {
  const [page, setPage] = useState(1);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["gamification", "points", page] as const,
    queryFn: () => getMyPoints(page, PAGE_SIZE),
    staleTime: 60_000,
  });

  if (isLoading && !data) return <PointLogListSkeleton />;
  if (isError && !data) return null; /* 错误已在 PointOverview 统一呈现 */
  if (!data) return null;

  const logs: PointLogItem[] = data.recent_logs;

  return (
    <div className="overflow-hidden rounded-2xl border-[3px] border-foreground bg-white shadow-[0_4px_0_rgba(31,31,31,0.14)]">
      <div className="border-b-2 border-dashed border-foreground/15 px-4 py-3 text-sm font-extrabold text-foreground">
        积分流水 <span className="font-semibold text-muted-foreground">共 {data.logs_total} 条</span>
      </div>

      {logs.length === 0 ? (
        <EmptyState
          icon={<span className="text-3xl" aria-hidden="true">🪙</span>}
          title="还没有积分记录"
          description="还没有积分记录，去社区发帖 / 回帖、完成学习任务赚取第一笔积分吧～"
        />
      ) : (
        <div className="divide-y divide-dashed divide-foreground/10">
          {logs.map((log) => (
            <div key={log.log_id} className="flex items-center gap-3 px-4 py-3">
              <span
                className={cn(
                  "grid h-9 w-9 shrink-0 place-items-center rounded-xl border-[2px] border-foreground",
                  log.delta >= 0 ? "bg-candy-green-soft text-success-foreground" : "bg-candy-orange-soft text-destructive-foreground",
                )}
                aria-hidden="true"
              >
                {log.delta >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-bold text-foreground">{pointTypeLabel(log.point_type)}</div>
                <div className="truncate text-xs text-muted-foreground">
                  {[log.note, formatDateTime(log.created_at)].filter(Boolean).join(" · ")}
                </div>
              </div>
              <div className="text-right">
                <div className={cn("text-sm font-extrabold tabular-nums", log.delta >= 0 ? "text-success-foreground" : "text-destructive-foreground")}>
                  {log.delta >= 0 ? `+${log.delta}` : log.delta}
                </div>
                <div className="text-3xs tabular-nums text-muted-foreground">余额 {log.balance_after.toLocaleString()}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {data.logs_total > PAGE_SIZE && (
        <div className="border-t-2 border-dashed border-foreground/15 p-3">
          <Pagination page={page} pageSize={PAGE_SIZE} total={data.logs_total} onPageChange={setPage} />
        </div>
      )}
    </div>
  );
}

function PointLogListSkeleton() {
  return (
    <div className="h-64 animate-pulse rounded-2xl border-[3px] border-border bg-white" role="status" aria-label="正在加载积分流水…" />
  );
}