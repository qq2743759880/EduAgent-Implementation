"use client";

import { usePathname, useRouter } from "next/navigation";
import { useMemo } from "react";
import { ChevronRight, LogOut, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

import AppShell from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/lib/auth-client";
import { AdminGuard } from "@/lib/admin-guard";
import { filterAdminNav } from "@/lib/admin-nav";

/**
 * 管理端共享布局（路由组 (admin) 共享壳，task02 改薄 / fe-task00）
 *  - AdminGuard 包裹：admin 放行；manager/student/teacher 拦截 + toast + 重定向；未登录跳登录页
 *    （对抗 #2 处置：后端 /api/admin/* 全部 ADMIN-only，manager 无任何管理端点权限）
 *  - 侧边栏 6 菜单（仪表盘/课程/题库/用户/RAG/MCP），仅 admin 可见（RBAC 菜单过滤）
 *  - 顶栏面包屑（headerLeft）+ 用户信息/退出（headerRight）
 *  - 壳本身（侧边栏/顶栏/抽屉/激活态）全部下沉 AppShell；守卫/角色过滤/面包屑留在本层
 *  - 注意：管理端 URL 统一 /admin/* 前缀，与用户端 /courses /dashboard 路由隔离
 */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <AdminGuard>
      <AdminShell>{children}</AdminShell>
    </AdminGuard>
  );
}

/** 面包屑段落 → 中文标签 */
const CRUMB_LABELS: Record<string, string> = {
  admin: "管理端",
  dashboard: "仪表盘",
  courses: "课程",
  questions: "题库",
  users: "用户",
  rag: "RAG",
  mcp: "MCP",
};

function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const me = useAuthStore((s) => s.me);
  const logout = useAuthStore((s) => s.logout);

  const navItems = useMemo(() => filterAdminNav(me?.roles), [me?.roles]);

  const crumbs = useMemo(() => {
    const parts = pathname
      .split("/")
      .filter(Boolean)
      .filter((p) => p !== "admin");
    return parts.map((p, i) => CRUMB_LABELS[p] ?? (i === parts.length - 1 ? "详情" : p));
  }, [pathname]);

  const nickname =
    typeof me?.nickname === "string" && me.nickname ? me.nickname : "管理员";
  const avatarText = nickname.trim().charAt(0).toUpperCase() || "A";

  function handleLogout() {
    logout({ silent: false });
    toast.success("已退出登录");
    router.replace("/login");
    router.refresh();
  }

  const breadcrumb = (
    <nav aria-label="面包屑" className="flex items-center gap-1.5 text-sm min-w-0">
      <span className="shrink-0 text-muted-foreground">管理端</span>
      {crumbs.map((label, i) => (
        <span key={`${i}-${label}`} className="flex items-center gap-1.5 min-w-0">
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          <span
            className={cn(
              "truncate",
              i === crumbs.length - 1
                ? "font-medium text-secondary-foreground"
                : "text-muted-foreground",
            )}
          >
            {label}
          </span>
        </span>
      ))}
    </nav>
  );

  const userInfo = (
    <>
      <span
        aria-hidden="true"
        className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-primary-deep to-primary text-white text-xs font-semibold"
      >
        {avatarText}
      </span>
      <span className="hidden md:inline text-sm text-secondary-foreground font-medium max-w-[120px] truncate">
        {nickname}
      </span>
      <Button
        variant="ghost"
        size="sm"
        className="gap-1.5 text-muted-foreground"
        onClick={handleLogout}
      >
        <LogOut className="h-4 w-4" />
        退出
      </Button>
    </>
  );

  return (
    <AppShell
      brand={{ href: "/admin/dashboard", label: "EduAgent 管理端", Icon: ShieldCheck }}
      navItems={navItems}
      navAriaLabel="管理端导航"
      headerLeft={breadcrumb}
      headerRight={userInfo}
      pageClassName="bg-muted/40"
      contentClassName="p-4 md:p-6"
      footer={
        <p className="px-1 text-3xs leading-relaxed text-sidebar-foreground/60">
          © EduAgent · 管理控制台
        </p>
      }
    >
      {children}
    </AppShell>
  );
}
