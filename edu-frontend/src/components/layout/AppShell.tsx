"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ComponentType, type KeyboardEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { ChevronRight, Menu, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * AppShell —— 全站唯一共享壳（纯展示壳，fe-task00 / D1）。
 *
 * 职责边界（diff 红线）：
 *  - 只做参数化渲染：品牌 / 导航 / 顶栏 / footer / 内容区 + 移动抽屉（状态/焦点/aria 全部壳内实现）。
 *  - 禁止：读取 auth store、角色判断、登录特判、守卫（AdminGuard/ProtectedRoute）、路由跳转业务、
 *          业务数据查询 —— 全部由两薄 layout（(user)/(admin)）注入或包裹。
 *  - 激活态由 `usePathname` + `matchPrefix` 计算，注入方只提供配置。
 */
export interface AppShellNavItem {
  href: string;
  label: string;
  Icon: ComponentType<{ className?: string }>;
  /**
   * 激活判定：matchPrefix 存在 → pathname.startsWith(matchPrefix)（数组任一命中）；
   * 缺省 → pathname === href。
   * user 侧把既有 startsWith 语义显式化为 matchPrefix（如 /courses → matchPrefix "/courses"）；
   * 单一项无法表达双前缀（如 我的课程 = /my-courses 或 /learning）时用数组。
   */
  matchPrefix?: string | string[];
  /** 可选角标（当前两壳均未用，保留契约） */
  badge?: string;
}

export interface AppShellBrand {
  href: string; // user: "/"；admin: "/admin/dashboard"
  label: string; // "EduAgent" / "EduAgent 管理端"
  Icon: ComponentType<{ className?: string }>; // user: Sparkles；admin: ShieldCheck
}

export interface AppShellProps {
  brand: AppShellBrand;
  /** 注入配置：user 8 项 / admin 6 项；RBAC 过滤在调用方完成（薄 layout），AppShell 不感知角色 */
  navItems: AppShellNavItem[];
  /** admin: 面包屑（CRUMB_LABELS 留在薄 layout）；user: 缺省 */
  headerLeft?: ReactNode;
  /** user: 问AI + 用户下拉（纯 CSS hover 菜单，留在薄 layout）；admin: 用户信息+退出 */
  headerRight?: ReactNode;
  /** 侧边栏底部：user: 退出/登录 CTA+版权；admin: 版权；缺省渲染 © 版权行 */
  footer?: ReactNode;
  /** 内容区 padding：user 默认无 padding、admin 传 "p-4 md:p-6" */
  contentClassName?: string;
  /** 页面底色：缺省 "bg-slate-100/70"（管理端基准） */
  pageClassName?: string;
  /** 侧边栏 aria-label：两壳区分（"主导航"/"管理端导航"），缺省 "主导航" */
  navAriaLabel?: string;
  children: ReactNode;
}

const DESKTOP_MQ = "(min-width: 768px)";

function isActive(pathname: string, item: AppShellNavItem): boolean {
  if (!item.matchPrefix) return pathname === item.href;
  const prefixes = Array.isArray(item.matchPrefix) ? item.matchPrefix : [item.matchPrefix];
  return prefixes.some((p) => pathname.startsWith(p));
}

