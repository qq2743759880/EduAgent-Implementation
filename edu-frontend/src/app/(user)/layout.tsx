"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  BookOpen,
  BookOpenCheck,
  LayoutDashboard,
  LogOut,
  MessageCircle,
  MessagesSquare,
  NotepadTextDashed,
  Settings2,
  Sparkles,
  Trophy,
  UserRoundCog,
} from "lucide-react";
import { toast } from "sonner";

import AppShell, { type AppShellNavItem } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { useAuthStore } from "@/lib/auth-client";
import { cn } from "@/lib/utils";

/**
 * 用户区布局（路由组 (user) 共享壳，fe-task00 改薄）：
 *  - 登录/注册页（isAuthGate）：仅品牌条，不渲染 AppShell（现状特判保留）。
 *  - 其余页面：薄包装 AppShell —— 8 导航配置、问AI + 用户下拉（headerRight）、
 *    退出/登录 CTA + 版权（footer）均在本层组装；守卫在页面级 ProtectedRoute（不动）。
 *  - 壳本身（侧边栏/顶栏/抽屉/激活态）全部下沉 AppShell。
 */
export default function UserAreaLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const authed = useAuthStore((s) => s.isAuthenticated());
  const me = useAuthStore((s) => s.me);
  const logout = useAuthStore((s) => s.logout);

  const isAuthGate = useMemo(
    () => pathname === "/login" || pathname === "/register",
    [pathname],
  );

  /** 用户下拉（fe-task00 a11y 修正 #2）：React state 控制开合，键盘可达（非仅 hover） */
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuTriggerRef = useRef<HTMLButtonElement>(null);
  const userMenuPanelRef = useRef<HTMLDivElement>(null);
  // 菜单项点击/路由变化后由点击外部监听（pointerdown）或菜单项 onClick 关闭

  // 菜单展开期间：点击外部关闭；Escape 关闭并归还焦点到触发按钮
  useEffect(() => {
    if (!userMenuOpen) return;
    function handlePointerDown(e: PointerEvent) {
      const target = e.target as Node;
      if (
        userMenuPanelRef.current?.contains(target) ||
        userMenuTriggerRef.current?.contains(target)
      ) {
        return;
      }
      setUserMenuOpen(false);
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      setUserMenuOpen(false);
      userMenuTriggerRef.current?.focus();
    }
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [userMenuOpen]);

  /** 侧边栏导航项（登录后展示；既有 === / startsWith 语义显式化为 matchPrefix） */
  const navItems: AppShellNavItem[] = [
    { href: "/dashboard", label: "学习仪表盘", Icon: LayoutDashboard },
    { href: "/courses", label: "课程中心", Icon: BookOpen, matchPrefix: "/courses" },
    {
      href: "/my-courses",
      label: "我的课程",
      Icon: BookOpenCheck,
      matchPrefix: ["/my-courses", "/learning"],
    },
    {
      href: "/practice/wrong-book",
      label: "错题 / 单词本",
      Icon: NotepadTextDashed,
      matchPrefix: "/practice",
    },
    { href: "/chat", label: "AI 学习问答", Icon: Sparkles },
    { href: "/community", label: "社区", Icon: MessagesSquare, matchPrefix: "/community" },
    { href: "/achievements", label: "成就中心", Icon: Trophy, matchPrefix: "/achievements" },
    { href: "/me", label: "个人中心", Icon: UserRoundCog },
  ];

  const nickname =
    typeof me?.nickname === "string" && me.nickname ? me.nickname : me?.username ?? "我";
  const avatarText = String(nickname).trim().charAt(0).toUpperCase() || "E";

  function handleLogout() {
    logout({ silent: false });
    toast.success("已退出登录", { description: "下次见面也要继续加油哦" });
    router.replace("/login");
    router.refresh();
  }

  /** headerRight：问AI + 用户下拉（键盘可达下拉，fe-task00 a11y 修正 #2；hover 打开保留）/ 未登录登录按钮 */
  const headerRight: ReactNode = (
    <>
      <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex">
        <Link href="/chat" className="gap-1.5">
          <MessageCircle className="h-4 w-4" />
          问 AI
        </Link>
      </Button>

      {authed ? (
        <div className="relative group">
          <Button
            ref={userMenuTriggerRef}
            variant="ghost"
            size="sm"
            className="gap-2 px-2 h-9"
            aria-haspopup="menu"
            aria-expanded={userMenuOpen}
            aria-controls="user-menu"
            aria-label={nickname}
            onClick={() => setUserMenuOpen((v) => !v)}
          >
            <Avatar className="h-7 w-7 border border-border">
              <AvatarFallback className="bg-gradient-to-br from-primary-deep to-primary text-white text-xs font-semibold">
                {avatarText}
              </AvatarFallback>
            </Avatar>
            <span className="hidden md:inline text-sm text-secondary-foreground font-medium max-w-[140px] truncate">
              {nickname}
            </span>
          </Button>
          <div
            id="user-menu"
            ref={userMenuPanelRef}
            role="menu"
            aria-label="用户菜单"
            className={cn(
              "absolute right-0 mt-1.5 w-60 origin-top-right rounded-xl border border-border bg-card shadow-xl shadow-slate-900/5 z-50",
              "transition-all duration-150 ease-out",
              // 收起态：invisible（移出 Tab 序与无障碍树）+ opacity-0 + pointer-events-none；
              // hover 仍可打开（group-hover:visible/opacity/pointer-events 保留原 hover 能力）
              "pointer-events-none opacity-0 group-hover:pointer-events-auto group-hover:opacity-100",
              "invisible group-hover:visible",
              userMenuOpen && "visible pointer-events-auto opacity-100",
            )}
          >
            <div className="px-4 py-3 border-b border-border" role="presentation">
              <p className="text-xs text-muted-foreground">当前账号</p>
              <p className="text-sm font-semibold text-foreground truncate">{nickname}</p>
              <p className="text-3xs text-success-foreground mt-0.5">已登录</p>
            </div>
            <div className="p-1.5 flex flex-col gap-0.5">
              <Link
                href="/dashboard"
                role="menuitem"
                className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-secondary-foreground hover:bg-muted"
                onClick={() => setUserMenuOpen(false)}
              >
                <LayoutDashboard className="h-4 w-4 text-muted-foreground" />
                返回仪表盘
              </Link>
              <Link
                href="/me"
                role="menuitem"
                className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-secondary-foreground hover:bg-muted"
                onClick={() => setUserMenuOpen(false)}
              >
                <UserRoundCog className="h-4 w-4 text-muted-foreground" />
                个人中心
              </Link>
              <Link
                href="/me?tab=preferences"
                role="menuitem"
                className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-secondary-foreground hover:bg-muted"
                onClick={() => setUserMenuOpen(false)}
              >
                <Settings2 className="h-4 w-4 text-muted-foreground" />
                学习偏好
              </Link>
            </div>
            <div className="p-1.5 border-t border-border">
              <button
                role="menuitem"
                onClick={() => {
                  setUserMenuOpen(false);
                  handleLogout();
                }}
                className="w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-destructive hover:bg-destructive/10"
              >
                <LogOut className="h-4 w-4" />
                退出登录
              </button>
            </div>
          </div>
        </div>
      ) : (
        <Button asChild size="sm">
          <Link href="/login">登录</Link>
        </Button>
      )}
    </>
  );

  /** footer：退出登录 CTA（登录态）/ 登录 CTA（未登录）+ 版权 */
  const footer: ReactNode = (
    <div className="space-y-2">
      {authed ? (
        <button
          onClick={handleLogout}
          className="w-full inline-flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-sidebar-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
        >
          <LogOut className="h-5 w-5" />
          <span className="font-medium">退出登录</span>
        </button>
      ) : (
        <Link
          href="/login"
          className="w-full inline-flex items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-sm font-medium text-white bg-gradient-to-br from-primary-deep to-primary hover:from-primary-deep hover:to-primary-strong shadow-sm"
        >
          登录 EduAgent
        </Link>
      )}
      <p className="px-1 text-3xs leading-relaxed text-sidebar-foreground/60">
        © EduAgent · 让学习被量化，让努力被记住
      </p>
    </div>
  );

  // 登录/注册页：只保留简洁品牌条，不展示导航
  if (isAuthGate) {
    return (
      <div className="min-h-screen flex flex-col">
        <header className="w-full px-5 py-3 flex items-center justify-center border-b border-border bg-background/70 backdrop-blur">
          <Link
            href="/"
            className="inline-flex items-center gap-2 group"
            aria-label="返回 EduAgent 首页"
          >
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-primary-deep to-primary-strong shadow-sm text-white">
              <Sparkles className="h-4 w-4" />
            </span>
            <span className="font-semibold tracking-wide text-sidebar-accent-foreground group-hover:text-primary transition-colors">
              EduAgent
            </span>
          </Link>
        </header>
        <main className="flex-1">{children}</main>
      </div>
    );
  }

  return (
    <AppShell
      brand={{ href: "/", label: "EduAgent", Icon: Sparkles }}
      navItems={navItems}
      navAriaLabel="主导航"
      pageClassName="bg-slate-100/70"
      headerRight={headerRight}
      footer={footer}
    >
      {children}
    </AppShell>
  );
}
