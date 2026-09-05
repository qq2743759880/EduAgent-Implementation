"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * /admin：管理端入口路由，无独立页面内容，跳转到默认管理页 /admin/dashboard
 * - 守卫在 (admin)/layout.tsx 的 AdminGuard 中统一处理（admin/manager 放行，其余拦截）
 * - 原 /admin 直接 404（目录下只有 dashboard/courses/mcp/questions/rag/users 子路由），C1 补入口
 */
export default function AdminIndexPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/admin/dashboard");
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground bg-gradient-to-br from-primary-soft via-white to-secondary">
      正在进入管理后台…
    </div>
  );
}
