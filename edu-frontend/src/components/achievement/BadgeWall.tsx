/**
 * BadgeWall — 徽章墙（已解锁高亮、未解锁置灰 + 解锁进度）
 *
 * 契约：GET /api/gamification/me/badges
 *   → { total, unlocked_count, next_milestone, items: BadgeItem[] }
 *   BadgeItem 含 progress_current / progress_required / progress_pct（未解锁进度）
 *
 * 满级判定（对抗 fe-task01 #5）：unlocked_count === total 时展示「已满级」，
 * 不再展示后端兜底的 next_milestone 占位文案。
 */
"use client";

import { useQuery } from "@tanstack/react-query";
import { Lock, Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";
import { getMyBadges, type BadgeItem, type BadgeRarity } from "@/lib/api/community";

/**
 * 稀有度元数据（fe-task07 收敛）：稀有度四色 → 中性 + 文字 label 补偿（普通/稀有/史诗/传说）。
 */
const RARITY_META: Record<BadgeRarity, { label: string; color: string }> = {
  COMMON: { label: "普通", color: "border-border text-muted-foreground" },
  RARE: { label: "稀有", color: "border-border text-muted-foreground" },
  EPIC: { label: "史诗", color: "border-border text-muted-foreground" },
  LEGENDARY: { label: "传说", color: "border-border text-muted-foreground" },
};

export function BadgeWall() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["gamification", "badges"] as const,
    queryFn: getMyBadges,
    staleTime: 60_000,
  });

  if (isLoading) return <BadgeWallSkeleton />;
  if (isError || !data) {
    return (
      <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-6 text-sm text-destructive-foreground">
        徽章加载失败，请稍后刷新重试。
      </div>
    );
  }

  /** 全部解锁 = 满级：展示「已满级」，忽略后端满级占位文案（对抗 fe-task01 #5） */
  const allUnlocked = data.total > 0 && data.unlocked_count >= data.total;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h3 className="text-lg font-semibold text-foreground">我的徽章</h3>
          <p className="mt-0.5 text-sm text-muted-foreground">
            已解锁 {data.unlocked_count} / {data.total} 枚
          </p>
        </div>
        {allUnlocked ? (
          <p className="inline-flex items-center gap-1.5 text-xs text-warning-foreground">
            <Sparkles className="h-3.5 w-3.5" />
            已满级：{data.total} 枚徽章全部解锁
          </p>
        ) : data.next_milestone ? (
          <p className="inline-flex items-center gap-1.5 text-xs text-warning-foreground">
            <Sparkles className="h-3.5 w-3.5" />
            下一枚：{data.next_milestone}
          </p>
        ) : null}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {data.items.map((badge) => (
          <BadgeCard key={badge.badge_code} badge={badge} />
        ))}
      </div>
    </div>
  );
}

function BadgeCard({ badge }: { badge: BadgeItem }) {
  const rarity = RARITY_META[badge.rarity] ?? RARITY_META.COMMON;
  const pct = Math.min(100, Math.max(0, Math.round(badge.progress_pct)));

  return (
    <div
      className={cn(
        "relative flex flex-col rounded-xl border p-4 transition-all",
        badge.unlocked
          ? "border-warning/40 bg-warning/10 shadow-card"
          : "border-border bg-muted/40",
      )}
    >
      {/* 图标区：未解锁置灰 + 锁角标 */}
      <div className="relative mx-auto grid h-16 w-16 place-items-center">
        <div
          className={cn(
            "grid h-14 w-14 place-items-center rounded-xl border text-3xl",
            badge.unlocked
              ? "border-warning/40 bg-card shadow-inner"
              : "border-border bg-card grayscale opacity-50",
          )}
        >
          {badge.icon_emoji || "🎖️"}
        </div>
        {!badge.unlocked && (
          <span className="absolute -bottom-1 -right-1 grid h-6 w-6 place-items-center rounded-full bg-muted-foreground text-white shadow">
            <Lock className="h-3 w-3" />
          </span>
        )}
      </div>

      <div className="mt-3 text-center">
        <div className="text-sm font-semibold text-foreground">{badge.badge_name}</div>
        <div className={cn("mt-1 inline-block rounded-full border px-2 py-0.5 text-4xs", rarity.color)}>
          {rarity.label}
        </div>
        <p className="mt-2 line-clamp-2 text-3xs leading-relaxed text-muted-foreground">
          {badge.badge_desc}
        </p>
      </div>

      {/* 进度条（未解锁） */}
      {!badge.unlocked && (
        <div className="mt-3">
          <div className="flex items-center justify-between text-4xs text-muted-foreground">
            <span>解锁进度</span>
            <span className="tabular-nums">
              {badge.progress_current}/{badge.progress_required}
            </span>
          </div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
            <div
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={pct}
              className="h-full rounded-full bg-primary"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}

      {/* 已解锁：奖励积分（正向变动 → success） */}
      {badge.unlocked && (
        <div className="mt-3 text-center text-3xs text-success-foreground">
          +{badge.reward_points} 积分 · 已解锁
        </div>
      )}
    </div>
  );
}

function BadgeWallSkeleton() {
  return (
    <div className="space-y-4">
      <div className="h-6 w-40 animate-pulse rounded bg-muted" />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-44 animate-pulse rounded-xl border border-border bg-muted/40" />
        ))}
      </div>
    </div>
  );
}
