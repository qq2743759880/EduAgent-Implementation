/**
 * 成就中心（/achievements）— task53 candy-playful frozen
 * 板块顺序（用户签收）：排行榜 → 积分 → 徽章墙
 *  - 排行榜：GET /api/gamification/rankings?scope&dimension（日/周/月/总 × 积分/时长/徽章数，ZSET）
 *  - 积分：GET /api/gamification/me/points（等级/总积分/进度 + 流水分页）
 *  - 徽章墙：GET /api/gamification/me/badges（已解锁高亮/未解锁置灰 + 进度）
 * 全部来自真实 API，无 MOCK。
 */
"use client";

import { Award, Coins, Trophy } from "lucide-react";

import { ProtectedRoute } from "@/lib/protected-route";
import { BadgeWall } from "@/components/achievement/BadgeWall";
import { PointOverview } from "@/components/achievement/PointOverview";
import { PointLogList } from "@/components/achievement/PointLogList";
import { RankingTabs } from "@/components/achievement/RankingTabs";

export function AchievementsPageInner() {
  return (
    <div className="min-h-screen bg-candy-bg">
      {/* Hero 成就横幅（candy 渐变） */}
      <header className="relative overflow-hidden border-b-[3px] border-foreground bg-gradient-to-r from-candy-purple via-candy-blue to-candy-green text-white">
        <div className="pointer-events-none absolute inset-0 opacity-20 [background-image:radial-gradient(ellipse_at_top_left,rgba(255,255,255,0.5),transparent_55%)]" />
        <div className="relative mx-auto w-full max-w-5xl px-4 py-8 md:px-6">
          <span className="inline-flex items-center gap-1.5 rounded-full border-[2px] border-white/40 bg-white/15 px-3 py-1 text-xs font-extrabold backdrop-blur-sm">
            🏆 成就中心 · 让努力被看见
          </span>
          <h1 className="mt-3 text-2xl font-extrabold md:text-3xl">成就与成长</h1>
          <p className="mt-2 max-w-2xl text-sm text-white/90">
            徽章记录你的每一步成长，积分见证每一次坚持，排行榜上看看你超越了谁。
          </p>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl space-y-6 px-4 py-6 md:px-6">
        {/* 1. 排行榜 */}
        <section aria-labelledby="rank-sec">
          <SectionTitle Icon={Trophy} title="排行榜" subtitle="日 / 周 / 月 / 总榜 · 积分 / 学习时长 / 徽章数 · 实时数据" id="rank-sec" />
          <div className="mt-3">
            <RankingTabs />
          </div>
        </section>

        {/* 2. 积分 */}
        <section aria-labelledby="points-sec">
          <SectionTitle Icon={Coins} title="积分" subtitle="等级成长与积分流水" id="points-sec" />
          <div className="mt-3 space-y-3">
            <PointOverview />
            <PointLogList />
          </div>
        </section>

        {/* 3. 徽章墙 */}
        <section aria-labelledby="badge-sec">
          <SectionTitle Icon={Award} title="徽章" subtitle="学习 / 成就 / 社交三类徽章" id="badge-sec" />
          <div className="mt-3">
            <BadgeWall />
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
  id,
}: {
  Icon: React.ComponentType<{ className?: string }>;
  title: string;
  subtitle?: string;
  id?: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="grid h-10 w-10 place-items-center rounded-xl border-[3px] border-foreground bg-candy-yellow shadow-[0_3px_0_rgba(31,31,31,0.18)]">
        <Icon className="h-5 w-5 text-foreground" aria-hidden="true" />
      </span>
      <div>
        <h2 id={id} className="text-lg font-extrabold text-foreground">{title}</h2>
        {subtitle && <p className="text-xs font-semibold text-muted-foreground">{subtitle}</p>}
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