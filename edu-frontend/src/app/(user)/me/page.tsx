"use client";

import { Suspense, useMemo } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronLeft, LayoutDashboard } from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import BasicProfileForm from "@/components/profile/BasicProfileForm";
import PreferencesForm from "@/components/profile/PreferencesForm";
import ProfileLayout from "@/components/profile/ProfileLayout";
import { useAuthStore } from "@/lib/auth-client";
import { ProtectedRoute } from "@/lib/protected-route";
import type { SubjectKey } from "@/lib/validators/profile-schemas";

type ProfileTabKey = "basic" | "preferences";
const VALID_TABS: ProfileTabKey[] = ["basic", "preferences"];

function ProfilePageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const me = useAuthStore((s) => s.me);
  const anyMe = me as (UserInfoExtended | null) | undefined;

  // 受控 Tabs：从 URL ?tab= 读取（修复 ISSUE #2：原来用 defaultValue，/me?tab=preferences 永远不生效）
  const activeTab: ProfileTabKey = useMemo(() => {
    const raw = searchParams?.get("tab")?.trim()?.toLowerCase();
    return VALID_TABS.includes(raw as any) ? (raw as ProfileTabKey) : "basic";
  }, [searchParams]);

  // 用户切 tab 时同步写回 URL（保证可刷新/可分享，保持导航一致）
  function onTabChange(next: string) {
    const safe: ProfileTabKey = VALID_TABS.includes(next as any) ? (next as ProfileTabKey) : "basic";
    const params = new URLSearchParams(searchParams?.toString() ?? "");
    if (safe === "basic") {
      params.delete("tab");
    } else {
      params.set("tab", safe);
    }
    const qs = params.toString();
    router.replace(`/me${qs ? `?${qs}` : ""}`, { scroll: false });
  }

  const subjectPreferences = useMemo<SubjectKey[]>(() => {
    const raw = anyMe?.subjectPreferences;
    if (!Array.isArray(raw)) return [];
    return raw.filter((x): x is SubjectKey => typeof x === "string");
  }, [anyMe]);

  const points = typeof anyMe?.points === "number" ? anyMe.points : null;

  return (
    <>
      <div className="w-full max-w-6xl mx-auto mb-5 flex items-center justify-between text-sm text-muted-foreground">
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-1 hover:text-foreground hover:underline underline-offset-4"
        >
          <ChevronLeft className="h-4 w-4" />
          返回仪表盘
        </Link>
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-1.5 text-primary hover:text-primary-strong hover:underline underline-offset-4"
        >
          <LayoutDashboard className="h-3.5 w-3.5" />
          开始学习
        </Link>
      </div>
      <ProfileLayout points={points} subjectPreferences={subjectPreferences}>
        <Tabs value={activeTab} onValueChange={onTabChange} className="w-full">
          <TabsList className="grid grid-cols-2 max-w-xs mb-5 shadow-card bg-card border border-border">
            <TabsTrigger value="basic" className="h-9">基本资料</TabsTrigger>
            <TabsTrigger value="preferences" className="h-9">偏好设置</TabsTrigger>
          </TabsList>
          <TabsContent value="basic" className="mt-0">
            <BasicProfileForm />
          </TabsContent>
          <TabsContent value="preferences" className="mt-0">
            <PreferencesForm />
          </TabsContent>
        </Tabs>
      </ProfileLayout>
    </>
  );
}

type UserInfoExtended = {
  subjectPreferences?: unknown;
  points?: unknown;
};

export default function ProfilePage() {
  return (
    <ProtectedRoute>
      {/* Suspense 边界：ProfilePageInner 使用 useSearchParams（修复 Next.js 构建期 ESLint/SSR 告警）*/}
      <Suspense
        fallback={
          <div className="min-h-[70vh] flex items-center justify-center text-sm text-muted-foreground">
            正在加载个人中心…
          </div>
        }
      >
        <ProfilePageInner />
      </Suspense>
    </ProtectedRoute>
  );
}
