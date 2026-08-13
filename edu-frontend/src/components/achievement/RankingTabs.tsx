/**
 * RankingTabs — 排行榜（日/周/月/总 × 积分/学习时长/徽章数）
 *
 * 契约：GET /api/gamification/rankings?scope=DAILY|WEEKLY|MONTHLY|ALL_TIME
 *                    &dimension=POINTS|STUDY_MIN|BADGE_COUNT&top_n=20
 *   → { top: RankingRow[], my_rank, source }；is_myself 行高亮 + 底部展示我的排名。
 *
 * 无障碍（APG Tabs 模式）：两组 tablist（时间范围/维度）均带
 * aria-controls 指向同一个排行内容面板 + roving tabindex + 方向键。
 */
"use client";

import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Award, Crown, Medal, Trophy, Timer, TrendingUp } from "lucide-react";

import { cn } from "@/lib/utils";
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

/**
 * 前三名奖牌（fe-task07：名次多色收敛——第一名保留 amber 单色豁免 text-warning-foreground（amber-700 档，a11y 修复），
 * 2/3 名 muted-foreground，orange 删除；排名由数字文本兜底）
 */
const MEDAL_FOR: Record<number, { Icon: typeof Crown; color: string }> = {
  1: { Icon: Crown, color: "text-warning-foreground" },
  2: { Icon: Medal, color: "text-muted-foreground" },
  3: { Icon: Medal, color: "text-muted-foreground" },
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

  const { data, isLoading, isError } = useQuery({
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
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-lg font-semibold">学习排行榜</h3>
        {data?.snapshot_date && (
          <span className="text-xs text-muted-foreground">
            快照日期：{data.snapshot_date}
            {/* 契约 source 固定为 SNAPSHOT_OR_LIVE（后端 schema 默认值），直接映射「实时」，无死分支（对抗 fe-task01 #9） */}
            {data.source === "SNAPSHOT_OR_LIVE" ? " · 实时" : ""}
          </span>
        )}
      </div>

      {/* 时间范围 Tab */}
      <div className="inline-flex items-center gap-1 rounded-xl bg-muted p-1" role="tablist" aria-label="排行时间范围">
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
              "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-foreground",
              scope === t.value ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 维度 Tab */}
      <div className="inline-flex items-center gap-1 rounded-lg border border-border bg-card p-0.5" role="tablist" aria-label="排行维度">
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
              "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring",
              dimension === value
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}
      </div>

      {/* 排行列表（tabpanel） */}
      <div id={RANKINGS_PANEL_ID} role="tabpanel" className="space-y-4">
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-12 animate-pulse rounded-xl border border-border bg-muted/40" />
            ))}
          </div>
        ) : isError ? (
          <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-6 text-sm text-destructive-foreground">
            排行榜加载失败，请稍后刷新重试。
          </div>
        ) : top.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
            该榜暂时还没有数据，快去学习抢榜首吧～
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            <ul className="divide-y divide-border">
              {top.map((row) => {
                const medal = MEDAL_FOR[row.rank_no] ?? null;
                return (
                  <li
                    key={`${row.rank_no}-${row.user_id}`}
                    className={cn(
                      "flex items-center gap-3 px-4 py-3",
                      row.is_myself && "bg-primary/10",
                    )}
                  >
                    <span
                      className={cn(
                        "grid h-8 w-8 shrink-0 place-items-center rounded-lg text-sm font-bold tabular-nums",
                        medal
                          ? "bg-warning/10"
                          : row.rank_no <= 10
                            ? "bg-muted text-muted-foreground"
                            : "text-muted-foreground",
                      )}
                    >
                      {medal ? (
                        <>
                          <medal.Icon className={cn("h-4 w-4", medal.color)} />
                          <span className="sr-only">第 {row.rank_no} 名</span>
                        </>
                      ) : (
                        row.rank_no
                      )}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">
                      {row.user_name ?? `学员 ${row.user_id}`}
                      {row.is_myself && (
                        <span className="ml-2 rounded bg-primary px-1.5 py-0.5 text-4xs font-semibold text-primary-foreground">
                          我
                        </span>
                      )}
                    </span>
                    <span className="inline-flex items-center gap-1 text-sm font-semibold text-primary tabular-nums">
                      <TrendingUp className="h-3.5 w-3.5" />
                      {row.metric_value.toLocaleString()}
                      <span className="text-3xs font-normal text-muted-foreground">
                        {DIMENSION_UNIT[dimension]}
                      </span>
                    </span>
                  </li>
                );
              })}
            </ul>

            {myRank && (
              <div className="border-t border-border bg-muted/40 px-4 py-3 text-sm">
                <span className="text-muted-foreground">我的排名：</span>
                <span className="font-semibold text-foreground">第 {myRank.rank_no} 名</span>
                <span className="ml-3 text-muted-foreground">
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
