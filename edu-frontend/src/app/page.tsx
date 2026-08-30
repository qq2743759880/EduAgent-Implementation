"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * 根路由：进入 fe-html 糖果色静态页入口
 * - 未登录/已登录都先进 login-register.html（页面内判断跳转 /dashboard.html）
 * - 登录后存 token（localStorage edu:auth:token），各静态页 edu-api.js 读取
 */
export default function RootHomePage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/login-register.html");
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground bg-gradient-to-br from-primary-soft via-white to-secondary">
      正在进入 EduAgent…
    </div>
  );
}
