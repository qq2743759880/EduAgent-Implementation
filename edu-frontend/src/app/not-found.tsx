import Link from "next/link";
import { ArrowLeft, BookOpen, LayoutDashboard, LogIn, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

/**
 * 全局 404 页（App Router 约定：app/not-found.tsx 自动捕获未匹配路由）
 * 表现：带 EduAgent 品牌样式 + 3 个导航 CTA（避免用户无处可去）
 */
export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-10 bg-gradient-to-br from-indigo-50 via-white to-sky-50">
      <Card className="w-full max-w-md shadow-xl border-slate-200/80 bg-white/90 backdrop-blur">
        <CardHeader className="space-y-2 text-center pb-2">
          <div className="mx-auto inline-flex items-center gap-2 rounded-2xl bg-gradient-to-br from-indigo-600 to-sky-500 px-4 py-2 shadow-sm">
            <span className="h-6 w-6 rounded-lg bg-white/15 border border-white/20 flex items-center justify-center text-white text-xs font-bold">
              404
            </span>
            <span className="text-white font-semibold tracking-wide">EduAgent</span>
          </div>
          <CardTitle className="text-2xl font-bold text-slate-900 pt-2">
            这个页面暂时不存在
          </CardTitle>
          <CardDescription className="text-sm text-slate-500">
            链接可能已经失效，或者你访问的模块还在开发中（如管理后台）。
            试试下面几个入口，继续你的学习旅程。
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Button asChild variant="outline" className="h-16 flex-col gap-1 items-start px-4">
            <Link href="/dashboard">
              <LayoutDashboard className="h-4 w-4 text-indigo-600" />
              <span className="text-sm font-semibold">学习仪表盘</span>
            </Link>
          </Button>
          <Button asChild variant="outline" className="h-16 flex-col gap-1 items-start px-4">
            <Link href="/courses">
              <BookOpen className="h-4 w-4 text-emerald-600" />
              <span className="text-sm font-semibold">课程中心</span>
            </Link>
          </Button>
          <Button asChild variant="outline" className="h-16 flex-col gap-1 items-start px-4">
            <Link href="/chat">
              <Sparkles className="h-4 w-4 text-amber-600" />
              <span className="text-sm font-semibold">AI 问答</span>
            </Link>
          </Button>
        </CardContent>
        <CardFooter className="pt-2 pb-6 flex items-center justify-center gap-2 text-sm text-slate-600">
          <Button asChild variant="ghost" size="sm">
            <Link href="/login">
              <LogIn className="mr-1.5 h-4 w-4" />
              返回登录
            </Link>
          </Button>
          <Button
            asChild
            size="sm"
            className="bg-gradient-to-br from-indigo-600 to-sky-600 hover:from-indigo-700 hover:to-sky-700 text-white shadow-sm"
          >
            <Link href="/">
              <ArrowLeft className="mr-1.5 h-4 w-4" />
              回到首页
            </Link>
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
