"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ComponentType, useMemo, useState } from "react";
import {
  BookOpen,
  BookOpenCheck,
  ChevronRight,
  LayoutDashboard,
  LogOut,
  MessageCircle,
  Menu,
  NotepadTextDashed,
  Settings2,
  Sparkles,
  UserRoundCog,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/lib/auth-client";
import { toast } from "sonner";

/**
 * 用户区布局（路由组 (user) 共享壳）：
 *  - 桌面端：左侧固定侧边栏 + 顶部面包屑/用户下拉
 *  - 移动端：顶部汉堡按钮 → 抽屉式侧边栏
 *  - 登录/注册页：隐藏侧边栏与用户菜单（仅保留 EduAgent 品牌条居中返回首页）
 */
export default function UserAreaLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const authed = useAuthStore((s) => s.isAuthenticated());
  const me = useAuthStore((s) => s.me);
  const logout = useAuthStore((s) => s.logout);

  const [mobileOpen, setMobileOpen] = useState(false);

  const isAuthGate = useMemo(
    () => pathname === "/login" || pathname === "/register",
    [pathname],
  );

  // 侧边栏导航项（只有登录后展示）
  const navItems: Array<{
    href: string;
    label: string;
    Icon: ComponentType<{ className?: string }>;
    active: boolean;
    badge?: string;
  }> = [
    {
      href: "/dashboard",
      label: "学习仪表盘",
      Icon: LayoutDashboard,
      active: pathname === "/dashboard",
    },
    {
      href: "/courses",
      label: "课程中心",
      Icon: BookOpen,
      active: pathname.startsWith("/courses"),
    },
    {
      href: "/my-courses",
      label: "我的课程",
      Icon: BookOpenCheck,
      active: pathname.startsWith("/my-courses") || pathname.startsWith("/learning"),
    },
    {
      href: "/practice/wrong-book",
      label: "错题 / 单词本",
      Icon: NotepadTextDashed,
      active: pathname.startsWith("/practice"),
    },
    {
      href: "/chat",
      label: "AI 学习问答",
      Icon: Sparkles,
      active: pathname === "/chat",
    },
    {
      href: "/me",
      label: "个人中心",
      Icon: UserRoundCog,
      active: pathname === "/me",
    },
  ];

  const nickname =
    typeof me?.nickname === "string" && me.nickname ? me.nickname : (me as any)?.username ?? "我";
  const avatarText = String(nickname).trim().charAt(0).toUpperCase() || "E";

  function handleLogout() {
    logout({ silent: false });
    toast.success("已退出登录", { description: "下次见面也要继续加油哦" });
    router.replace("/login");
    router.refresh();
  }

  // 登录/注册页：只保留简洁品牌条，不展示导航
  if (isAuthGate) {
    return (
      <div className="min-h-screen flex flex-col">
        <header className="w-full px-5 py-3 flex items-center justify-center border-b border-slate-200/70 bg-white/70 backdrop-blur">
          <Link
            href="/"
            className="inline-flex items-center gap-2 group"
            aria-label="返回 EduAgent 首页"
          >
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-600 to-sky-500 shadow-sm text-white">
              <Sparkles className="h-4 w-4" />
            </span>
            <span className="font-semibold tracking-wide text-slate-800 group-hover:text-indigo-700 transition-colors">
              EduAgent
            </span>
          </Link>
        </header>
        <main className="flex-1">{children}</main>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex bg-slate-50/70">
      {/* ============ 侧边栏（桌面端固定，移动端抽屉） ============ */}
      <aside
        className={cn(
          "fixed z-40 inset-y-0 left-0 w-64 border-r border-slate-200 bg-white/90 backdrop-blur flex flex-col transition-transform duration-200 md:translate-x-0",
          mobileOpen ? "translate-x-0 shadow-2xl" : "-translate-x-full",
        )}
        aria-label="主导航"
      >
        <div className="h-16 border-b border-slate-200 px-5 flex items-center justify-between">
          <Link
            href="/"
            className="inline-flex items-center gap-2 shrink-0"
            onClick={() => setMobileOpen(false)}
          >
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-600 to-sky-500 shadow-sm text-white">
              <Sparkles className="h-4 w-4" />
            </span>
            <span className="font-semibold tracking-wide text-slate-800">EduAgent</span>
          </Link>
          <Button
            variant="ghost"
            size="icon"
            aria-label="关闭导航"
            className="md:hidden"
            onClick={() => setMobileOpen(false)}
          >
            <X className="h-5 w-5" />
          </Button>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {navItems.map(({ href, label, Icon, active }) => (
            <Link
              key={href}
              href={href}
              onClick={() => setMobileOpen(false)}
              className={cn(
                "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors",
                active
                  ? "bg-gradient-to-r from-indigo-600 to-indigo-500 text-white shadow-sm"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
              )}
              aria-current={active ? "page" : undefined}
            >
              <Icon className={cn("h-5 w-5 shrink-0", active ? "" : "text-slate-500 group-hover:text-indigo-600")} />
              <span className="flex-1 font-medium">{label}</span>
              <ChevronRight
                className={cn(
                  "h-4 w-4 transition-transform",
                  active ? "opacity-100" : "opacity-0 group-hover:opacity-60",
                )}
              />
            </Link>
          ))}
        </nav>

        <div className="border-t border-slate-200 px-3 py-3 space-y-2">
          {authed ? (
            <button
              onClick={handleLogout}
              className="w-full inline-flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-slate-600 hover:bg-rose-50 hover:text-rose-600 transition-colors"
            >
              <LogOut className="h-5 w-5" />
              <span className="font-medium">退出登录</span>
            </button>
          ) : (
            <Link
              href="/login"
              onClick={() => setMobileOpen(false)}
              className="w-full inline-flex items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-sm font-medium text-white bg-gradient-to-br from-indigo-600 to-sky-600 hover:from-indigo-700 hover:to-sky-700 shadow-sm"
            >
              登录 EduAgent
            </Link>
          )}
          <p className="px-1 text-[11px] leading-relaxed text-slate-400">
            © EduAgent · 让学习被量化，让努力被记住
          </p>
        </div>
      </aside>

      {/* 移动端遮罩 */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-slate-900/30 md:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden
        />
      )}

      {/* ============ 主内容区 ============ */}
      <div className="flex-1 min-w-0 md:ml-64 flex flex-col">
        {/* 顶部栏 */}
        <header className="sticky top-0 z-20 h-16 px-4 md:px-8 border-b border-slate-200 bg-white/80 backdrop-blur flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              aria-label="打开导航"
              className="md:hidden"
              onClick={() => setMobileOpen(true)}
            >
              <Menu className="h-5 w-5" />
            </Button>
            <div className="text-xs md:text-sm text-slate-500">
              当前路径：
              <code className="mx-1 rounded bg-slate-100 px-1.5 py-0.5 text-slate-700 font-mono text-[11px] md:text-xs">
                {pathname || "/"}
              </code>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex">
              <Link href="/chat" className="gap-1.5">
                <MessageCircle className="h-4 w-4" />
                问 AI
              </Link>
            </Button>

            {authed ? (
              /* 纯 CSS hover 菜单：避免依赖尚未安装的 dropdown-menu 组件 */
              <div className="relative group">
                <Button variant="ghost" size="sm" className="gap-2 px-2 h-9">
                  <Avatar className="h-7 w-7 border border-slate-200">
                    <AvatarFallback className="bg-gradient-to-br from-indigo-500 to-sky-500 text-white text-xs font-semibold">
                      {avatarText}
                    </AvatarFallback>
                  </Avatar>
                  <span className="hidden md:inline text-sm text-slate-700 font-medium max-w-[140px] truncate">
                    {nickname}
                  </span>
                </Button>
                <div className="pointer-events-none opacity-0 group-hover:opacity-100 group-hover:pointer-events-auto transition-all duration-150 ease-out absolute right-0 mt-1.5 w-60 origin-top-right rounded-xl border border-slate-200 bg-white shadow-xl shadow-slate-900/5 z-50">
                  <div className="px-4 py-3 border-b border-slate-100">
                    <p className="text-xs text-slate-500">当前账号</p>
                    <p className="text-sm font-semibold text-slate-900 truncate">{nickname}</p>
                    <p className="text-[11px] text-emerald-600 mt-0.5">已登录</p>
                  </div>
                  <div className="p-1.5 flex flex-col gap-0.5">
                    <Link
                      href="/dashboard"
                      className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-slate-700 hover:bg-slate-100"
                    >
                      <LayoutDashboard className="h-4 w-4 text-slate-500" />
                      返回仪表盘
                    </Link>
                    <Link
                      href="/me"
                      className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-slate-700 hover:bg-slate-100"
                    >
                      <UserRoundCog className="h-4 w-4 text-slate-500" />
                      个人中心
                    </Link>
                    <Link
                      href="/me?tab=preferences"
                      className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-slate-700 hover:bg-slate-100"
                    >
                      <Settings2 className="h-4 w-4 text-slate-500" />
                      学习偏好
                    </Link>
                  </div>
                  <div className="p-1.5 border-t border-slate-100">
                    <button
                      onClick={handleLogout}
                      className="w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-rose-600 hover:bg-rose-50"
                    >
                      <LogOut className="h-4 w-4" />
                      退出登录
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <Button asChild size="sm" className="bg-gradient-to-br from-indigo-600 to-sky-600 hover:from-indigo-700 hover:to-sky-700 text-white shadow-sm">
                <Link href="/login">登录</Link>
              </Button>
            )}
          </div>
        </header>

        {/* 页面内容 */}
        <main className="flex-1 min-w-0 w-full">{children}</main>
      </div>
    </div>
  );
}
