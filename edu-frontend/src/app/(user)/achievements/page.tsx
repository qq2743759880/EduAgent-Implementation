/**
 * 成就中心（/achievements）
 *  - 徽章墙：GET /api/gamification/me/badges（未解锁置灰 + 进度）
 *  - 积分流水：GET /api/gamification/me/points（等级/进度/流水）
 *  - 排行榜：GET /api/gamification/rankings?scope&dimension（日/周/月/总）
 *  全部来自真实 API，无 MOCK。
 */
"use client";

import { useQuery } from "@tanstack/react-query";
import { Award, Coins, Trophy } from "lucide-react";

import { ProtectedRoute } from "@/lib/protected-route";
import { BadgeWall } from "@/components/achievement/BadgeWall";
import { PointLogTable } from "@/components/achievement/PointLogTable";
import { RankingTabs } from "@/components/achievement/RankingTabs";
import { getMyBadges } from "@/lib/api/community";

function AchievementsPageInner() {
  /* 徽章计数与 BadgeWall 共用同一 queryKey → React Query 去重，不产生重复请求
     （对抗 fe-task01 #6：副标题数量由 unlocked_count/total 派生，不再硬编码） */
  const { data: badgeData } = useQuery({
    queryKey: ["gamification", "badges"] as const,
    queryFn: getMyBadges,
    staleTime: 60_000,
  });

  return (
    <div className="min-h-screen bg-slate-50/70">
      <header className="relative overflow-hidden bg-gradient-to-br from-amber-500 via-orange-500 to-rose-500 text-white">
        <div className="pointer-events-none absolute inset-0 opacity-20 [background-image:radial-gradient(ellipse_at_top_left,rgba(255,255,255,0.5),transparent_55%)]" />
        <div className="mx-auto w-full max-w-5xl px-4 py-10 md:px-6">
          <div className="inline-flex items-center gap-2 rounded-full border border-white/30 bg-white/10 px-3 py-1 text-xs backdrop-blur-sm">
            <Trophy className="h-3.5 w-3.5" />
            成就中心 · 让努力被看见
          </div>
          <h1 className="mt-3 text-2xl font-bold md:text-3xl">成就与成长</h1>
          <p className="mt-2 max-w-2xl text-sm text-white/85">
            徽章记录你的每一步成长，积分见证每一次坚持，排行榜上看看你超越了谁。
          </p>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl space-y-8 px-4 py-6 md:px-6">
        <section className="rounded-2xl border bg-white p-5 md:p-6">
          <SectionTitle
            Icon={Award}
            title="徽章"
            subtitle={
              badgeData
                ? `已解锁 ${badgeData.unlocked_count} / ${badgeData.total} 枚 · 学习/成就/社交三类`
                : "学习/成就/社交三类"
            }
          />
          <div className="mt-4">
            <BadgeWall />
          </div>
        </section>

        <section className="rounded-2xl border bg-white p-5 md:p-6">
          <SectionTitle Icon={Coins} title="积分" subtitle="等级成长与积分流水" />
          <div className="mt-4">
            <PointLogTable />
          </div>
        </section>

        <section className="rounded-2xl border bg-white p-5 md:p-6">
          <SectionTitle Icon={Trophy} title="排行榜" subtitle="日 / 周 / 月 / 总榜" />
          <div className="mt-4">
            <RankingTabs />
          </div>
        </section>
      </main>
    </div>
  );
}

function SectionTitle({
  Icon,
  title,
  subtitle,
}: {
  Icon: React.ComponentType<{ className?: string }>;
  title: string;
  subtitle?: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-amber-500 to-orange-400 text-white shadow-sm">
        <Icon className="h-5 w-5" />
      </span>
      <div>
        <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
        {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
      </div>
    </div>
  );
}

export default function AchievementsPage() {
  return (
    <ProtectedRoute>
      <AchievementsPageInner />
    </ProtectedRoute>
  );
}
