/**
 * MyCoursesClient — 我的班次客户端逻辑（task47，重构为 enrollments 语义）
 *
 * - 保护路由：未登录 → login?redirect=
 * - 数据来源：契约⑪ GET /api/enrollments/me/cohorts?status= （后端 task20/21 待联调）
 * - Tabs 由 enroll_status 驱动：active 学习中 / completed 已完成 / refunded 已退款
 *   （cancelled 契约① 后并入 neutral，不独立成 tab）
 * - 卡片：CohortCard（重组 P8 line 模式 Panel + P10 P3 语义，后台返回即渲染，无 MOCK）
 */
"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { GraduationCap, Loader2, RefreshCcw, Trophy } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { useAuthStore } from "@/lib/auth-client";
import {
  getEnrolledCohorts,
  type EnrolledCohort,
  type EnrolledTabId,
} from "@/lib/api/enrollments";
import { CohortCard } from "@/components/feature/cohort-card";

const TABS: { id: EnrolledTabId; label: string }[] = [
  { id: "active", label: "学习中" },
  { id: "completed", label: "已完成" },
  { id: "refunded", label: "已退款" },
];

const TAB_IDS = TABS.map((t) => t.id);

function tabFromUrl(sp: ReturnType<typeof useSearchParams>): EnrolledTabId {
  const raw = sp.get("tab");
  return isTabId(raw) ? raw : "active";
}

function isTabId(v: string | null): v is EnrolledTabId {
  return !!v && (TAB_IDS as string[]).includes(v);
}

export default function MyCoursesClient() {
  const router = useRouter();
  const sp = useSearchParams();
  const ready = useAuthStore((s) => s.ready);
  const token = useAuthStore((s) => s.token);
  const authed = ready && !!token;

  /* 保护路径：hydrate 完成后未登录 → 跳 login（redirect 回当前页） */
  useEffect(() => {
    if (!ready) return; // 等 providers hydrate，避免硬刷新瞬时误跳 /login（getting-ready 守卫）
    if (authed) return;
    const redirect = encodeURIComponent("/my-courses" + (window?.location.search ?? ""));
    router.replace(`/login?redirect=${redirect}`);
  }, [ready, authed, router]);

  /* URL 为 tab 唯一事实源：读 searchParams 派生；点击经 onValueChange 写回 URL */
  const tab: EnrolledTabId = tabFromUrl(sp);

  /* 拉取全部班次并在本地按 enroll_status 分组，保证三 tab 计数真实 */
  const q = useQuery({
    queryKey: ["enrollments", "me"] as const,
    queryFn: () => getEnrolledCohorts(),
    staleTime: 60_000,
    enabled: !!authed,
  });

  /* 按 enroll_status 分组（cancelled 并入 neutral 不计入三 tab） */
  const groups = useMemo(() => {
    const list = q.data ?? [];
    const g: Record<EnrolledTabId, EnrolledCohort[]> = { active: [], completed: [], refunded: [] };
    for (const c of list) {
      if (c.enroll_status === "active") g.active.push(c);
      else if (c.enroll_status === "completed") g.completed.push(c);
      else if (c.enroll_status === "refunded") g.refunded.push(c);
    }
    return g;
  }, [q.data]);

  const badgeCounts = useMemo(
    () => ({
      active: groups.active.length,
      completed: groups.completed.length,
      refunded: groups.refunded.length,
    }),
    [groups],
  );

  if (!authed) return <AuthRedirectSkeleton />;

  return (
    <div className="space-y-5">
      <Tabs
        value={tab}
        onValueChange={(v) => {
          if (isTabId(v)) router.push(`/my-courses?tab=${v}`, { scroll: false });
        }}
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <TabsList variant="line" className="gap-1">
            {TABS.map((t) => (
              <TabsTrigger key={t.id} value={t.id} className="gap-2">
                {t.id === "active" ? (
                  <GraduationCap className="h-4 w-4" />
                ) : t.id === "completed" ? (
                  <Trophy className="h-4 w-4" />
                ) : null}
                {t.label}
                <Badge variant="secondary" className="h-5 px-1.5 py-0 text-4xs">
                  {badgeCounts[t.id]}
                </Badge>
              </TabsTrigger>
            ))}
          </TabsList>

          <Button
            variant="ghost"
            size="sm"
            onClick={() => void q.refetch()}
            disabled={q.isFetching}
          >
            <RefreshCcw className={"mr-1.5 h-4 w-4 " + (q.isFetching ? "animate-spin" : "")} />
            刷新
          </Button>
        </div>

        {q.isError ? (
          <ErrorState
            title="加载我的班次失败"
            message={q.error instanceof Error ? q.error.message : "GET /api/enrollments/me/cohorts 暂不可达"}
            retry={() => q.refetch()}
          />
        ) : q.isLoading && !q.data ? (
          <GridSkeleton />
        ) : (
          <>
            {TABS.map((t) => (
              <TabsContent key={t.id} value={t.id}>
                <EnrolledGrid data={groups[t.id]} tabId={t.id} />
              </TabsContent>
            ))}
          </>
        )}
      </Tabs>
    </div>
  );
}

function EnrolledGrid({
  data,
  tabId,
}: {
  data: EnrolledCohort[];
  tabId: EnrolledTabId;
}) {
  if (!data.length) {
    return (
      <EmptyState
        icon={<GraduationCap />}
        title={tabId === "active" ? "还没有报名班次" : tabId === "completed" ? "还没有已完成的班次" : "还没有退款记录"}
        description={
          tabId === "active"
            ? "去课程中心挑一门喜欢的课程，开始你的学习之旅吧"
            : tabId === "completed"
              ? "坚持学习，完成第一个班次就能在这里看到它"
              : "申请退款的班次会出现在这里"
        }
        action={
          <Button asChild size="sm">
            <Link href="/courses">去选课 →</Link>
          </Button>
        }
      />
    );
  }
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {data.map((item) => (
        <CohortCard key={item.enrollment_id ?? item.cohort_id} data={item} />
      ))}
    </div>
  );
}

function GridSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 2 }).map((_, i) => (
        <div key={i} className="overflow-hidden rounded-[1.75rem] border-2 border-foreground/15 bg-card">
          <div className="h-20 w-full animate-pulse bg-muted" />
          <div className="space-y-3 p-4">
            <div className="h-3 w-1/3 animate-pulse rounded bg-muted" />
            <div className="h-3.5 w-full animate-pulse rounded-full bg-muted" />
            <div className="h-3 w-4/5 animate-pulse rounded bg-muted" />
            <div className="h-8 w-full animate-pulse rounded-lg bg-muted" />
          </div>
        </div>
      ))}
    </div>
  );
}

function AuthRedirectSkeleton() {
  return (
    <div className="rounded-xl border border-dashed border-border p-10 text-center">
      <Loader2 className="mx-auto mb-2 h-6 w-6 animate-spin text-primary" />
      <div className="text-base font-semibold text-foreground">正在跳转登录…</div>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
        「我的班次」需要登录后才能看到你报名的所有班次。
      </p>
    </div>
  );
}