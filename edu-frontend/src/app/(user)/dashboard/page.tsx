"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  BookOpenCheck,
  Flame,
  GraduationCap,
  LayoutGrid,
  Settings2,
  Sparkles,
  UserRoundCog,
  Waypoints,
} from "lucide-react";

import AbilityRadarChart from "@/components/dashboard/AbilityRadarChart";
import BadgeWallGrid, { type BadgeItem } from "@/components/dashboard/BadgeWallGrid";
import KpiCard from "@/components/dashboard/KpiCard";
import PointCard, { type PointGainItem } from "@/components/dashboard/PointCard";
import ProgressTrendChart, {
  type ProgressTrendPoint,
} from "@/components/dashboard/ProgressTrendChart";
import RankList, { type RankEntry, type RankRange } from "@/components/dashboard/RankList";
import StreakBadge from "@/components/dashboard/StreakBadge";
import { useAuthStore } from "@/lib/auth-client";
import { ProtectedRoute } from "@/lib/protected-route";
import {
  SUBJECT_LABELS,
  SUBJECT_OPTIONS,
  type SubjectKey,
} from "@/lib/validators/profile-schemas";

/* ---------- Mock 数据（后端未返回时 placeholderData，UI 完整可见） ---------- */

function daysAgoLabel(offset: number): string {
  const d = new Date();
  d.setDate(d.getDate() - (13 - offset));
  return `${(d.getMonth() + 1).toString().padStart(2, "0")}/${d.getDate().toString().padStart(2, "0")}`;
}

const MOCK_TREND: ProgressTrendPoint[] = Array.from({ length: 14 }).map((_, i) => ({
  dateLabel: daysAgoLabel(i),
  minutes: [25, 40, 60, 35, 55, 80, 45, 65, 50, 70, 90, 55, 75, 62][i] ?? 45,
  practiceMinutes: [10, 15, 20, 12, 25, 40, 18, 30, 22, 28, 45, 20, 35, 30][i] ?? 18,
}));

const MOCK_RADAR_SELF = {
  name: "我的能力",
  values: [78, 66, 82, 70, 60] as number[],
  color: "#6366f1",
  opacity: 0.24,
};

const MOCK_RADAR_PEER = {
  name: "全班平均",
  values: [65, 55, 68, 62, 52] as number[],
  color: "#10b981",
  opacity: 0.16,
};

const MOCK_BADGES: BadgeItem[] = [
  {
    key: "streak-7",
    name: "小试牛刀",
    description: "连续 7 天登录学习，开启你的学习旅程。",
    unlockCondition: "连续 7 天学习",
    category: "streak",
    earned: true,
    earnedAt: "03-12",
    icon: <Flame className="h-6 w-6" />,
  },
  {
    key: "streak-30",
    name: "坚持不懈",
    description: "连续 30 天学习，养成每日学习习惯。",
    unlockCondition: "连续 30 天学习（还需 17 天）",
    category: "streak",
    earned: false,
    icon: <Sparkles className="h-6 w-6" />,
  },
  {
    key: "english-star",
    name: "英语新星",
    description: "英语维度累计答对 100 道题。",
    unlockCondition: "英语练习题正确率达到 80%",
    category: "subject",
    earned: true,
    earnedAt: "03-15",
  },
  {
    key: "coding-first",
    name: "编程初体验",
    description: "完成第一个编程项目并提交。",
    unlockCondition: "完成 1 个编程实战任务",
    category: "subject",
    earned: true,
    earnedAt: "03-10",
  },
  {
    key: "math-master",
    name: "数学能手",
    description: "完成全部小学数学基础模块。",
    unlockCondition: "完成 8 个数学章节",
    category: "subject",
    earned: false,
  },
  {
    key: "chinese-reader",
    name: "语文小读者",
    description: "累计阅读 10 篇语文材料。",
    unlockCondition: "完成 10 篇阅读理解",
    category: "subject",
    earned: false,
  },
  {
    key: "physics-lab",
    name: "物理探索者",
    description: "完成 5 个物理实验或模拟任务。",
    unlockCondition: "完成 5 个物理实验模块",
    category: "subject",
    earned: false,
  },
  {
    key: "achiever-1000",
    name: "积分破千",
    description: "累计积分数突破 1000 点。",
    unlockCondition: "积分达到 1000",
    category: "achievement",
    earned: true,
    earnedAt: "03-18",
  },
  {
    key: "share-first",
    name: "乐于分享",
    description: "第一次分享学习笔记给同学。",
    unlockCondition: "分享 1 份学习笔记",
    category: "social",
    earned: true,
    earnedAt: "03-16",
  },
  {
    key: "explore-agent",
    name: "AI 探索家",
    description: "体验 5 个不同的 AI 学习工具。",
    unlockCondition: "体验 5 个 MCP 工具",
    category: "explore",
    earned: false,
  },
];

