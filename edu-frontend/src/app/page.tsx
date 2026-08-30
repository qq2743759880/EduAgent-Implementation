"use client";

import { Suspense, useEffect, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuthStore } from "@/lib/auth-client";
import { isSafeRedirect } from "@/lib/redirect";

/**
 * 根路由：根据登录态重定向
 * - 未登录 → /login（携带 ?redirect= 保持回跳）
 * - 已登录 → /dashboard 或 URL 指定的 ?redirect= 目标（安全正则校验，防 Open Redirect）
 */
function RootHomePageInner() {
  const router = useRouter();
  const search = useSearchParams();
  const { ready, token } = useAuthStore();

  const redirect = useMemo(() => {
    const raw = search?.get("redirect")?.trim();
    if (raw && isSafeRedirect(raw)) return raw;
    return null;
  }, [search]);

  useEffect(() => {
    if (!ready) return;
    if (token) {
      // 已登录：优先按 URL 指定 redirect 跳，否则回仪表盘
      router.replace(redirect ?? "/dashboard");
    } else {
      // 未登录：去登录页，把当前已有的 redirect（如果是当前用户要去的地方）保留透传给 login
      const dest = new URLSearchParams();
      if (redirect) dest.set("redirect", redirect);
      const qs = dest.toString();
      router.replace(`/login${qs ? `?${qs}` : ""}`);
    }
  }, [ready, token, router, redirect]);

  return (
    <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground bg-gradient-to-br from-primary-soft via-white to-secondary">
      正在进入 EduAgent…
    </div>
  );
}

export default function RootHomePage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground bg-gradient-to-br from-primary-soft via-white to-secondary">
          正在进入 EduAgent…
        </div>
      }
    >
      <RootHomePageInner />
    </Suspense>
  );
}
