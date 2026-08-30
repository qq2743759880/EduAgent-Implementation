"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * 根路由：直接进入糖果色静态页面（fe-html 签收版）
 * - 用户端仪表盘：/dashboard.html
 * - 页面间跳转由静态 HTML 内相对链接（courses.html / chat.html 等）驱动
 */
export default function RootHomePage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/dashboard.html");
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground bg-gradient-to-br from-primary-soft via-white to-secondary">
      正在进入 EduAgent…
    </div>
  );
}