const MOCK_GAINS: PointGainItem[] = [
  { key: "g1", title: "完成英语「时态 1」章节", points: 30, at: "09:10", kind: "study" },
  { key: "g2", title: "解锁徽章「小试牛刀」", points: 50, at: "09:25", kind: "badge" },
  { key: "g3", title: "编程实战：小试 AI 助手", points: 80, at: "11:02", kind: "study" },
  { key: "g4", title: "分享笔记给同桌", points: 20, at: "12:40", kind: "share" },
  { key: "g5", title: "首次体验 MCP 工具：解题顾问", points: 15, at: "19:55", kind: "explore" },
];

function buildRankList(): RankEntry[] {
  const names = [
    "星辰与你",
    "Kira",
    "小明同学",
    "CodeHunter",
    "学霸养成中",
    "Echo",
    "清风徐来",
    "物理小王子",
    "MathWhiz",
    "墨言",
    "Sunny",
    "Lumos",
  ];
  return names.map((n, i) => ({
    rank: i + 1,
    nickname: n,
    score: 3200 - i * 180,
    tag: i === 2 ? "本周 +5" : i === 6 ? "本周 +2" : undefined,
  }));
}

const ALL_RANGE_LIST = buildRankList();

/* ---------- Page 组件 ---------- */

function DashboardPageInner() {
  const me = useAuthStore((s) => s.me);
  const anyMe = me as (UserInfoExtended | null) | undefined;
  const nickname = anyMe?.nickname || anyMe?.name || "同学";

  const subjects = useMemo<SubjectKey[]>(() => {
    const raw = anyMe?.subjectPreferences;
    if (!Array.isArray(raw)) return [...SUBJECT_OPTIONS] as SubjectKey[];
    const filtered = raw.filter((x): x is SubjectKey => typeof x === "string");
    return filtered.length ? filtered : ([...SUBJECT_OPTIONS] as SubjectKey[]);
  }, [anyMe]);

  const { data: trend, isLoading: trendLoading } = useQuery({
    queryKey: ["dashboard", "trend"],
    queryFn: async () => {
      // TODO: 接入后端 /dashboard/progress-trend
      await new Promise((r) => setTimeout(r, 400));
      return MOCK_TREND;
    },
    placeholderData: MOCK_TREND,
    staleTime: 60_000,
  });

  const { data: radar, isLoading: radarLoading } = useQuery({
    queryKey: ["dashboard", "ability-radar"],
    queryFn: async () => {
      // TODO: 接入后端 /dashboard/ability-radar
      await new Promise((r) => setTimeout(r, 400));
      return [MOCK_RADAR_SELF, MOCK_RADAR_PEER];
    },
    placeholderData: [MOCK_RADAR_SELF, MOCK_RADAR_PEER],
    staleTime: 60_000,
  });

  const { data: badges, isLoading: badgesLoading } = useQuery({
    queryKey: ["dashboard", "badges"],
    queryFn: async () => {
      // TODO: 接入后端 /badges/my
      await new Promise((r) => setTimeout(r, 400));
      return MOCK_BADGES;
    },
    placeholderData: MOCK_BADGES,
    staleTime: 60_000,
  });

  const { data: points, isLoading: pointsLoading } = useQuery({
    queryKey: ["dashboard", "points"],
    queryFn: async () => {
      // TODO: 接入后端 /points/summary
      await new Promise((r) => setTimeout(r, 400));
      const base = typeof anyMe?.points === "number" ? anyMe.points : 1480;
      return {
        total: base,
        todayGain: 195,
        recentGains: MOCK_GAINS,
      };
    },
    placeholderData: {
      total: typeof anyMe?.points === "number" ? anyMe.points : 1480,
      todayGain: 195,
      recentGains: MOCK_GAINS,
    },
    staleTime: 30_000,
  });

  const { data: rankData, isLoading: rankLoading } = useQuery({
    queryKey: ["dashboard", "rank"],
    queryFn: async () => {
      // TODO: 接入后端 /dashboard/rank?range=
      await new Promise((r) => setTimeout(r, 400));
      const ranges: RankRange[] = ["day", "week", "month"];
      const out: Parameters<typeof RankList>[0]["data"] = {};
      for (const r of ranges) {
        out[r] = ALL_RANGE_LIST.map((row) => ({ ...row, score: row.score + (r === "day" ? 0 : r === "week" ? 1200 : 5000) }));
      }
      out.myRank = {
        day: {
          rank: 12,
          nickname: nickname as string,
          avatar: (anyMe?.avatar as string | null) || null,
          score: 2480,
          mine: true,
          totalPlayers: 128,
        },
        week: {
          rank: 18,
          nickname: nickname as string,
          avatar: (anyMe?.avatar as string | null) || null,
          score: 8600,
          mine: true,
          totalPlayers: 128,
        },
        month: {
          rank: 24,
          nickname: nickname as string,
          avatar: (anyMe?.avatar as string | null) || null,
          score: 32000,
          mine: true,
          totalPlayers: 128,
        },
      };
      return out;
    },
    placeholderData: (() => {
      const ranges: RankRange[] = ["day", "week", "month"];
      const out: Parameters<typeof RankList>[0]["data"] = {};
      for (const r of ranges) {
        out[r] = ALL_RANGE_LIST.map((row) => ({
          ...row,
          score: row.score + (r === "day" ? 0 : r === "week" ? 1200 : 5000),
        }));
      }
      out.myRank = {
        day: { rank: 12, nickname: nickname as string, avatar: (anyMe?.avatar as string | null) || null, score: 2480, mine: true, totalPlayers: 128 },
        week: { rank: 18, nickname: nickname as string, avatar: (anyMe?.avatar as string | null) || null, score: 8600, mine: true, totalPlayers: 128 },
        month: { rank: 24, nickname: nickname as string, avatar: (anyMe?.avatar as string | null) || null, score: 32000, mine: true, totalPlayers: 128 },
      };
      return out;
    })(),
    staleTime: 60_000,
  });

  const kpis = useMemo(
    () => ({
      minutesToday: 62,
      exercisesDone: 28,
      coursesInProgress: 4,
      streak: 13,
      subjects,
    }),
    [subjects],
  );

  const streakDays = typeof anyMe?.streak === "number" ? anyMe.streak : kpis.streak;

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

      {/* KPI 4 卡 */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          accent="indigo"
          title="今日学习时长"
          value={`${kpis.minutesToday} 分钟`}
          delta={{ direction: "up", value: "+12% 较昨日" }}
          icon={<GraduationCap className="h-5 w-5" />}
        />
        <KpiCard
          accent="emerald"
          title="今日练习题"
          value={`${kpis.exercisesDone} 道`}
          delta={{ direction: "up", value: "正确率 82%" }}
          icon={<BookOpenCheck className="h-5 w-5" />}
        />
        <KpiCard
          accent="amber"
          title="进行中课程"
          value={`${kpis.coursesInProgress} 门`}
          delta={{ direction: "flat", value: "建议一次 focus 2 门" }}
          icon={<LayoutGrid className="h-5 w-5" />}
        />
        <KpiCard
          accent="violet"
          title="活跃学科"
          value={`${kpis.subjects.length} / ${SUBJECT_OPTIONS.length}`}
          delta={{ direction: "up", value: kpis.subjects.slice(0, 3).map((s) => SUBJECT_LABELS[s]).join("·") }}
          icon={<Waypoints className="h-5 w-5" />}
        />
      </section>

      {/* 快捷入口 CTA：串联主要页面（修复 dashboard 只能点侧栏，没有显眼的跳转卡片的问题） */}
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
        <StreakBadge
          className="lg:col-span-1"
          streakDays={streakDays}
          last7Days={["done", "done", "partial", "done", "done", "partial", "today"]}
        />
        <PointCard
          className="lg:col-span-2"
          total={points?.total ?? 0}
          todayGain={points?.todayGain ?? 0}
          recentGains={points?.recentGains ?? []}
          loading={pointsLoading}
        />
      </section>

      {/* 第 3 行：折线 + 雷达 */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <ProgressTrendChart
          className="lg:col-span-2"
          data={trend ?? []}
          loading={trendLoading}
        />
        <AbilityRadarChart
          className="lg:col-span-1"
          series={radar ?? []}
          loading={radarLoading}
          description="对比「我的能力」与「全班平均」，一眼看到优势和待提升点。"
        />
      </section>

      {/* 第 4 行：徽章墙 + 排行榜 */}
      <section className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <BadgeWallGrid
          className="xl:col-span-2"
          badges={badges ?? []}
          minCols={5}
          description={badgesLoading ? "加载中…" : undefined}
        />
        <RankList
          className="xl:col-span-1"
          data={rankData ?? {}}
          loading={rankLoading}
          topN={10}
        />
      </section>
    </div>
  );
}

type UserInfoExtended = {
  nickname?: string | null;
  name?: string | null;
  avatar?: string | null;
  points?: number | null;
  subjectPreferences?: unknown;
  streak?: number | null;
};

export default function DashboardPage() {
  return (
    <ProtectedRoute>
      <DashboardPageInner />
    </ProtectedRoute>
  );
}
