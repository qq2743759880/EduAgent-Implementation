/**
 * /my-courses — 我的班次（task47，重构为 enrollments 语义）
 *   Tabs: 学习中 (active) / 已完成 (completed) / 已退款 (refunded)
 *   受保护路由：客户端 MyCoursesClient hydrate 后未登录 → 跳 /login?redirect=/my-courses
 *   数据来源: 契约⑪ GET /api/enrollments/me/cohorts（task20/21 待联调）
 */
import { Suspense } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { Loader2 } from "lucide-react";
import MyCoursesClient from "./_components/MyCoursesClient";

export const metadata: Metadata = {
  title: "我的班次 · EduAgent",
  description: "查看你正在学习、已完成或已退款的报名班次，并继续学习。",
};

export const dynamic = "force-dynamic";

export default function MyCoursesPage() {
  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-6 md:px-6 md:py-10">
      <nav aria-label="面包屑" className="mb-4 flex flex-wrap items-center gap-1.5 text-[0.8rem] text-foreground/70">
        <Link className="font-semibold text-candy-blue hover:underline" href="/courses">课程中心</Link>
        <span aria-hidden="true" className="opacity-50">›</span>
        <span className="font-bold text-foreground">我的班次</span>
      </nav>
      <header className="mb-6 flex items-center gap-3.5">
        <span aria-hidden="true" className="text-4xl drop-shadow-[0_4px_0_rgba(31,31,31,0.15)]">🎓</span>
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-foreground md:text-[1.625rem]">我的班次</h1>
          <p className="mt-1 text-[0.8rem] text-foreground/60">
            你报名的所有班次 · 进度聚合为「模块 X/Y · 课次 X/Y」四级真实数据
          </p>
        </div>
      </header>
      <Suspense
        fallback={
          <div className="flex min-h-[50vh] items-center justify-center text-sm text-foreground/60">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            正在加载我的班次…
          </div>
        }
      >
        <MyCoursesClient />
      </Suspense>
    </div>
  );
}