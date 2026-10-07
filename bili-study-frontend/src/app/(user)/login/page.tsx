"use client";

import AuthCard from "@/components/auth/AuthCard";
import LoginForm from "@/components/auth/LoginForm";
import { GuestOnlyRoute } from "@/lib/protected-route";

export default function LoginPage() {
  return (
    <GuestOnlyRoute>
      <AuthCard
        title="欢迎回来"
        subtitle="登录后开始你的个性化学习旅程"
        footerHint="还没有账号？"
        footerLinkLabel="免费注册"
        footerLinkHref="/register"
      >
        <LoginForm />
      </AuthCard>
    </GuestOnlyRoute>
  );
}
