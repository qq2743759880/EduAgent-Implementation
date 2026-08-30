"use client";

import AuthCard from "@/components/auth/AuthCard";
import RegisterForm from "@/components/auth/RegisterForm";
import { GuestOnlyRoute } from "@/lib/protected-route";

export default function RegisterPage() {
  return (
    <GuestOnlyRoute>
      <AuthCard
        title="创建你的学习账号"
        subtitle="加入 EduAgent，获取个性化学习路径与徽章激励"
        footerHint="已有账号？"
        footerLinkLabel="直接登录"
        footerLinkHref="/login"
      >
        <RegisterForm />
      </AuthCard>
    </GuestOnlyRoute>
  );
}
