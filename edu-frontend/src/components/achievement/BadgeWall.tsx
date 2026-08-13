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

const RARITY_META: Record<BadgeRarity, { label: string; color: string }> = {
  COMMON: { label: "普通", color: "border-slate-300 text-slate-600" },
  RARE: { label: "稀有", color: "border-sky-300 text-sky-600" },
  EPIC: { label: "史诗", color: "border-violet-300 text-violet-600" },
  LEGENDARY: { label: "传说", color: "border-amber-300 text-amber-600" },
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
      <div className="rounded-2xl border border-rose-200 bg-rose-50/50 p-6 text-sm text-rose-700">
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
          <h3 className="text-lg font-semibold">我的徽章</h3>
          <p className="mt-0.5 text-sm text-muted-foreground">
            已解锁 {data.unlocked_count} / {data.total} 枚
          </p>
        </div>
        {allUnlocked ? (
          <p className="inline-flex items-center gap-1.5 text-xs text-amber-700">
            <Sparkles className="h-3.5 w-3.5" />
            已满级：{data.total} 枚徽章全部解锁
          </p>
        ) : data.next_milestone ? (
          <p className="inline-flex items-center gap-1.5 text-xs text-amber-700">
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
        "relative flex flex-col rounded-2xl border p-4 transition-all",
        badge.unlocked
          ? "border-amber-200 bg-gradient-to-br from-amber-50/80 to-white shadow-sm"
          : "border-slate-200 bg-slate-50/60",
      )}
    >
      {/* 图标区：未解锁置灰 + 锁角标 */}
      <div className="relative mx-auto grid h-16 w-16 place-items-center">
        <div
          className={cn(
            "grid h-14 w-14 place-items-center rounded-2xl border text-3xl",
            badge.unlocked
              ? "border-amber-200 bg-white shadow-inner"
              : "border-slate-200 bg-white grayscale opacity-50",
          )}
        >
          {badge.icon_emoji || "🎖️"}
        </div>
        {!badge.unlocked && (
          <span className="absolute -bottom-1 -right-1 grid h-6 w-6 place-items-center rounded-full bg-slate-600 text-white shadow">
            <Lock className="h-3 w-3" />
          </span>
        )}
      </div>

      <div className="mt-3 text-center">
        <div className="text-sm font-semibold text-slate-900">{badge.badge_name}</div>
        <div className={cn("mt-1 inline-block rounded-full border px-2 py-0.5 text-[10px]", rarity.color)}>
          {rarity.label}
        </div>
        <p className="mt-2 line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">
          {badge.badge_desc}
        </p>
      </div>

      {/* 进度条（未解锁） */}
      {!badge.unlocked && (
        <div className="mt-3">
          <div className="flex items-center justify-between text-[10px] text-muted-foreground">
            <span>解锁进度</span>
            <span className="tabular-nums">
              {badge.progress_current}/{badge.progress_required}
            </span>
          </div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-200">
            <div
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={pct}
              className="h-full rounded-full bg-gradient-to-r from-primary/70 to-primary"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}

      {/* 已解锁：奖励积分 */}
      {badge.unlocked && (
        <div className="mt-3 text-center text-[11px] text-amber-700">
          +{badge.reward_points} 积分 · 已解锁
        </div>
      )}
    </div>
  );
}

function BadgeWallSkeleton() {
  return (
    <div className="space-y-4">
      <div className="h-6 w-40 animate-pulse rounded bg-slate-100" />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-44 animate-pulse rounded-2xl border bg-white" />
        ))}
      </div>
    </div>
  );
}
