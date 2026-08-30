/**
 * BadgeWall — 徽章墙（candy-playful frozen，task53 对齐 approved achievements.html）
 * - 已解锁：糖果绿 soft 高亮 + 稀有度四色（普通灰/稀有蓝/史诗紫/传说金）+「+N 积分 · 已解锁」
 * - 未解锁：置灰 grayscale + 右下 🔒 锁角标 + 解锁进度条（progress_current/required + progress_pct）
 * - 满级判定（对抗 fe-task01 #5）：unlocked_count === total 时展示「已满级」，忽略后端 next_milestone 占位
 * - 三态：loading（徽章骨架）/ error（ErrorState + 重试，不吞错）/ success（墙）
 * 契约：GET /api/gamification/me/badges → { total, unlocked_count, next_milestone, items: BadgeItem[] }
 */
"use client";

import { useQuery } from "@tanstack/react-query";
import { Lock, Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";
import { ErrorState } from "@/components/ui/error-state";
import { getMyBadges, type BadgeItem, type BadgeRarity } from "@/lib/api/community";

/** 稀有度四色（fe-task07 收敛 + task53 candy 化）：稀有度由色相 + 文字 label 双载体标识 */
const RARITY_META: Record<BadgeRarity, { label: string; chip: string }> = {
  COMMON: { label: "普通", chip: "border-border bg-muted text-muted-foreground" },
  RARE: { label: "稀有", chip: "border-candy-blue bg-candy-blue text-white" },
  EPIC: { label: "史诗", chip: "border-candy-purple bg-candy-purple text-white" },
  LEGENDARY: { label: "传说", chip: "border-candy-yellow bg-candy-yellow text-foreground" },
};

/** 3D 实底阴影：以糖果绿为底的深档（对齐 ReactButtons 约定） */
const GREEN_3D = "shadow-[0_4px_0_color-mix(in_oklch,var(--candy-green),black_30%)]";

export function BadgeWall() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["gamification", "badges"] as const,
    queryFn: getMyBadges,
    staleTime: 60_000,
  });

  /* 首屏三态：加载 → 骨架；错误 → ErrorState + 重试；success 已解锁数据 */
  if (isLoading && !data) return <BadgeWallSkeleton />;
  if (isError && !data) {
    return <ErrorState title="徽章加载失败" message="网络开小差了，请稍后重试。" retry={refetch} retryLabel="重试" />;
  }
  if (!data) return null;

  /** 满级判定：全部解锁 → 忽略后端占位文案 */
  const allUnlocked = data.total > 0 && data.unlocked_count >= data.total;

  return (
    <div className="rounded-2xl border-[3px] border-foreground bg-white shadow-[0_4px_0_rgba(31,31,31,0.14)]">
      <div className="flex flex-wrap items-center gap-2 border-b-2 border-dashed border-foreground/15 p-4">
        <span className="inline-flex items-center gap-1.5 rounded-full border-[2px] border-candy-green/40 bg-candy-green-soft px-3 py-1 text-xs font-extrabold text-success-foreground">
          🎖 已解锁 {data.unlocked_count} / {data.total} 枚
        </span>
        {allUnlocked ? (
          <span className="inline-flex items-center gap-1.5 rounded-full border-[2px] border-candy-green/40 bg-candy-green-soft px-3 py-1 text-xs font-extrabold text-success-foreground">
            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
            已满级：{data.total} 枚徽章全部解锁
          </span>
        ) : data.next_milestone ? (
          <span className="inline-flex items-center gap-1.5 rounded-full border-[2px] border-candy-purple/35 bg-candy-purple-soft px-3 py-1 text-xs font-extrabold text-primary">
            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
            下一枚：{data.next_milestone}
          </span>
        ) : null}
      </div>

      <div className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-3 lg:grid-cols-4">
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
        "relative flex flex-col rounded-2xl border-[3px] border-foreground p-3 transition-transform hover:-translate-y-0.5",
        badge.unlocked ? cn("bg-candy-green-soft", GREEN_3D) : "bg-candy-bg opacity-80",
      )}
    >
      {/* 图标区：未解锁置灰 + 锁角标 */}
      <div className="relative mx-auto grid h-16 w-16 place-items-center">
        <div
          className={cn(
            "grid h-14 w-14 place-items-center rounded-xl border-[2px] border-foreground text-3xl",
            badge.unlocked ? "bg-white" : "bg-white grayscale opacity-50",
          )}
        >
          <span aria-hidden="true">{badge.icon_emoji || "🎖️"}</span>
        </div>
        {!badge.unlocked && (
          <span className="absolute -bottom-1 -right-1 grid h-6 w-6 place-items-center rounded-full bg-muted-foreground text-white shadow" aria-hidden="true">
            <Lock className="h-3 w-3" />
          </span>
        )}
      </div>

      <div className="mt-3 text-center">
        <div className="text-sm font-extrabold text-foreground">{badge.badge_name}</div>
        <span className={cn("mt-1 inline-block rounded-full border-[2px] px-2 py-0.5 text-3xs font-extrabold", rarity.chip)}>
          {rarity.label}
        </span>
        <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-muted-foreground">{badge.badge_desc}</p>
      </div>

      {/* 未解锁：解锁进度条 */}
      {!badge.unlocked && (
        <div className="mt-3">
          <div className="flex items-center justify-between text-3xs font-bold text-muted-foreground">
            <span>解锁进度</span>
            <span className="tabular-nums">
              {badge.progress_current}/{badge.progress_required}
            </span>
          </div>
          <div
            className="mt-1 h-2 overflow-hidden rounded-full border border-black/10 bg-white"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={pct}
            aria-label={`${badge.badge_name} 解锁进度`}
          >
            <div className="h-full rounded-full bg-candy-green" style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}

      {/* 已解锁：奖励积分 */}
      {badge.unlocked && (
        <div className="mt-3 text-center text-3xs font-extrabold text-success-foreground">
          +{badge.reward_points} 积分 · 已解锁
        </div>
      )}
    </div>
  );
}

function BadgeWallSkeleton() {
  return (
    <div className="rounded-2xl border-[3px] border-border bg-white p-4" role="status" aria-label="正在加载徽章…">
      <div className="h-6 w-48 animate-pulse rounded-lg bg-muted" />
      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-44 animate-pulse rounded-2xl border-[3px] border-border bg-muted/40" />
        ))}
      </div>
    </div>
  );
}