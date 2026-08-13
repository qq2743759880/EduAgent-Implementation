"use client";

import { type ReactNode, Suspense, useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";

import { useAuthStore } from "@/lib/auth-client";
import { ADMIN_NAV_ITEMS, isAdminRole } from "@/lib/admin-nav";

/**
 * 管理端角色守卫（task02，G2 管理端布局与权限）
 *
 * 规则（RBAC，2026-08-12 对抗修正 #2 收紧为仅 admin）：
 *  - admin → 放行渲染 children
 *  - manager / teacher / student / 未知角色 → 拦截：toast 提示无权限 + 重定向回用户端（默认 /dashboard）
 *  - 未登录 → toast 提示请先登录 + 跳登录页并带 ?redirect= 回跳原 URL
 *  - hydrate 完成前显示校验占位（无白屏）
 *
 * 说明：
 *  - 后端 /api/admin/* 全部 require_role([ADMIN])（manager 实测 403），前端守卫与之一致，
 *    manager 不再放行（对抗 #2 处置：后端 ADMIN-only 为权威契约）。
 *  - 后端 DEBUG 鉴权绕过（无 token 即虚拟 admin）属既有后端设计（对抗 #1），本轮不改后端；
 *    上线硬门槛为 .env DEBUG=false，CORS 收紧（main.py 现为 *）待后端迭代，见挑战报告处置结论。
 *  - useSearchParams 必须包在 Suspense 边界内（Next.js 约束，参照 protected-route.tsx）
 *  - 服务端组件勿直接调用本组件依赖的 hook，本组件已标记 "use client"
 */
export function AdminGuard({
  children,
  loginPath = "/login",
  studentRedirectPath = "/dashboard",
}: {
  children: ReactNode;
  loginPath?: string;
  studentRedirectPath?: string;
}) {
  return (
    <Suspense
      fallback={
        <AdminShellSkeleton ariaHidden />
      }
    >
      <AdminGuardInner loginPath={loginPath} studentRedirectPath={studentRedirectPath}>
        {children}
      </AdminGuardInner>
    </Suspense>
  );
}

function AdminGuardInner({
  children,
  loginPath,
  studentRedirectPath,
}: {
  children: ReactNode;
  loginPath: string;
  studentRedirectPath: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const { ready, token, me } = useAuthStore();

  useEffect(() => {
    if (!ready) return;

    if (!token) {
      // 未登录：跳登录页并携带 redirect 回跳原 URL（登录成功后 GuestOnlyRoute 处理回跳）
      const from = pathname + (search?.toString() ? `?${search.toString()}` : "");
      const dest = new URL(
        loginPath,
        typeof window === "undefined" ? "http://localhost" : window.location.origin,
      );
      if (from && from !== loginPath) dest.searchParams.set("redirect", from);
      toast.warning("请先登录");
      router.replace(dest.pathname + dest.search);
      return;
    }

    if (!isAdminRole(me?.roles)) {
      // 已登录但非 admin（manager/teacher/student）：拦截 + 提示 + 重定向回用户端
      toast.error("无权限访问管理端");
      router.replace(studentRedirectPath);
    }
  }, [ready, token, me, router, pathname, search, loginPath, studentRedirectPath]);

  if (!ready || !token || !isAdminRole(me?.roles)) {
    return <AdminShellSkeleton />;
  }
  return <>{children}</>;
}

/**
 * 管理端布局骨架（perf P1 #1 处置：SSR 静态壳下沉）。
 *
 * - 纯展示组件：无 hooks / 无交互元素 / 无 landmark，仅输出品牌区 + 菜单占位结构，
 *   使 SSR HTML 直接携带管理端壳骨架（而非仅一行占位文案），LCP 提前到 HTML 解析即见。
 * - 安全语义不降级：不渲染真实链接与角色过滤结果，菜单仅为占位条（数据取自 admin-nav.ts
 *   纯常量，可 SSR）；真实壳与守卫判定行为完全不变（守卫仍客户端强制，后端 /api/admin/* ADMIN-only 为权威）。
 * - ariaHidden=true（Suspense 边界场景）：整骨架对读屏器隐藏，仅作为视觉占位；
 *   常规校验占位场景保留可读状态文案。
 */
function AdminShellSkeleton({ ariaHidden = false }: { ariaHidden?: boolean }) {
  return (
    <div className="min-h-screen flex bg-slate-100/70" aria-hidden={ariaHidden || undefined}>
      {/* 侧边栏骨架（桌面 SSR 可见；移动端隐藏，与真实壳抽屉关闭态一致） */}
      <div className="hidden md:flex fixed z-40 inset-y-0 left-0 w-64 border-r border-slate-200 bg-white flex-col">
        <div className="h-16 border-b border-slate-200 px-5 flex items-center gap-2">
          <div className="h-8 w-8 shrink-0 rounded-xl bg-slate-200" />
          <div className="h-4 w-32 rounded bg-slate-200" />
        </div>
        <div className="flex-1 px-3 py-4 overflow-y-auto">
          <div className="space-y-1">
            {ADMIN_NAV_ITEMS.map((item) => (
              <div key={item.href} className="h-10 rounded-xl bg-slate-100" />
            ))}
          </div>
        </div>
        <div className="border-t border-slate-200 px-3 py-3">
          <div className="h-3 w-36 rounded bg-slate-200" />
        </div>
      </div>

      {/* 主区骨架：顶栏 + 内容区校验文案 */}
      <div className="flex-1 min-w-0 md:ml-64 flex flex-col">
        <div className="h-14 border-b border-slate-200 bg-white/80 px-4 md:px-6 flex items-center gap-2">
          <div className="h-4 w-24 rounded bg-slate-200" />
        </div>
        <main className="flex-1 min-w-0 w-full p-4 md:p-6 flex items-center justify-center">
          <p className="text-sm text-slate-500">正在校验登录状态…</p>
        </main>
      </div>
    </div>
  );
}
