"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  AlertCircle,
  BookOpenCheck,
  Flame,
  GraduationCap,
  LayoutGrid,
  RotateCw,
  Settings2,
  Sparkles,
  UserRoundCog,
  Waypoints,
} from "lucide-react";

import AbilityRadarChart from "@/components/dashboard/AbilityRadarChart";
import BadgeWallGrid from "@/components/dashboard/BadgeWallGrid";
import KpiCard, { type KpiDelta } from "@/components/dashboard/KpiCard";
import PointCard from "@/components/dashboard/PointCard";
import ProgressTrendChart from "@/components/dashboard/ProgressTrendChart";
import RankList, { type RankRange } from "@/components/dashboard/RankList";
import StreakBadge from "@/components/dashboard/StreakBadge";
import {
  RANGE_SCOPE,
  buildRankSlice,
  deriveAbilityRadar,
  deriveDashboardKpis,
  deriveStreakLast7,
  getMySubjectPreferences,
  getProgressCourses,
  getProgressDashboard,
  mapBadgesToWall,
  mapPointsToCard,
  toProgressTrend,
  type DashboardKpis,
} from "@/lib/api/dashboard";
import { getMyBadges, getMyPoints, getRankings } from "@/lib/api/community";
import { useAuthStore } from "@/lib/auth-client";
import { ProtectedRoute } from "@/lib/protected-route";
import { cn } from "@/lib/utils";

/* ---------- KPI delta 文案（页面级格式化，数值来自 deriveDashboardKpis 派生） ---------- */

function minutesDelta(k: DashboardKpis): KpiDelta {
  // 卡 1：今日时长 vs 昨日
  if (k.yesterdayMinutes == null) return { direction: "flat", value: "暂无昨日数据" };
  if (k.minutesToday > k.yesterdayMinutes)
    return { direction: "up", value: `较昨日 +${k.minutesToday - k.yesterdayMinutes} 分钟` };
  if (k.minutesToday < k.yesterdayMinutes)
    return { direction: "down", value: `较昨日 ${k.minutesToday - k.yesterdayMinutes} 分钟` };
  return { direction: "flat", value: "较昨日持平" };
}

function exercisesDelta(k: DashboardKpis): KpiDelta {
  // 卡 2：累计正确率（attempted=0 → 「暂无数据」中性，除零保护在派生层完成）
  if (k.accuracyPct == null) return { direction: "flat", value: "暂无数据" };
  return { direction: "up", value: `正确率 ${k.accuracyPct}%` };
}

function streakDelta(k: DashboardKpis): KpiDelta {
  // 卡 4：近 7 天活跃天数
  return {
    direction: k.last7ActiveDays >= 4 ? "up" : k.last7ActiveDays <= 1 ? "down" : "flat",
    value: `近 7 天活跃 ${k.last7ActiveDays} 天`,
  };
}

/* ---------- 卡片级错误态（页面统一注入，tokens 语义 class） ---------- */

function DataErrorCard({
  message,
  onRetry,
  className,
}: {
  message: string;
  onRetry: () => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border border-destructive/30 bg-destructive/10 text-destructive flex flex-col items-center justify-center gap-2 p-6 text-center",
        className,
      )}
    >
      <AlertCircle className="h-6 w-6 opacity-80" aria-hidden="true" />
      <p className="text-sm font-medium">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="inline-flex items-center gap-1.5 h-8 px-3 rounded-full bg-primary text-primary-foreground text-xs font-medium hover:opacity-90"
      >
        <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
        重试
      </button>
    </div>
  );
}

/* ---------- Page 组件 ---------- */

