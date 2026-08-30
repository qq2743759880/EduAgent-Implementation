/**
 * RankingTabs — 排行榜（candy-playful frozen，task53 对齐 approved achievements.html）
 * - 双 tablist：时间范围 日/周/月/总 × 维度 积分/学习时长/徽章数（APG Tabs + roving tabindex + 方向键）
 * - 前三名奖牌（👑 金 / 🥈 银 / 🥉 铜），1 名金色背景 + 2/3 名灰底；名次由数字文本兜底
 * - is_myself 行高亮 +「我」徽标；底部「我的排名」；source 实时标记
 * - 空态 C7 / 错误态 ErrorState + 重试
 * 契约：GET /api/gamification/rankings?scope&dimension&top_n=20
 *   → { top: RankingRow[], my_rank, source }；数据来自 ZSET（task15 已验证 4 周期 key + 积分实时累计）
 */
"use client";

import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Award, Crown, Medal, Timer, TrendingUp, Trophy } from "lucide-react";

import { cn } from "@/lib/utils";
import { ErrorState } from "@/components/ui/error-state";
import { EmptyState } from "@/components/ui/empty-state";
import { getRankings, type RankingDimension, type RankingScope } from "@/lib/api/community";

const SCOPE_TABS: Array<{ value: RankingScope; label: string }> = [
  { value: "DAILY", label: "日榜" },
  { value: "WEEKLY", label: "周榜" },
  { value: "MONTHLY", label: "月榜" },
  { value: "ALL_TIME", label: "总榜" },
];

const DIMENSION_TABS: Array<{ value: RankingDimension; label: string; Icon: typeof Trophy }> = [
  { value: "POINTS", label: "积分", Icon: Trophy },
  { value: "STUDY_MIN", label: "学习时长", Icon: Timer },
  { value: "BADGE_COUNT", label: "徽章数", Icon: Award },
];

const DIMENSION_UNIT: Record<RankingDimension, string> = {
  POINTS: "分",
  STUDY_MIN: "分钟",
  BADGE_COUNT: "枚",
};

/** 前三名奖牌：1 名金色（candy-yellow）+ 数字兜底；2/3 名灰底奖牌 */
const MEDAL_FOR: Record<number, { Icon: typeof Crown; noClass: string }> = {
  1: { Icon: Crown, noClass: "border-foreground bg-candy-yellow text-foreground shadow-[0_3px_0_rgba(31,31,31,0.25)]" },
  2: { Icon: Medal, noClass: "border-foreground bg-candy-silver text-foreground shadow-[0_3px_0_rgba(31,31,31,0.2)]" },
  3: { Icon: Medal, noClass: "border-foreground bg-candy-orange-soft text-foreground shadow-[0_3px_0_rgba(31,31,31,0.2)]" },
};

/** 排行内容面板（两组 tablist 的 aria-controls 共同指向） */
const RANKINGS_PANEL_ID = "rankings-panel";

/** 键盘方向键导航（APG Tabs）：左右/上下循环 + Home/End */
function moveTabIndex(key: string, index: number, length: number): number {
  if (key === "Home") return 0;
  if (key === "End") return length - 1;
  if (key === "ArrowRight" || key === "ArrowDown") return (index + 1) % length;
  if (key === "ArrowLeft" || key === "ArrowUp") return (index - 1 + length) % length;
  return index;
}

