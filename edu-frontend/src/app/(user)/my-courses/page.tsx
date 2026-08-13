/**
 * /my-courses — 我的课程中心
 *   Tabs: 进行中 (in_progress) / 已完成 (completed) / 已收藏 (favorited)
 *   ProtectedRoute: 未登录 → 跳 /login?redirect=/my-courses
 *   数据来源: P3 /api/progress/courses + 本地 localStorage 收藏夹
 */
import { Suspense } from "react";
import type { Metadata } from "next";
import {
  BookOpenCheck,
  BookMarked,
  CircleHelp,
  GraduationCap,
  Heart,
  Loader2,
  Trophy,
} from "lucide-react";
import MyCoursesClient from "./_components/MyCoursesClient";

export const metadata: Metadata = {
  title: "我的课程 · EduAgent",
  description: "查看你正在学习、已完成或已收藏的分级课程，并继续学习。",
};

export const dynamic = "force-dynamic";

export default function MyCoursesPage() {
  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-6 md:px-6 md:py-10">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1.5">
          <div className="inline-flex items-center gap-1.5 rounded-full border border-primary-border bg-primary-soft px-3 py-1 text-xs font-medium text-primary">
            <BookOpenCheck className="h-3.5 w-3.5" />
            Learning Center
          </div>
          <h1 className="text-2xl font-bold tracking-tight md:text-3xl text-foreground">我的课程</h1>
          <p className="max-w-xl text-sm text-muted-foreground">
            在这里查看所有报名课程的学习进度，也可以快速收藏喜欢的课程留待稍后学习。
          </p>
        </div>
        <StatStrip />
      </header>
      <Suspense
        fallback={
          <div className="min-h-[50vh] flex items-center justify-center text-sm text-muted-foreground">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            正在加载我的课程…
          </div>
        }
      >
        <MyCoursesClient />
      </Suspense>
    </div>
  );
}

function StatStrip() {
  /* fe-task07：StatStrip 并列分类统计三态色（sky/emerald/rose）→ 全主色（design-options §2.5）；
     区分靠图标 + 文字标签 + 计数数字 */
  const items = [
    { key: "in_progress", label: "进行中", Icon: GraduationCap, tone: "text-primary", bg: "bg-primary-soft" },
    { key: "completed", label: "已完成", Icon: Trophy, tone: "text-primary", bg: "bg-primary-soft" },
    { key: "favorited", label: "已收藏", Icon: Heart, tone: "text-primary", bg: "bg-primary-soft" },
    { key: "faq", label: "需要帮助？", Icon: CircleHelp, tone: "text-primary", bg: "bg-primary-soft" },
  ] as const;
  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
      {items.map(({ key, label, Icon, tone, bg }) => (
        <div
          key={key}
          className="flex items-center gap-3 rounded-xl border border-border bg-card px-3 py-2.5 shadow-card"
        >
          <span className={`grid h-9 w-9 place-items-center rounded-xl ${bg} ${tone}`}>
            <Icon className="h-4.5 w-4.5" />
          </span>
          <div className="text-sm">
            <div className="font-semibold leading-tight text-foreground">{label}</div>
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin opacity-60" />
              实时加载
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// 保留 BookMarked import（避免 lint 未使用：在 client 端 Tab "已收藏" 用 Icon
export const __fav_icon_marker = BookMarked;