function DashboardPageInner() {
  const me = useAuthStore((s) => s.me);
  const nickname = me?.nickname || "同学";

  const [range, setRange] = useState<RankRange>("day");

  // 1) 趋势（KPI / 打卡 / 趋势图共用原始 DashboardOut）
  const trendQuery = useQuery({
    queryKey: ["dashboard", "trend"],
    queryFn: () => getProgressDashboard(14),
    staleTime: 60_000,
  });

  // 2) 课程进度（KPI 派生源 2：coursesInProgress）
  const coursesQuery = useQuery({
    queryKey: ["dashboard", "courses"],
    queryFn: () => getProgressCourses(),
    staleTime: 60_000,
  });

  // 3) 雷达（queryFn 内 Promise.all + 派生，单一消费方）
  const radarQuery = useQuery({
    queryKey: ["dashboard", "ability-radar"],
    queryFn: async () => {
      const [dash, prefs] = await Promise.all([getProgressDashboard(14), getMySubjectPreferences()]);
      // 派生自 GET /api/progress/dashboard.overall_correct_rate + GET /api/users/me/profile.subject_preferences
      return deriveAbilityRadar(dash.overall_correct_rate, prefs);
    },
    staleTime: 60_000,
  });

  // 4) 徽章墙
  const badgesQuery = useQuery({
    queryKey: ["dashboard", "badges"],
    queryFn: async () => {
      // 派生自 GET /api/gamification/me/badges
      const resp = await getMyBadges();
      return mapBadgesToWall(resp);
    },
    staleTime: 60_000,
  });

  // 5) 积分卡
  const pointsQuery = useQuery({
    queryKey: ["dashboard", "points"],
    queryFn: async () => {
      // 派生自 GET /api/gamification/me/points
      const resp = await getMyPoints(1, 20);
      return mapPointsToCard(resp);
    },
    staleTime: 60_000,
  });

  // 6) 排行榜（key 含 range，切 tab 触发 refetch）
  const rankQuery = useQuery({
    queryKey: ["dashboard", "rank", range],
    queryFn: async () => {
      // 派生自 GET /api/gamification/rankings
      const resp = await getRankings(RANGE_SCOPE[range], "POINTS", 10);
      const slice = buildRankSlice(resp, range);
      const data: Parameters<typeof RankList>[0]["data"] = { [range]: slice.list };
      if (slice.myRank) data.myRank = { [range]: slice.myRank };
      return data;
    },
    staleTime: 60_000,
  });

  // 派生：趋势点（翻转成时间正序，末位 = 今天）
  const trendPoints = useMemo(
    () => (trendQuery.data ? toProgressTrend(trendQuery.data) : []),
    [trendQuery.data],
  );

  // 派生：KPI 4 卡（依赖 trend + courses 两 query）
  const kpis = useMemo(() => {
    if (!trendQuery.data || !coursesQuery.data) return null;
    // 派生自 GET /api/progress/dashboard + GET /api/progress/courses
    return deriveDashboardKpis(trendQuery.data, coursesQuery.data);
  }, [trendQuery.data, coursesQuery.data]);

  // 派生：连续打卡（随 trend 同源）
  const streak = useMemo(
    () => (trendQuery.data ? deriveStreakLast7(trendQuery.data) : null),
    [trendQuery.data],
  );

  const kpiSourceLoading = trendQuery.isLoading || coursesQuery.isLoading;
  const kpiSourceError =
    (trendQuery.isError && !trendQuery.data) || (coursesQuery.isError && !coursesQuery.data);

  return (
    <div className="w-full max-w-7xl mx-auto space-y-6">
      {/* 顶部欢迎条 */}
      <section className="flex items-start justify-between gap-4 flex-wrap">
        <div className="space-y-1">
          <div className="inline-flex items-center gap-2 rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700 border border-indigo-100">
            <Sparkles className="h-3.5 w-3.5" />
            今天也要和 EduAgent 一起进步呀 ✨
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            你好，{nickname}
          </h1>
          <p className="text-sm text-slate-500 max-w-xl leading-6">
            这里是你的学习仪表盘：随时查看学习时长、学科能力、积分与排行榜，让每一次努力都能被看见。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/me"
            className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-sm text-slate-700 shadow-sm"
          >
            <UserRoundCog className="h-4 w-4" />
            个人中心
          </Link>
          <Link
            href="/me?tab=preferences"
            className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-xl border border-indigo-200 bg-indigo-600 hover:bg-indigo-700 text-sm text-white shadow-sm"
          >
            <Settings2 className="h-4 w-4" />
            调整偏好
          </Link>
        </div>
      </section>

      {/* KPI 4 卡（任一派生源错误 → 整区错误卡，不显示 0 兜底） */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {kpiSourceError ? (
          <DataErrorCard
            className="sm:col-span-2 lg:col-span-4 min-h-[128px]"
            message="学习数据加载失败"
            onRetry={() => {
              trendQuery.refetch();
              coursesQuery.refetch();
            }}
          />
        ) : (
          <>
            <KpiCard
              accent="indigo"
              title="今日学习时长"
              value={`${kpis?.minutesToday ?? 0} 分钟`}
              delta={kpis ? minutesDelta(kpis) : undefined}
              icon={<GraduationCap className="h-5 w-5" />}
              loading={kpiSourceLoading || !kpis}
            />
            <KpiCard
              accent="emerald"
              title="今日练习题"
              value={`${kpis?.exercisesToday ?? 0} 道`}
              delta={kpis ? exercisesDelta(kpis) : undefined}
              icon={<BookOpenCheck className="h-5 w-5" />}
              loading={kpiSourceLoading || !kpis}
            />
            <KpiCard
              accent="amber"
              title="进行中课程"
              value={`${kpis?.coursesInProgress ?? 0} 门`}
              delta={{ direction: "flat", value: "建议一次 focus 2 门" }}
              icon={<LayoutGrid className="h-5 w-5" />}
              loading={kpiSourceLoading || !kpis}
            />
            <KpiCard
              accent="violet"
              title="连续打卡"
              value={`${kpis?.streakDays ?? 0} 天`}
              delta={kpis ? streakDelta(kpis) : undefined}
              icon={<Flame className="h-5 w-5" />}
              loading={kpiSourceLoading || !kpis}
            />
          </>
        )}
      </section>

      {/* 快捷入口 CTA：串联主要页面 */}
      <section className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <Link
          href="/courses"
          className="group rounded-xl border border-slate-200 bg-white/80 hover:bg-white shadow-sm hover:shadow hover:border-indigo-200 p-4 flex flex-col gap-2 transition-all"
        >
          <span className="h-9 w-9 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center group-hover:scale-105 transition">
            <BookOpenCheck className="h-5 w-5" />
          </span>
          <span className="text-sm font-semibold text-slate-800">课程中心</span>
          <span className="text-xs text-slate-500 line-clamp-1">全部课程 · 名师合集</span>
        </Link>
        <Link
          href="/my-courses"
          className="group rounded-xl border border-slate-200 bg-white/80 hover:bg-white shadow-sm hover:shadow hover:border-indigo-200 p-4 flex flex-col gap-2 transition-all"
        >
          <span className="h-9 w-9 rounded-lg bg-sky-50 text-sky-600 flex items-center justify-center group-hover:scale-105 transition">
            <GraduationCap className="h-5 w-5" />
          </span>
          <span className="text-sm font-semibold text-slate-800">我的课程</span>
          <span className="text-xs text-slate-500 line-clamp-1">继续上次学习</span>
        </Link>
        <Link
          href="/practice/wrong-book"
          className="group rounded-xl border border-slate-200 bg-white/80 hover:bg-white shadow-sm hover:shadow hover:border-indigo-200 p-4 flex flex-col gap-2 transition-all"
        >
          <span className="h-9 w-9 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center group-hover:scale-105 transition">
            <Flame className="h-5 w-5" />
          </span>
          <span className="text-sm font-semibold text-slate-800">错题本</span>
          <span className="text-xs text-slate-500 line-clamp-1">消灭薄弱点</span>
        </Link>
        <Link
          href="/practice/vocab"
          className="group rounded-xl border border-slate-200 bg-white/80 hover:bg-white shadow-sm hover:shadow hover:border-indigo-200 p-4 flex flex-col gap-2 transition-all"
        >
          <span className="h-9 w-9 rounded-lg bg-violet-50 text-violet-600 flex items-center justify-center group-hover:scale-105 transition">
            <Waypoints className="h-5 w-5" />
          </span>
          <span className="text-sm font-semibold text-slate-800">单词本</span>
          <span className="text-xs text-slate-500 line-clamp-1">每日单词打卡</span>
        </Link>
        <Link
          href="/chat"
          className="group rounded-xl border border-slate-200 bg-white/80 hover:bg-white shadow-sm hover:shadow hover:border-indigo-200 p-4 flex flex-col gap-2 transition-all sm:col-span-1 col-span-2"
        >
          <span className="h-9 w-9 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center group-hover:scale-105 transition">
            <Sparkles className="h-5 w-5" />
          </span>
          <span className="text-sm font-semibold text-slate-800">AI 问答</span>
          <span className="text-xs text-slate-500 line-clamp-1">随时问老师</span>
        </Link>
      </section>

      {/* 第 2 行：连续打卡 + 积分卡 */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {trendQuery.isError && !trendQuery.data ? (
          <DataErrorCard
            className="lg:col-span-1"
            message="学习数据加载失败"
            onRetry={() => trendQuery.refetch()}
          />
        ) : !streak ? (
          <div className="lg:col-span-1 animate-pulse bg-muted rounded-xl h-48" aria-hidden="true" />
        ) : (
          <StreakBadge
            className="lg:col-span-1"
            streakDays={streak.streakDays}
            last7Days={streak.last7Days}
          />
        )}
        {pointsQuery.isError && !pointsQuery.data ? (
          <DataErrorCard
            className="lg:col-span-2"
            message="积分数据加载失败"
            onRetry={() => pointsQuery.refetch()}
          />
        ) : (
          <PointCard
            className="lg:col-span-2"
            total={pointsQuery.data?.total ?? 0}
            todayGain={pointsQuery.data?.todayGain ?? 0}
            recentGains={pointsQuery.data?.recentGains ?? []}
            loading={pointsQuery.isLoading}
          />
        )}
      </section>

      {/* 第 3 行：折线 + 雷达 */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <ProgressTrendChart
          className="lg:col-span-2"
          data={trendPoints}
          loading={trendQuery.isLoading}
          empty={!!trendQuery.data && trendPoints.length === 0}
          error={trendQuery.isError && !trendQuery.data}
          onRetry={() => trendQuery.refetch()}
          description="统计每天学习时长，单位分钟。"
        />
        <AbilityRadarChart
          className="lg:col-span-1"
          series={radarQuery.data ?? []}
          loading={radarQuery.isLoading}
          empty={!!radarQuery.data && radarQuery.data.length === 0}
          error={radarQuery.isError && !radarQuery.data}
          onRetry={() => radarQuery.refetch()}
        />
      </section>

      {/* 第 4 行：徽章墙 + 排行榜 */}
      <section className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {badgesQuery.isError && !badgesQuery.data ? (
          <DataErrorCard
            className="xl:col-span-2"
            message="徽章数据加载失败"
            onRetry={() => badgesQuery.refetch()}
          />
        ) : (
          <BadgeWallGrid
            className="xl:col-span-2"
            badges={badgesQuery.data ?? []}
            minCols={5}
            description={badgesQuery.isLoading ? "加载中…" : undefined}
          />
        )}
        {rankQuery.isError && !rankQuery.data ? (
          <DataErrorCard
            className="xl:col-span-1"
            message="排行榜加载失败"
            onRetry={() => rankQuery.refetch()}
          />
        ) : (
          <RankList
            className="xl:col-span-1"
            data={rankQuery.data ?? {}}
            loading={rankQuery.isLoading}
            topN={10}
            defaultRange={range}
            onRangeChange={setRange}
          />
        )}
      </section>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <ProtectedRoute>
      <DashboardPageInner />
    </ProtectedRoute>
  );
}