export function RankingTabs() {
  const [scope, setScope] = useState<RankingScope>("DAILY");
  const [dimension, setDimension] = useState<RankingDimension>("POINTS");

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["gamification", "rankings", scope, dimension] as const,
    queryFn: () => getRankings(scope, dimension, 20),
    staleTime: 60_000,
  });

  const top = data?.top ?? [];
  const myRank = data?.my_rank ?? null;

  const scopeRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const dimensionRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const onScopeKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    const next = moveTabIndex(e.key, index, SCOPE_TABS.length);
    setScope(SCOPE_TABS[next].value);
    scopeRefs.current[next]?.focus();
  };

  const onDimensionKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    const next = moveTabIndex(e.key, index, DIMENSION_TABS.length);
    setDimension(DIMENSION_TABS[next].value);
    dimensionRefs.current[next]?.focus();
  };

  return (
    <div className="overflow-hidden rounded-2xl border-[3px] border-foreground bg-white shadow-[0_4px_0_rgba(31,31,31,0.14)]">
      {/* 头部：标题 + 快照日期 + 实时标记 */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b-2 border-dashed border-foreground/15 px-4 py-3">
        <span className="text-sm font-extrabold text-foreground">学习排行榜</span>
        <span className="flex items-center gap-2 text-3xs font-semibold text-muted-foreground">
          {data?.snapshot_date ? `快照日期：${data.snapshot_date}` : "实时数据"}
          <em className="not-italic">
            {data?.source === "SNAPSHOT_OR_LIVE" && (
              <span className="rounded-full border-[2px] border-candy-green/40 bg-candy-green-soft px-2 py-0.5 font-extrabold text-success-foreground not-italic">
                ● 实时
              </span>
            )}
          </em>
        </span>
      </div>

      {/* 时间范围 Tab 组 */}
      <div className="px-4 pt-3">
        <div
          className="inline-flex flex-wrap items-center gap-1 rounded-xl border-[2px] border-foreground bg-candy-bg p-1"
          role="tablist"
          aria-label="排行时间范围"
        >
          {SCOPE_TABS.map((t, i) => (
            <button
              key={t.value}
              ref={(el) => {
                scopeRefs.current[i] = el;
              }}
              id={`ranking-scope-tab-${t.value}`}
              type="button"
              role="tab"
              aria-selected={scope === t.value}
              aria-controls={RANKINGS_PANEL_ID}
              tabIndex={scope === t.value ? 0 : -1}
              onClick={() => setScope(t.value)}
              onKeyDown={(e) => onScopeKeyDown(e, i)}
              className={cn(
                "rounded-lg px-3 py-1.5 text-sm font-bold transition-all focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-foreground",
                scope === t.value
                  ? "bg-candy-purple text-white shadow-[0_2px_0_rgba(31,31,31,0.25)]"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* 维度 Tab 组 */}
      <div className="px-4 pt-2">
        <div
          className="inline-flex flex-wrap items-center gap-1 rounded-xl border-[2px] border-foreground bg-candy-bg p-1"
          role="tablist"
          aria-label="排行维度"
        >
          {DIMENSION_TABS.map(({ value, label, Icon }, i) => (
            <button
              key={value}
              ref={(el) => {
                dimensionRefs.current[i] = el;
              }}
              id={`ranking-dimension-tab-${value}`}
              type="button"
              role="tab"
              aria-selected={dimension === value}
              aria-controls={RANKINGS_PANEL_ID}
              tabIndex={dimension === value ? 0 : -1}
              onClick={() => setDimension(value)}
              onKeyDown={(e) => onDimensionKeyDown(e, i)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-bold transition-all focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring",
                dimension === value
                  ? "bg-candy-purple text-white shadow-[0_2px_0_rgba(31,31,31,0.25)]"
                  : "text-muted-foreground hover:bg-candy-bg hover:text-foreground",
              )}
            >
              <Icon className="h-3.5 w-3.5" aria-hidden="true" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* 排行列表（tabpanel） */}
      <div id={RANKINGS_PANEL_ID} role="tabpanel" className="m-4">
        {isLoading ? (
          <div className="space-y-2" role="status" aria-label="正在加载排行榜…">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-12 animate-pulse rounded-xl border-[3px] border-border bg-candy-bg" />
            ))}
          </div>
        ) : isError ? (
          <ErrorState title="排行榜加载失败" message="网络开小差了，请稍后重试。" retry={refetch} retryLabel="重试" />
        ) : top.length === 0 ? (
          <EmptyState
            icon={<span className="text-3xl" aria-hidden="true">🏅</span>}
            title="该榜暂无数据"
            description="快去学习抢榜首吧～"
          />
        ) : (
          <div>
            <ul className="divide-y divide-dashed divide-foreground/10">
              {top.map((row) => {
                const medal = MEDAL_FOR[row.rank_no] ?? null;
                return (
                  <li
                    key={`${row.rank_no}-${row.user_id}`}
                    className={cn(
                      "flex items-center gap-3 px-2 py-2.5",
                      row.is_myself && "rounded-xl border-[2px] border-candy-purple/30 bg-candy-purple-soft px-2.5",
                    )}
                  >
                    <span
                      className={cn(
                        "grid h-8 w-8 shrink-0 place-items-center rounded-lg border-[2px] border-foreground text-sm font-extrabold tabular-nums",
                        medal ? medal.noClass : "bg-candy-bg text-muted-foreground",
                      )}
                    >
                      {medal ? (
                        <>
                          <medal.Icon className="h-4 w-4" aria-hidden="true" />
                          <span className="sr-only">第 {row.rank_no} 名</span>
                        </>
                      ) : (
                        row.rank_no
                      )}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm font-bold text-foreground">
                      {row.user_name ?? `学员 ${row.user_id}`}
                      {row.is_myself && (
                        <span className="ml-2 inline-block rounded-md bg-candy-purple px-1.5 py-0.5 text-3xs font-extrabold text-white">
                          我
                        </span>
                      )}
                    </span>
                    <span className="inline-flex items-center gap-1 text-sm font-extrabold tabular-nums text-primary">
                      <TrendingUp className="h-3.5 w-3.5" aria-hidden="true" />
                      {row.metric_value.toLocaleString()}
                      <span className="text-3xs font-semibold text-muted-foreground">{DIMENSION_UNIT[dimension]}</span>
                    </span>
                  </li>
                );
              })}
            </ul>

            {myRank && (
              <div className="mt-2 flex items-center gap-2 rounded-xl border-2 border-dashed border-foreground/20 bg-candy-bg px-3 py-2.5 text-sm">
                <span className="text-muted-foreground">📍 我的排名：</span>
                <span className="font-extrabold text-foreground">第 {myRank.rank_no} 名</span>
                <span className="ml-auto font-bold tabular-nums text-primary">
                  {myRank.metric_value.toLocaleString()} {DIMENSION_UNIT[dimension]}
                </span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}