export default function AppShell({
  brand,
  navItems,
  headerLeft,
  headerRight,
  footer,
  contentClassName,
  pageClassName = "bg-slate-100/70",
  navAriaLabel = "主导航",
  children,
}: AppShellProps) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  // 桌面优先（fe-task00 a11y 修正 #1）：初始恒为 true —— SSR 与客户端首次渲染均渲染无 inert，
  // hydration 完全一致（React 不会修补属性 mismatch，旧实现桌面端残留 inert 阻塞导航）。
  // 移动端由下方 matchMedia effect 挂载后修正为 false → 状态变化触发重渲染 → inert 生效。
  // 注意：初始值不得在客户端求值 matchMedia（移动端会与 SSR 不一致 → mismatch + inert 永不落地）。
  const [isDesktop, setIsDesktop] = useState(true);
  const openBtnRef = useRef<HTMLButtonElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const firstNavLinkRef = useRef<HTMLAnchorElement>(null);

  // 视口 ≥md（Tailwind md 断点）时侧边栏固定可见；移动端随抽屉开合
  useEffect(() => {
    const mq = window.matchMedia(DESKTOP_MQ);
    const onChange = () => setIsDesktop(mq.matches);
    onChange();
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  /**
   * 关闭抽屉并归还焦点到触发按钮（非导航型关闭：X / 遮罩 / Escape）。
   * 菜单/品牌链接点击关闭后由路由接管焦点，不调用本函数。
   */
  function closeDrawer() {
    setMobileOpen(false);
    openBtnRef.current?.focus();
  }

  /** 打开抽屉：移动端抽屉为临时层，焦点在 effect 中移入首个菜单项 */
  function openDrawer() {
    setMobileOpen(true);
  }

  // 抽屉打开后聚焦内部首个可交互元素（首菜单项，无菜单时回退关闭按钮）
  useEffect(() => {
    if (!mobileOpen) return;
    (firstNavLinkRef.current ?? closeBtnRef.current)?.focus();
  }, [mobileOpen]);

  /** Escape 关闭抽屉：挂在根容器，焦点在抽屉内或已移出均可关闭 */
  function handleRootKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key !== "Escape" || !mobileOpen) return;
    e.preventDefault();
    closeDrawer();
  }

  return (
    <div className={cn("min-h-screen flex", pageClassName)} onKeyDown={handleRootKeyDown}>
      {/* ============ 侧边栏（桌面固定 / 移动抽屉） ============ */}
      <aside
        id="app-sidebar"
        aria-label={navAriaLabel}
        // 移动端抽屉关闭态：inert 将侧边栏整体移出 Tab 序列与无障碍树
        inert={!isDesktop && !mobileOpen}
        className={cn(
          "fixed z-40 inset-y-0 left-0 w-64 border-r border-sidebar-border bg-sidebar flex flex-col transition-transform duration-200 md:translate-x-0",
          mobileOpen ? "translate-x-0 shadow-drawer" : "-translate-x-full",
        )}
      >
        <div className="h-16 border-b border-sidebar-border px-5 flex items-center justify-between">
          <Link
            href={brand.href}
            className="inline-flex items-center gap-2 shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-xl"
            onClick={() => setMobileOpen(false)}
          >
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-primary-deep to-primary-strong shadow-sm text-white">
              <brand.Icon className="h-4 w-4" />
            </span>
            <span className="font-semibold tracking-wide text-sidebar-accent-foreground">
              {brand.label}
            </span>
          </Link>
          <Button
            ref={closeBtnRef}
            variant="ghost"
            size="icon"
            aria-label="关闭导航"
            aria-expanded={mobileOpen}
            aria-controls="app-sidebar"
            className="md:hidden"
            onClick={closeDrawer}
          >
            <X className="h-5 w-5" />
          </Button>
        </div>

        <nav aria-label={navAriaLabel} className="flex-1 px-3 py-4 overflow-y-auto">
          <ul className="space-y-1">
            {navItems.map(({ href, label, Icon, matchPrefix }, index) => {
              const active = isActive(pathname, { href, label, Icon, matchPrefix });
              return (
                <li key={href}>
                  <Link
                    ref={index === 0 ? firstNavLinkRef : undefined}
                    href={href}
                    onClick={() => setMobileOpen(false)}
                    className={cn(
                      "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      active
                        ? "bg-gradient-to-r from-primary-deep to-primary-strong text-white shadow-sm"
                        : "text-sidebar-foreground hover:bg-sidebar-accent",
                    )}
                    aria-current={active ? "page" : undefined}
                  >
                    <Icon
                      className={cn(
                        "h-5 w-5 shrink-0",
                        active ? "" : "text-muted-foreground group-hover:text-primary",
                      )}
                    />
                    <span className="flex-1 font-medium">{label}</span>
                    <ChevronRight
                      className={cn(
                        "h-4 w-4 transition-transform",
                        active ? "opacity-100" : "opacity-0 group-hover:opacity-60",
                      )}
                    />
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="border-t border-sidebar-border px-3 py-3 space-y-2">
          {footer ?? (
            <p className="px-1 text-3xs leading-relaxed text-sidebar-foreground/60">© EduAgent</p>
          )}
        </div>
      </aside>

      {/* 移动端遮罩 */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-slate-900/30 md:hidden"
          onClick={closeDrawer}
          aria-hidden
        />
      )}

      {/* ============ 主内容区 ============ */}
      <div className="flex-1 min-w-0 md:ml-64 flex flex-col">
        <header className="sticky top-0 z-20 h-14 px-4 md:px-6 border-b border-border bg-background/80 backdrop-blur flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <Button
              ref={openBtnRef}
              variant="ghost"
              size="icon"
              aria-label="打开导航"
              aria-expanded={mobileOpen}
              aria-controls="app-sidebar"
              className="md:hidden"
              onClick={openDrawer}
            >
              <Menu className="h-5 w-5" />
            </Button>
            {headerLeft}
          </div>
          <div className="flex items-center gap-2 shrink-0">{headerRight}</div>
        </header>

        {/* 页面内容 */}
        <main className={cn("flex-1 min-w-0 w-full", contentClassName)}>{children}</main>
      </div>
    </div>
  );
}
