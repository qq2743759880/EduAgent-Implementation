"use client";

import { ComponentType, Suspense, type JSX, useEffect, type ReactNode } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { useAuthStore } from "./auth-client";
import { isSafeRedirect } from "./redirect";

/* -------------------------------------------------------------------------- */
/*                                ProtectedRoute                              */
/* -------------------------------------------------------------------------- */

/**
 * 受保护路由（登录后才能访问）：
 * - 用法一（包裹整个 page component）：
 *     export default withAuth(DashboardPage);
 * - 用法二（JSX 包裹 children）：
 *     <ProtectedRoute><DashboardPage /></ProtectedRoute>
 */
export function ProtectedRoute({
  children,
  loginPath = "/login",
}: {
  children: ReactNode;
  loginPath?: string;
}) {
  // useSearchParams 必须被 Suspense 边界包裹（避免 SSR / build 报错 & nextjs 14+ lint 告警）
  return (
    <Suspense
      fallback={
        <div className="min-h-[70vh] flex items-center justify-center text-sm text-slate-500">
          正在校验登录状态…
        </div>
      }
    >
      <ProtectedRouteInner loginPath={loginPath}>{children}</ProtectedRouteInner>
    </Suspense>
  );
}

function ProtectedRouteInner({
  children,
  loginPath,
}: {
  children: ReactNode;
  loginPath: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const { ready, token } = useAuthStore();

  useEffect(() => {
    if (!ready) return;
    if (token) return;
    const from = pathname + (search?.toString() ? `?${search.toString()}` : "");
    const dest = new URL(loginPath, typeof window === "undefined" ? "http://localhost" : window.location.origin);
    if (from && from !== loginPath) dest.searchParams.set("redirect", from);
    toast.warning("请先登录");
    router.replace(dest.pathname + dest.search);
  }, [ready, token, router, pathname, search, loginPath]);

  if (!ready || !token) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center text-sm text-slate-500">
        正在校验登录状态…
      </div>
    );
  }
  return <>{children}</>;
}

export function withAuth<P extends object>(
  Wrapped: ComponentType<P>,
  opts?: { loginPath?: string },
): (props: P) => JSX.Element {
  function WithAuthInner(props: P) {
    return (
      <ProtectedRoute loginPath={opts?.loginPath}>
        <Wrapped {...props} />
      </ProtectedRoute>
    );
  }
  WithAuthInner.displayName = `withAuth(${Wrapped.displayName || Wrapped.name || "Component"})`;
  return WithAuthInner;
}

/* -------------------------------------------------------------------------- */
/*                                GuestOnlyRoute                              */
/* -------------------------------------------------------------------------- */

/**
 * 游客专用路由（已登录访问 login/register → 自动跳 /dashboard）：
 * 用法：<GuestOnlyRoute><LoginPage /></GuestOnlyRoute>
 */
export function GuestOnlyRoute({
  children,
  redirectAfterLogin = "/dashboard",
}: {
  children: ReactNode;
  redirectAfterLogin?: string;
}) {
  return (
    <Suspense
      fallback={
        <div className="min-h-[70vh] flex items-center justify-center text-sm text-slate-500">
          跳转中…
        </div>
      }
    >
      <GuestOnlyRouteInner redirectAfterLogin={redirectAfterLogin}>{children}</GuestOnlyRouteInner>
    </Suspense>
  );
}

function GuestOnlyRouteInner({
  children,
  redirectAfterLogin,
}: {
  children: ReactNode;
  redirectAfterLogin: string;
}) {
  const router = useRouter();
  const search = useSearchParams();
  const { ready, token } = useAuthStore();

  useEffect(() => {
    if (!ready) return;
    if (!token) return;
    const redirect = search?.get("redirect")?.trim();
    const dest = redirect && isSafeRedirect(redirect) ? redirect : redirectAfterLogin;
    router.replace(dest);
  }, [ready, token, router, search, redirectAfterLogin]);

  if (!ready || token) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center text-sm text-slate-500">
        跳转中…
      </div>
    );
  }
  return <>{children}</>;
}

export function withGuestOnly<P extends object>(
  Wrapped: ComponentType<P>,
  opts?: { redirectAfterLogin?: string },
): (props: P) => JSX.Element {
  function WithGuestOnlyInner(props: P) {
    return (
      <GuestOnlyRoute redirectAfterLogin={opts?.redirectAfterLogin}>
        <Wrapped {...props} />
      </GuestOnlyRoute>
    );
  }
  WithGuestOnlyInner.displayName = `withGuestOnly(${Wrapped.displayName || Wrapped.name || "Component"})`;
  return WithGuestOnlyInner;
}
